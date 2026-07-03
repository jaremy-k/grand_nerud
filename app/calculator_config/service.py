from datetime import datetime

from app.calculator_config.models import CalculatorConfig
from app.calculator_config import repository as config_repo
from app.calculator_config.shemas import CalculatorConfigDto, CalculatorConfigUpdate
from app.core.mongo_utils import serialize_mongo_doc
from app.exceptions import InternalError


class CalculatorConfigService:
    _cache: CalculatorConfig | None = None

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._cache = None

    @classmethod
    async def get_config(cls) -> CalculatorConfig:
        if cls._cache is not None:
            return cls._cache
        doc = await config_repo.find_config()
        cls._cache = CalculatorConfig.from_document(doc)
        return cls._cache

    @classmethod
    async def get_dto(cls) -> CalculatorConfigDto:
        doc = await config_repo.find_config()
        if not doc:
            config = CalculatorConfig()
            return CalculatorConfigDto(
                ndsPercent=config.nds_percent,
                defaultManagerShare=config.default_manager_share,
                cashPaymentMethod=config.cash_payment_method,
                nonCashPaymentMethod=config.non_cash_payment_method,
            )
        serialized = serialize_mongo_doc(doc)
        return CalculatorConfigDto.model_validate(serialized)

    @classmethod
    async def update(cls, data: CalculatorConfigUpdate) -> CalculatorConfigDto:
        payload = data.model_dump(exclude_none=True)
        if not payload:
            return await cls.get_dto()

        payload["updatedAt"] = datetime.now()
        result = await config_repo.upsert_config(payload)
        if not result:
            raise InternalError("Не удалось обновить настройки калькулятора")

        cls.invalidate_cache()
        return await cls.get_dto()
