from app.database import database_mongo
from app.repositories.mongo import MongoRepository
from pymongo import ReturnDocument


class CompaniesRepository(MongoRepository):
    async def add_role(self, company_id, role: str) -> dict | None:
        return await self._collection.find_one_and_update(
            {"_id": company_id, "deletedAt": None},
            {"$addToSet": {"roles": role}},
            return_document=ReturnDocument.AFTER,
        )


companies_repository = CompaniesRepository(database_mongo["companies"])
