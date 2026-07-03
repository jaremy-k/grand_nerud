import re
from datetime import datetime, timezone
from typing import Any, Optional, Union

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.results import DeleteResult, InsertManyResult, UpdateResult

from app.core.pagination import PaginatedResponse
from app.logger import logger


class MongoRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        self._collection = collection

    async def find_one(
            self,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            **kwargs,
    ) -> Optional[dict[str, Any]]:
        try:
            query = filter_by or {}
            query.update(kwargs)
            return await self._collection.find_one(query, projection)
        except Exception as e:
            logger.error("Error finding document: %s", e, exc_info=True)
            return None

    async def find_many(
            self,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
            **kwargs,
    ) -> list[dict[str, Any]]:
        try:
            query = filter_by or {}
            query.update(kwargs)
            cursor = self._collection.find(query, projection)
            if sort:
                cursor = cursor.sort(sort)
            cursor = cursor.skip(skip).limit(limit)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error("Error finding documents: %s", e, exc_info=True)
            return []

    async def find_paginated(
            self,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
            **kwargs,
    ) -> PaginatedResponse:
        try:
            query = filter_by or {}
            query.update(kwargs)
            total = await self._collection.count_documents(query)
            cursor = self._collection.find(query, projection)
            if sort:
                cursor = cursor.sort(sort)
            cursor = cursor.skip(skip).limit(limit)
            items = [doc async for doc in cursor]

            for item in items:
                if "_id" in item and isinstance(item["_id"], ObjectId):
                    item["_id"] = str(item["_id"])
                for key, value in item.items():
                    if isinstance(value, ObjectId):
                        item[key] = str(value)

            page = (skip // limit) + 1 if limit > 0 else 1
            total_pages = (total + limit - 1) // limit if limit > 0 else 1
            return PaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=limit,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            )
        except Exception as e:
            logger.error("Error finding paginated documents: %s", e, exc_info=True)
            return PaginatedResponse(
                items=[], total=0, page=1, page_size=limit,
                total_pages=0, has_next=False, has_prev=False,
            )

    async def aggregate(self, pipeline: list[dict]) -> list[dict[str, Any]]:
        try:
            cursor = self._collection.aggregate(pipeline)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error("Error executing aggregation: %s", e, exc_info=True)
            return []

    async def create(self, document: dict) -> Optional[dict[str, Any]]:
        try:
            result = await self._collection.insert_one(document)
            if result.inserted_id:
                return await self._collection.find_one({"_id": result.inserted_id})
            return None
        except Exception as e:
            logger.error("Error inserting document: %s", e, exc_info=True)
            return None

    async def update_by_id(
            self,
            object_id: Union[str, ObjectId],
            update_data: dict,
            upsert: bool = False,
    ) -> Optional[dict[str, Any]]:
        try:
            if isinstance(object_id, str):
                object_id = ObjectId(object_id)
            result: UpdateResult = await self._collection.update_one(
                {"_id": object_id},
                {"$set": update_data},
                upsert=upsert,
            )
            if result.matched_count == 0 and not upsert:
                return None
            return await self._collection.find_one({"_id": object_id})
        except Exception as e:
            logger.error("Error updating document: %s", e, exc_info=True)
            return None

    async def update_many(self, filter_by: dict, update_data: dict, upsert: bool = False) -> int:
        try:
            result: UpdateResult = await self._collection.update_many(
                filter_by, {"$set": update_data}, upsert=upsert,
            )
            return result.modified_count
        except Exception as e:
            logger.error("Error updating documents: %s", e, exc_info=True)
            return 0

    async def delete_one(self, filter_by: dict, **kwargs) -> bool:
        try:
            query = filter_by.copy()
            query.update(kwargs)
            result: DeleteResult = await self._collection.delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            logger.error("Error deleting document: %s", e, exc_info=True)
            return False

    async def delete_many(self, filter_by: dict, **kwargs) -> int:
        try:
            query = filter_by.copy()
            query.update(kwargs)
            result: DeleteResult = await self._collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error("Error deleting documents: %s", e, exc_info=True)
            return 0

    async def create_many(
            self,
            documents: list[dict],
            ordered: bool = True,
    ) -> Optional[list[ObjectId]]:
        try:
            result: InsertManyResult = await self._collection.insert_many(documents, ordered=ordered)
            return result.inserted_ids
        except Exception as e:
            logger.error("Error bulk inserting documents: %s", e, exc_info=True)
            return None

    async def count(self, filter_by: Optional[dict] = None, **kwargs) -> int:
        try:
            query = filter_by or {}
            query.update(kwargs)
            return await self._collection.count_documents(query)
        except Exception as e:
            logger.error("Error counting documents: %s", e, exc_info=True)
            return 0

    async def is_unique(
            self,
            field_name: str,
            value: Optional[Union[str, int]],
            exclude_id: Optional[Union[str, ObjectId]] = None,
            case_sensitive: bool = False,
            trim_spaces: bool = True,
    ) -> bool:
        try:
            if value is None:
                query_value = None
            elif isinstance(value, str):
                query_value = value.strip() if trim_spaces else value
            else:
                query_value = value

            if isinstance(query_value, str) and not case_sensitive:
                query = {field_name: {"$regex": f"^{re.escape(query_value)}$", "$options": "i"}}
            else:
                query = {field_name: query_value}

            if exclude_id is not None:
                if isinstance(exclude_id, str):
                    exclude_id = ObjectId(exclude_id)
                query["_id"] = {"$ne": exclude_id}

            existing = await self._collection.find_one(query)
            return existing is None
        except Exception as e:
            logger.error("Error checking uniqueness: %s", e, exc_info=True)
            return False

    async def soft_delete(
            self,
            object_id: Union[str, ObjectId],
            deleted_at_field: str = "deletedAt",
    ) -> Optional[dict[str, Any]]:
        try:
            update_data = {deleted_at_field: datetime.now(timezone.utc)}
            return await self.update_by_id(object_id=object_id, update_data=update_data)
        except Exception as e:
            logger.error("Error soft-deleting document: %s", e, exc_info=True)
            return None
