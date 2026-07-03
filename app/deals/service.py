from datetime import datetime
from typing import Optional

from bson import ObjectId

from app.calculation_rules.service import CalculationRulesService
from app.calculator_config.service import CalculatorConfigService
from app.core.mongo_utils import serialize_mongo_doc, serialize_mongo_docs
from app.core.object_id import parse_object_id
from app.core.pagination import PaginatedResponse, PaginationParams
from app.deals.calculator import get_manager_share
from app.deals.pipelines import build_deal_relations_pipeline
from app.deals.repository import deals_repository
from app.deals.shemas import SDeals, SDealsInput, SDealsPreviewInput, SDealsPreviewResult
from app.exceptions import ForbiddenError, InternalError, NotFoundError, ValidationError
from app.logger import logger
from app.repositories.protocols import DealsRepositoryProtocol
from app.users.shemas import SUsersGet

_REQUIRED_CREATE_FIELDS = ("serviceId", "customerId", "stageId", "materialId")


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
    def _validate_create(cls, data: SDealsInput) -> None:
        payload = data.model_dump(exclude_none=True)
        missing = [field for field in _REQUIRED_CREATE_FIELDS if not payload.get(field)]
        if missing:
            raise ValidationError("Необходимо заполнить все обязательные поля")

    @classmethod
    def _normalize_lists(cls, data: dict) -> dict:
        if data.get("addExpenses") is not None:
            data["addExpenses"] = [
                item if isinstance(item, dict) else item.model_dump()
                for item in data["addExpenses"]
            ]
        if data.get("deliveredQuantity") is not None:
            data["deliveredQuantity"] = [
                item if isinstance(item, dict) else item.model_dump()
                for item in data["deliveredQuantity"]
            ]
        return data

    @classmethod
    def _resolve_profit(cls, deal: dict, user: SUsersGet | None) -> dict | None:
        deal_user = deal.get("user")
        if isinstance(deal_user, dict) and deal_user.get("profit"):
            return deal_user["profit"]
        if user:
            return user.profit
        return None

    @classmethod
    def _rule_id_from_deal(cls, deal: dict) -> str | None:
        rule_id = deal.get("calculationRuleId")
        if rule_id is None:
            return None
        return str(rule_id)

    @classmethod
    def _stored_nds_percent(cls, deal: dict) -> float | None:
        value = deal.get("ndsPercent")
        if value is None:
            return None
        return float(value)

    @classmethod
    async def _compute_stored(
            cls,
            deal_data: dict,
            user: SUsersGet,
            stored_nds_percent: float | None = None,
            rule_id: str | None = None,
    ) -> tuple[dict, str, int]:
        config = await CalculatorConfigService.get_config()
        return await CalculationRulesService.compute_stored_deal_fields(
            deal_data=deal_data,
            user_profit=user.profit,
            config=config,
            stored_nds_percent=stored_nds_percent,
            rule_id=rule_id,
        )

    @classmethod
    async def _enrich_response(cls, deal: dict, user: SUsersGet | None = None) -> dict:
        config = await CalculatorConfigService.get_config()
        profit = cls._resolve_profit(deal, user)
        computed, _, _ = await CalculationRulesService.compute_deal(
            deal_data=deal,
            user_profit=profit,
            config=config,
            stored_nds_percent=cls._stored_nds_percent(deal),
            rule_id=cls._rule_id_from_deal(deal),
        )
        computed["managerShare"] = get_manager_share(profit, deal.get("paymentMethod"), config)
        return {**deal, **computed}

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

        result = await cls.repository.find_paginated_with_relations(
            filter_by=filter_data,
            skip=pagination.skip,
            limit=pagination.limit,
            sort=sort,
            include_relations=include_relations,
        )
        enriched_items = []
        for item in result.items:
            enriched_items.append(await cls._enrich_response(item, user))
        result.items = enriched_items
        return result

    @classmethod
    async def list_with_relations(cls, filters: SDeals, user: SUsersGet) -> list[dict]:
        if not user.admin:
            filters.userId = ObjectId(user.id)
        match_filter = filters.model_dump(exclude_none=True)
        if "deletedAt" not in match_filter:
            match_filter["deletedAt"] = None
        pipeline = build_deal_relations_pipeline(match_filter=match_filter)
        result = await cls.repository.aggregate(pipeline)
        docs = serialize_mongo_docs(result)
        enriched = []
        for doc in docs:
            enriched.append(await cls._enrich_response(doc, user))
        return enriched

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
        doc = serialize_mongo_doc(result[0])
        return await cls._enrich_response(doc, user)

    @classmethod
    async def preview(cls, data: SDealsPreviewInput, user: SUsersGet) -> SDealsPreviewResult:
        deal_data = {
            "quantity": data.quantity,
            "amountPurchaseUnit": data.amountPurchaseUnit,
            "amountSalesUnit": data.amountSalesUnit,
            "amountDelivery": data.amountDelivery,
            "paymentMethod": data.paymentMethod,
            "addExpenses": [item.model_dump() for item in (data.addExpenses or [])],
            "deliveredQuantity": [item.model_dump() for item in (data.deliveredQuantity or [])],
        }
        config = await CalculatorConfigService.get_config()
        computed, _, _ = await CalculationRulesService.compute_deal(
            deal_data=deal_data,
            user_profit=user.profit,
            config=config,
            stored_nds_percent=None,
            rule_id=None,
        )
        manager_share = get_manager_share(user.profit, data.paymentMethod, config)
        return SDealsPreviewResult(
            taxAmount=float(computed.get("ndsAmount") or 0),
            companyProfit=float(computed.get("companyProfit") or 0),
            managerProfit=float(computed.get("managerProfit") or 0),
            amountPurchaseTotal=float(computed.get("amountPurchaseTotal") or 0),
            amountSalesTotal=float(computed.get("amountSalesTotal") or 0),
            actualCompanyProfit=float(computed.get("actualCompanyProfit") or 0),
            actualAmountSalesTotal=float(computed.get("actualAmountSalesTotal") or 0),
            actualAmountPurchaseTotal=float(computed.get("actualAmountPurchaseTotal") or 0),
            totalDeliveredQuantity=float(computed.get("totalDeliveredQuantity") or 0),
            ndsPercent=float(computed.get("ndsPercent") or 0),
            managerShare=manager_share,
            totalAmount=float(computed.get("totalAmount") or 0),
        )

    @classmethod
    async def create(cls, data: SDealsInput, user: SUsersGet) -> dict:
        cls._validate_create(data)
        payload = cls._normalize_lists(data.model_dump(exclude_none=True))
        stored, rule_id, rule_version = await cls._compute_stored(payload, user)
        payload = {
            **payload,
            **stored,
            "calculationRuleId": ObjectId(rule_id),
            "calculationRuleVersion": rule_version,
        }
        payload["userId"] = ObjectId(user.id)
        payload["createdAt"] = datetime.now()
        result = await cls.repository.create(payload)
        if not result:
            raise InternalError("Не удалось создать сделку")
        return await cls._enrich_response(result, user)

    @classmethod
    def _calculation_source(cls, deal: dict) -> dict:
        return {
            "quantity": deal.get("quantity"),
            "amountPurchaseUnit": deal.get("amountPurchaseUnit"),
            "amountSalesUnit": deal.get("amountSalesUnit"),
            "amountDelivery": deal.get("amountDelivery"),
            "paymentMethod": deal.get("paymentMethod"),
            "addExpenses": deal.get("addExpenses"),
            "deliveredQuantity": deal.get("deliveredQuantity"),
        }

    @classmethod
    async def update(cls, deal_id: str, data: SDealsInput, user: SUsersGet) -> dict:
        parse_object_id(deal_id, "deal_id")
        existing = await cls.repository.find_one(_id=ObjectId(deal_id), deletedAt=None)
        if not existing:
            raise NotFoundError("Сделка не найдена")
        cls._ensure_access(existing, user)

        calc_source = cls._normalize_lists({**cls._calculation_source(existing), **payload})
        stored, rule_id, rule_version = await cls._compute_stored(
            calc_source,
            user,
            stored_nds_percent=cls._stored_nds_percent(existing),
            rule_id=cls._rule_id_from_deal(existing),
        )
        payload = {
            **payload,
            **stored,
            "calculationRuleId": ObjectId(rule_id),
            "calculationRuleVersion": rule_version,
            "updatedAt": datetime.now(),
        }
        result = await cls.repository.update_by_id(object_id=deal_id, update_data=payload)
        if not result:
            raise InternalError("Не удалось обновить сделку")
        logger.info("Deal updated: id=%s, changes=%s", deal_id, list(payload.keys()))
        return await cls._enrich_response(result, user)

    @classmethod
    async def update_stage(cls, deal_id: str, stage_id: str, user: SUsersGet) -> dict:
        parse_object_id(deal_id, "deal_id")
        parse_object_id(stage_id, "stageId")
        existing = await cls.repository.find_one(_id=ObjectId(deal_id), deletedAt=None)
        if not existing:
            raise NotFoundError("Сделка не найдена")
        cls._ensure_access(existing, user)

        result = await cls.repository.update_by_id(
            object_id=deal_id,
            update_data={
                "stageId": ObjectId(stage_id),
                "updatedAt": datetime.now(),
            },
        )
        if not result:
            raise InternalError("Не удалось обновить этап сделки")
        return await cls._enrich_response(result, user)

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
