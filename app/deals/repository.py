from typing import Optional
import re

from bson import ObjectId
from pymongo.errors import PyMongoError

from app.core.mongo_utils import convert_objectids_to_str
from app.core.pagination import PaginatedResponse
from app.database import database_mongo
from app.deals.pipelines import get_deal_relation_lookups
from app.exceptions import InternalError
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
            search: str = "",
            **kwargs,
    ) -> PaginatedResponse:
        try:
            query = dict(filter_by or {})
            query.update(kwargs)
            if search:
                return await self._find_paginated_search(query, search, skip, limit, sort, include_relations)
            if include_relations:
                return await self._find_paginated_with_relations(query, skip, limit, sort)
            return await self._find_paginated_simple(query, projection, skip, limit, sort)
        except PyMongoError as e:
            logger.error("Error finding paginated documents: %s", e, exc_info=True)
            raise InternalError("Не удалось загрузить сделки") from e

    async def _find_paginated_search(self, query, search, skip, limit, sort, include_relations):
        # Search related names before pagination; count and items share the same match.
        pattern = {"$regex": re.escape(search), "$options": "i"}
        fields = ["_searchCustomer.name", "_searchCustomer.abbreviatedName", "_searchCustomer.inn",
                  "_searchProvider.name", "_searchProvider.abbreviatedName", "_searchProvider.inn",
                  "_searchMaterial.name"]
        matches = [{field: pattern} for field in fields]
        if ObjectId.is_valid(search):
            matches.append({"_id": ObjectId(search)})
        pipeline = [{"$match": query}]
        for source, field, alias in (
            ("companies", "customerId", "_searchCustomer"),
            ("companies", "providerId", "_searchProvider"),
            ("materials", "materialId", "_searchMaterial"),
        ):
            pipeline.append({"$lookup": {
                "from": source, "localField": field, "foreignField": "_id", "as": alias,
                "pipeline": [{"$project": {"name": 1, "abbreviatedName": 1, "inn": 1}}],
            }})
        pipeline.append({"$match": {"$or": matches}})
        items = [{"$sort": dict(sort or [("createdAt", -1), ("_id", -1)])},
                 {"$skip": skip}, {"$limit": limit},
                 {"$project": {"_searchCustomer": 0, "_searchProvider": 0, "_searchMaterial": 0}}]
        if include_relations:
            items.extend(get_deal_relation_lookups())
        pipeline.append({"$facet": {"items": items, "total": [{"$count": "value"}]}})
        result = await self._collection.aggregate(pipeline).to_list(length=1)
        if len(result) != 1 or "items" not in result[0] or "total" not in result[0]:
            raise InternalError("Не удалось загрузить сделки")
        total = result[0]["total"][0]["value"] if result[0]["total"] else 0
        return self._build_paginated_response(convert_objectids_to_str(result[0]["items"]), total, skip, limit)

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
        items = convert_objectids_to_str(await self._collection.aggregate(pipeline).to_list(length=None))
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
