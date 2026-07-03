from datetime import datetime
from typing import Optional

from bson import ObjectId

from app.core.mongo_utils import serialize_mongo_doc, serialize_mongo_docs
from app.core.object_id import parse_object_id
from app.core.pagination import PaginatedResponse, PaginationParams
from app.deals.pipelines import build_deal_relations_pipeline
from app.deals.repository import deals_repository
from app.deals.shemas import SDeals, SDealsAdd
from app.exceptions import ForbiddenError, InternalError, NotFoundError
from app.logger import logger
from app.repositories.protocols import DealsRepositoryProtocol
from app.users.shemas import SUsersGet


class DealsService:
    repository: DealsRepositoryProtocol = deals_repository

    @classmethod
    def _ensure_access(cls, deal: dict, user: SUsersGet) -> None:
        if user.admin:
            return
        deal_user_id = deal.get("userId")
        if deal_user_id is None or str(deal_user_id) != str(user.id):
            raise ForbiddenError()

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

        return await cls.repository.find_paginated_with_relations(
            filter_by=filter_data,
            skip=pagination.skip,
            limit=pagination.limit,
            sort=sort,
            include_relations=include_relations,
        )

    @classmethod
    async def list_with_relations(cls, filters: SDeals, user: SUsersGet) -> list[dict]:
        if not user.admin:
            filters.userId = ObjectId(user.id)
        match_filter = filters.model_dump(exclude_none=True)
        if "deletedAt" not in match_filter:
            match_filter["deletedAt"] = None
        pipeline = build_deal_relations_pipeline(match_filter=match_filter)
        result = await cls.repository.aggregate(pipeline)
        return serialize_mongo_docs(result)

    @classmethod
    async def get_with_relations(cls, deal_id: str, user: SUsersGet) -> dict:
        parse_object_id(deal_id, "deal_id")
        deal = await cls.repository.find_one(_id=ObjectId(deal_id), deletedAt=None)
        if not deal:
            raise NotFoundError("Сделка не найдена")
        cls._ensure_access(deal, user)

        pipeline = build_deal_relations_pipeline(deal_id=deal_id)
        result = await cls.repository.aggregate(pipeline)
        if not result:
            raise NotFoundError("Сделка не найдена")
        return serialize_mongo_doc(result[0])

    @classmethod
    async def create(cls, data: SDealsAdd, user: SUsersGet) -> dict:
        data.userId = ObjectId(user.id)
        data.createdAt = datetime.now()
        result = await cls.repository.create(data.model_dump(exclude_none=True))
        if not result:
            raise InternalError("Не удалось создать сделку")
        return result

    @classmethod
    async def update(cls, deal_id: str, data: SDealsAdd, user: SUsersGet) -> dict:
        parse_object_id(deal_id, "deal_id")
        existing = await cls.repository.find_one(_id=ObjectId(deal_id), deletedAt=None)
        if not existing:
            raise NotFoundError("Сделка не найдена")
        cls._ensure_access(existing, user)

        update_data = data.model_dump(exclude_none=True)
        result = await cls.repository.update_by_id(object_id=deal_id, update_data=update_data)
        if not result:
            raise InternalError("Не удалось обновить сделку")
        logger.info("Deal updated: id=%s, changes=%s", deal_id, list(update_data.keys()))
        return result

    @classmethod
    async def soft_delete(cls, deal_id: str, user: SUsersGet) -> dict:
        parse_object_id(deal_id, "deal_id")
        existing = await cls.repository.find_one(_id=ObjectId(deal_id), deletedAt=None)
        if not existing:
            raise NotFoundError("Сделка не найдена")
        cls._ensure_access(existing, user)

        result = await cls.repository.soft_delete(deal_id)
        if not result:
            raise InternalError("Не удалось удалить сделку")
        return result
