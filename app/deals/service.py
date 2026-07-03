from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import HTTPException, status

from app.core.mongo_utils import serialize_mongo_doc, serialize_mongo_docs
from app.deals.dao import DealsDAO
from app.deals.pipelines import build_deal_relations_pipeline
from app.deals.shemas import PaginatedResponse, PaginationParams, SDeals, SDealsAdd
from app.logger import logger
from app.users.shemas import SUsersGet
from fastapi import HTTPException, status


class DealsService:
    @classmethod
    async def list_deals(
            cls,
            filters: SDeals,
            pagination: PaginationParams,
            user: SUsersGet,
            sort_by: Optional[str] = None,
            sort_order: str = "asc",
            include_relations: bool = False,
            include_deleted: bool = False,
    ) -> PaginatedResponse:
        if not user.admin:
            filters.userId = ObjectId(user.id)

        filter_data = filters.model_dump(exclude_none=True)
        if not include_deleted:
            filter_data["deletedAt"] = None

        sort = None
        if sort_by:
            order = 1 if sort_order == "asc" else -1
            sort = [(sort_by, order)]

        return await DealsDAO.find_paginated_with_relations(
            filter_by=filter_data,
            skip=pagination.skip,
            limit=pagination.limit,
            sort=sort,
            include_relations=include_relations,
        )

    @classmethod
    async def list_with_relations(cls, filters: SDeals) -> list[dict]:
        match_filter = filters.model_dump(exclude_none=True)
        if "deletedAt" not in match_filter:
            match_filter["deletedAt"] = None
        pipeline = build_deal_relations_pipeline(match_filter=match_filter)
        result = await DealsDAO.aggregate(pipeline)
        return serialize_mongo_docs(result)

    @classmethod
    async def get_with_relations(cls, deal_id: str) -> dict:
        pipeline = build_deal_relations_pipeline(deal_id=deal_id)
        result = await DealsDAO.aggregate(pipeline)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сделка не найдена")
        return serialize_mongo_doc(result[0])

    @classmethod
    async def create(cls, data: SDealsAdd, user: SUsersGet) -> dict:
        data.userId = ObjectId(user.id)
        data.createdAt = datetime.now()
        result = await DealsDAO.add(document=data.model_dump(exclude_none=True))
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать сделку",
            )
        return result

    @classmethod
    async def update(cls, deal_id: str, data: SDealsAdd) -> dict:
        existing = await DealsDAO.find_one_or_none(_id=ObjectId(deal_id))
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сделка не найдена")

        update_data = data.model_dump(exclude_none=True)
        result = await DealsDAO.update_by_id(object_id=deal_id, update_data=update_data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить сделку",
            )
        logger.info("Deal updated: id=%s, changes=%s", deal_id, list(update_data.keys()))
        return result

    @classmethod
    async def soft_delete(cls, deal_id: str) -> dict:
        existing = await DealsDAO.find_one_or_none(_id=ObjectId(deal_id))
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сделка не найдена")

        result = await DealsDAO.soft_delete(deal_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось удалить сделку",
            )
        return result
