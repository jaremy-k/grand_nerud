from app.database import database_mongo
from app.repositories.mongo import MongoRepository
from pymongo import ReturnDocument


class TasksRepository(MongoRepository):
    async def update_followup(self, task: dict, payload: dict) -> dict | None:
        return await self._collection.find_one_and_update(
            {"_id": task["_id"], "deletedAt": None, "status": "open", "updatedAt": task.get("updatedAt")},
            {"$set": payload},
            return_document=ReturnDocument.AFTER,
        )


tasks_repository = TasksRepository(database_mongo["tasks"])
