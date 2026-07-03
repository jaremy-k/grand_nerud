from typing import Optional

from app.core.mongo_utils import convert_objectids_to_str
from app.core.pagination import PaginatedResponse
from app.database import database_mongo
from app.deals.pipelines import get_deal_relation_lookups
from app.logger import logger
from app.repositories.mongo import MongoRepository


class DealsRepository(MongoRepository):
    async def find_paginated_with_relations(
            self,
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
                return await self._find_paginated_with_relations(query, skip, limit, sort)
            return await self._find_paginated_simple(query, projection, skip, limit, sort)
        except Exception as e:
            logger.error("Error finding paginated documents: %s", e, exc_info=True)
            return PaginatedResponse(
                items=[], total=0, page=1, page_size=limit,
                total_pages=0, has_next=False, has_prev=False,
            )

    async def _find_paginated_simple(
            self,
            query: dict,
            projection: Optional[dict],
            skip: int,
            limit: int,
            sort: Optional[list[tuple]],
    ) -> PaginatedResponse:
        total = await self._collection.count_documents(query)
        cursor = self._collection.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)
        items = convert_objectids_to_str([doc async for doc in cursor])
        return self._build_paginated_response(items, total, skip, limit)

    async def _find_paginated_with_relations(
            self,
            query: dict,
            skip: int,
            limit: int,
            sort: Optional[list[tuple]],
    ) -> PaginatedResponse:
        total = await self._collection.count_documents(query)
        pipeline = [{"$match": query}]
        if sort:
            pipeline.append({"$sort": dict(sort)})
        pipeline.extend([{"$skip": skip}, {"$limit": limit}])
        pipeline.extend(get_deal_relation_lookups())
        items = convert_objectids_to_str(await self.aggregate(pipeline))
        return self._build_paginated_response(items, total, skip, limit)

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


deals_repository = DealsRepository(database_mongo["deals"])
