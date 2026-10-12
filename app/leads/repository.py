from pymongo import ReturnDocument

from app.core.crm import utc_now
from app.database import database_mongo
from app.repositories.mongo import MongoRepository


class LeadsRepository(MongoRepository):
    async def attach_followup(self, lead: dict, task_id) -> dict | None:
        return await self._collection.find_one_and_update(
            {
                "_id": lead["_id"], "deletedAt": None, "dealId": None, "conversionDealId": None,
                "updatedAt": lead["updatedAt"], "nextContactAt": lead["nextContactAt"],
            },
            {"$set": {"followUpTaskId": task_id}},
            return_document=ReturnDocument.AFTER,
        )

    async def clear_followup(self, lead: dict) -> dict | None:
        return await self._collection.find_one_and_update(
            {
                "_id": lead["_id"], "deletedAt": lead.get("deletedAt"),
                "updatedAt": lead["updatedAt"], "followUpTaskId": lead.get("followUpTaskId"),
            },
            {"$set": {"nextContactAt": None, "followUpTaskId": None, "updatedAt": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def reserve_conversion(self, lead: dict, payload: dict, deal_id, document: dict) -> dict | None:
        return await self._collection.find_one_and_update(
            {
                "_id": lead["_id"], "deletedAt": None,
                "stageId": lead["stageId"], "ownerId": lead["ownerId"],
                "updatedAt": lead.get("updatedAt"),
                "conversionDealId": None, "dealId": None,
            },
            {"$set": {
                "conversionDealId": deal_id,
                "conversionInput": payload,
                "conversionDocument": document,
                "updatedAt": utc_now(),
            }},
            return_document=ReturnDocument.AFTER,
        )

    async def update_unconverted(self, lead: dict, payload: dict) -> dict | None:
        return await self._collection.find_one_and_update(
            {
                "_id": lead["_id"], "deletedAt": None,
                "updatedAt": lead.get("updatedAt"),
                "conversionDealId": None, "dealId": None,
            },
            {"$set": payload},
            return_document=ReturnDocument.AFTER,
        )


leads_repository = LeadsRepository(database_mongo["leads"])
lead_activities_repository = MongoRepository(database_mongo["lead_activities"])
