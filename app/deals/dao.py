from typing import Optional

from bson import ObjectId

from app.core.mongo_utils import convert_objectids_to_str
from app.dao.base import MongoDAO
from app.database import database_mongo
from app.deals.pipelines import get_deal_relation_lookups
from app.deals.shemas import PaginatedResponse
from app.logger import logger


class DealsDAO(MongoDAO):
    collection = database_mongo["deals"]

    @classmethod
    async def find_paginated_with_relations(
            cls,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
            include_relations: bool = False,
            **kwargs,
    ) -> PaginatedResponse:
        try:
            query = filter_by or {}
            query.update(kwargs)

            if include_relations:
                return await cls._find_paginated_with_relations(
                    query=query, skip=skip, limit=limit, sort=sort,
                )
            return await cls._find_paginated_simple(
                query=query, projection=projection, skip=skip, limit=limit, sort=sort,
            )
        except Exception as e:
            logger.error(f"Error finding paginated documents: {e}", exc_info=True)
            return PaginatedResponse(
                items=[], total=0, page=1, page_size=limit,
                total_pages=0, has_next=False, has_prev=False,
            )

    @classmethod
    async def _find_paginated_simple(
            cls,
            query: dict,
            projection: Optional[dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
    ) -> PaginatedResponse:
        total = await cls.collection.count_documents(query)
        cursor = cls.collection.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)
        items = convert_objectids_to_str([doc async for doc in cursor])
        return cls._build_paginated_response(items, total, skip, limit)

    @classmethod
    async def _find_paginated_with_relations(
            cls,
            query: dict,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
    ) -> PaginatedResponse:
        total = await cls.collection.count_documents(query)
        pipeline = [{"$match": query}]
        if sort:
            pipeline.append({"$sort": dict(sort)})
        pipeline.extend([{"$skip": skip}, {"$limit": limit}])
        pipeline.extend(get_deal_relation_lookups())
        items = convert_objectids_to_str(await cls.aggregate(pipeline))
        return cls._build_paginated_response(items, total, skip, limit)

    @staticmethod
    def _build_paginated_response(items, total: int, skip: int, limit: int) -> PaginatedResponse:
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
