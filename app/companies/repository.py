from app.database import database_mongo
from app.repositories.mongo import MongoRepository
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from app.exceptions import InternalError
from app.logger import logger


class CompaniesRepository(MongoRepository):
    async def read_page(self, pipeline: list[dict]) -> dict:
        try:
            result = await self._collection.aggregate(pipeline).to_list(length=1)
            if len(result) != 1 or "items" not in result[0] or "total" not in result[0]:
                raise InternalError("Не удалось загрузить компании")
            return result[0]
        except PyMongoError as exc:
            logger.error("Could not load company page", exc_info=True)
            raise InternalError("Не удалось загрузить компании") from exc

    async def add_role(self, company_id, role: str) -> dict | None:
        return await self._collection.find_one_and_update(
            {"_id": company_id, "deletedAt": None},
            {"$addToSet": {"roles": role}},
            return_document=ReturnDocument.AFTER,
        )


companies_repository = CompaniesRepository(database_mongo["companies"])
