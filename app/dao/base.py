import re
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Union

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.results import InsertManyResult, DeleteResult, UpdateResult

from app.deals.shemas import PaginatedResponse
from app.logger import logger


class MongoDAO:
    collection: AsyncIOMotorCollection = None

    @classmethod
    async def find_one_or_none(
            cls,
            filter_by: Optional[Dict] = None,
            projection: Optional[Dict] = None,
            **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Find a single document or return None."""
        try:
            query = filter_by or {}
            query.update(kwargs)
            return await cls.collection.find_one(query, projection)
        except Exception as e:
            logger.error(f"Error finding document: {str(e)}", exc_info=True)
            return None

    @classmethod
    async def find_all(
            cls,
            filter_by: Optional[Dict] = None,
            projection: Optional[Dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[List[tuple]] = None,
            **kwargs,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents with pagination and optional sorting."""
        try:
            query = filter_by or {}
            query.update(kwargs)

            cursor = cls.collection.find(query, projection)

            if sort:
                cursor = cursor.sort(sort)

            cursor = cursor.skip(skip).limit(limit)

            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Error finding documents: {str(e)}", exc_info=True)
            return []

    @classmethod
    async def find_paginated(
            cls,
            filter_by: Optional[Dict] = None,
            projection: Optional[Dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[List[tuple]] = None,
            **kwargs,
    ) -> PaginatedResponse:
        """Find documents with pagination metadata."""
        try:
            query = filter_by or {}
            query.update(kwargs)

            # Получаем общее количество документов
            total = await cls.collection.count_documents(query)

            # Получаем данные с пагинацией
            cursor = cls.collection.find(query, projection)

            if sort:
                cursor = cursor.sort(sort)

            cursor = cursor.skip(skip).limit(limit)
            items = [doc async for doc in cursor]

            # Конвертируем ObjectId в строки для сериализации
            for item in items:
                if '_id' in item and isinstance(item['_id'], ObjectId):
                    item['_id'] = str(item['_id'])
                # Также конвертируем другие ObjectId поля если нужно
                for key, value in item.items():
                    if isinstance(value, ObjectId):
                        item[key] = str(value)

            # Вычисляем метаданные пагинации
            page = (skip // limit) + 1 if limit > 0 else 1
            total_pages = (total + limit - 1) // limit if limit > 0 else 1
            has_next = page < total_pages
            has_prev = page > 1

            return PaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=limit,
                total_pages=total_pages,
                has_next=has_next,
                has_prev=has_prev
            )

        except Exception as e:
            logger.error(f"Error finding paginated documents: {str(e)}", exc_info=True)
            return PaginatedResponse(
                items=[],
                total=0,
                page=1,
                page_size=limit,
                total_pages=0,
                has_next=False,
                has_prev=False
            )

    @classmethod
    async def aggregate(cls, pipeline: List[Dict]) -> List[Dict[str, Any]]:
        """Execute aggregation pipeline"""
        try:
            cursor = cls.collection.aggregate(pipeline)
            return [doc async for doc in cursor]
        except Exception as e:
            logger.error(f"Error executing aggregation: {str(e)}", exc_info=True)
            return []

    @classmethod
    async def add(cls, document: Dict) -> Optional[Dict[str, Any]]:
        """
        Insert a document and return the created document.
        Motor-specific implementation without return_document parameter.
        """
        try:

            result = await cls.collection.insert_one(document)
            if result.inserted_id:
                return await cls.collection.find_one({"_id": result.inserted_id})
            return None
        except Exception as e:
            logger.error(f"Error inserting document: {str(e)}", exc_info=True)
            return None

    @classmethod
    async def update_by_id(
            cls,
            object_id: Union[str, ObjectId],
            update_data: Dict,
            upsert: bool = False,
            return_document: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Update a document by its ID."""
        try:
            if isinstance(object_id, str):
                object_id = ObjectId(object_id)

            result: UpdateResult = await cls.collection.update_one(
                {"_id": object_id},
                {"$set": update_data},
                upsert=upsert,
            )

            if result.modified_count == 0 and not upsert:
                return None

            return await cls.collection.find_one({"_id": object_id})
        except Exception as e:
            logger.error(f"Error updating document: {str(e)}", exc_info=True)
            return None

    @classmethod
    async def update_many(
            cls,
            filter_by: Dict,
            update_data: Dict,
            upsert: bool = False,
    ) -> int:
        """Update multiple documents and return the count of modified documents."""
        try:
            result: UpdateResult = await cls.collection.update_many(
                filter_by,
                {"$set": update_data},
                upsert=upsert,
            )
            return result.modified_count
        except Exception as e:
            logger.error(f"Error updating documents: {str(e)}", exc_info=True)
            return 0

    @classmethod
    async def delete_one(cls, filter_by: Dict, **kwargs) -> bool:
        """Delete a single document matching the filter."""
        try:
            query = filter_by.copy()
            query.update(kwargs)

            result: DeleteResult = await cls.collection.delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}", exc_info=True)
            return False

    @classmethod
    async def delete_many(cls, filter_by: Dict, **kwargs) -> int:
        """Delete multiple documents and return the count of deleted documents."""
        try:
            query = filter_by.copy()
            query.update(kwargs)

            result: DeleteResult = await cls.collection.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting documents: {str(e)}", exc_info=True)
            return 0

    @classmethod
    async def add_bulk(
            cls,
            documents: List[Dict],
            ordered: bool = True,
    ) -> Optional[List[ObjectId]]:
        """Bulk insert documents and return their IDs."""
        try:
            result: InsertManyResult = await cls.collection.insert_many(
                documents,
                ordered=ordered,
            )
            return result.inserted_ids
        except Exception as e:
            logger.error(f"Error bulk inserting documents: {str(e)}", exc_info=True)
            return None

    @classmethod
    async def count(
            cls,
            filter_by: Optional[Dict] = None,
            **kwargs,
    ) -> int:
        """Count documents matching the filter."""
        try:
            query = filter_by or {}
            query.update(kwargs)
            return await cls.collection.count_documents(query)
        except Exception as e:
            logger.error(f"Error counting documents: {str(e)}", exc_info=True)
            return 0

    @classmethod
    async def is_unique(
            cls,
            field_name: str,
            value: Optional[Union[str, int]],
            exclude_id: Optional[Union[str, ObjectId]] = None,
            case_sensitive: bool = False,
            trim_spaces: bool = True
    ) -> bool:
        """
        Проверка уникальности значения поля с возможностью:
        - исключения текущего документа
        - игнорирования регистра (только для строк)
        - обрезки пробелов по краям (только для строк)

        Args:
            field_name: Название поля для проверки
            value: Значение для проверки (str или int)
            exclude_id: ID документа, который следует исключить из проверки
            case_sensitive: Учитывать ли регистр (для строк)
            trim_spaces: Обрезать ли пробелы (для строк)

        Returns:
            True если значение уникально
        """
        try:
            # Обработка None значения
            if value is None:
                query_value = None
            else:
                # Приводим к строке и обрабатываем пробелы для строковых значений
                if isinstance(value, str):
                    query_value = value.strip() if trim_spaces else value
                else:
                    # Для чисел и других типов оставляем как есть
                    query_value = value

            # Формируем запрос с учетом типа значения
            if isinstance(query_value, str) and not case_sensitive:
                query = {
                    field_name: {
                        "$regex": f"^{re.escape(query_value)}$",
                        "$options": "i"
                    }
                }
            else:
                query = {field_name: query_value}

            # Добавляем исключение для текущего документа
            if exclude_id is not None:
                if isinstance(exclude_id, str):
                    exclude_id = ObjectId(exclude_id)
                query["_id"] = {"$ne": exclude_id}

            existing = await cls.collection.find_one(query)
            return existing is None

        except Exception as e:
            logger.error(f"Error checking uniqueness: {str(e)}", exc_info=True)
            return False

    @classmethod
    async def soft_delete(
            cls,
            object_id: Union[str, ObjectId],
            deleted_at_field: str = "deletedAt",
    ) -> Optional[Dict[str, Any]]:
        """
        Софт-удаление: помечает документ полем deletedAt (или указанным полем).
        Возвращает обновлённый документ или None при ошибке.
        """
        try:
            if isinstance(object_id, str):
                object_id = ObjectId(object_id)
            update_data = {deleted_at_field: datetime.now(timezone.utc)}
            result = await cls.update_by_id(
                object_id=object_id,
                update_data=update_data,
                upsert=False,
                return_document=True,
            )
            return result
        except Exception as e:
            logger.error(f"Error soft-deleting document: {str(e)}", exc_info=True)
            return None
