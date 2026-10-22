from app.database import database_mongo
from app.exceptions import InternalError
from app.leads.service import lead_relation_lookups
from app.logger import logger
from pymongo.errors import PyMongoError


def task_relation_lookups() -> list[dict]:
    return [
        {"$lookup": {
            "from": "companies", "localField": "companyId", "foreignField": "_id",
            "pipeline": [{"$project": {"_id": 1, "name": 1}}], "as": "_workspaceCompany",
        }},
        {"$lookup": {
            "from": "leads", "localField": "leadId", "foreignField": "_id",
            "pipeline": [{"$project": {"_id": 1, "title": 1}}], "as": "_workspaceLead",
        }},
        {"$addFields": {
            "company": {"$ifNull": [{"$arrayElemAt": ["$_workspaceCompany", 0]}, None]},
            "lead": {"$ifNull": [{"$arrayElemAt": ["$_workspaceLead", 0]}, None]},
        }},
        {"$unset": ["_workspaceCompany", "_workspaceLead"]},
    ]


class WorkspaceRepository:
    def __init__(self):
        self.tasks_collection = database_mongo["tasks"]
        self.leads_collection = database_mongo["leads"]

    @staticmethod
    async def _read(collection, pipeline: list[dict]) -> dict:
        # A facet always returns one document, including for an empty collection.
        try:
            rows = await collection.aggregate(pipeline).to_list(length=1)
        except PyMongoError as exc:
            logger.exception("Could not load workspace aggregation")
            raise InternalError("Не удалось загрузить рабочий стол") from exc
        if len(rows) != 1:
            raise InternalError("Не удалось получить показатели рабочего стола")
        return rows[0]

    async def task_buckets(self, query: dict, bounds: dict, limit: int) -> dict:
        facets = {}
        for bucket, due_at in bounds.items():
            match = {"$match": {"dueAt": due_at}}
            facets[f"{bucket}Total"] = [match, {"$count": "value"}]
            facets[f"{bucket}Items"] = [
                match, {"$sort": {"dueAt": 1, "_id": 1}}, {"$limit": limit},
                *task_relation_lookups(),
            ]
        return await self._read(self.tasks_collection, [
            {"$match": query}, {"$facet": facets},
        ])

    async def new_leads(self, query: dict, limit: int) -> dict:
        return await self._read(self.leads_collection, [
            {"$match": query},
            {"$lookup": {
                "from": "lead_stages", "localField": "stageId",
                "foreignField": "_id", "as": "_workspaceStage",
            }},
            {"$match": {"_workspaceStage": {"$elemMatch": {"kind": "new", "deletedAt": None}}}},
            {"$unset": "_workspaceStage"},
            {"$facet": {
                "total": [{"$count": "value"}],
                "items": [
                    {"$sort": {"createdAt": -1, "_id": -1}}, {"$limit": limit},
                    *lead_relation_lookups(),
                ],
            }},
        ])


workspace_repository = WorkspaceRepository()
