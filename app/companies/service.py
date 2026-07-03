import re

from bson import ObjectId

from app.companies.repository import companies_repository
from app.companies.shemas import SCompanies, SCompaniesAdd
from app.core.base_entity_service import BaseEntityService
from app.deals.repository import deals_repository
from app.exceptions import ConflictError, ExternalServiceError, InternalError, NotFoundError
from app.integrations import get_fns_client
from app.integrations.exceptions import IntegrationError


class CompaniesService(BaseEntityService):
    repository = companies_repository
    not_found_detail = "Компания не найдена"
    conflict_detail = "Невозможно удалить компанию — имеются связанные объекты"

    @classmethod
    async def list_companies(cls, filters: SCompanies, include_deleted: bool = False) -> list[dict]:
        query = filters.model_dump(exclude_none=True)
        if not include_deleted:
            query["deletedAt"] = None
        return await cls.repository.find_many(**query)

    @classmethod
    async def find_by_inn(cls, inn: int | str) -> dict | None:
        value = str(inn).strip() if inn is not None else None
        if value is None:
            return None

        found = await cls.repository.find_one(filter_by={
            "inn": {"$regex": f"^{re.escape(value)}$", "$options": "i"},
        })
        if found:
            return found

        try:
            return await cls.repository.find_one(inn=int(value))
        except (ValueError, TypeError):
            return None

    @classmethod
    async def fetch_from_fns(cls, inn: int) -> dict:
        try:
            return await get_fns_client().get_company_by_inn(inn)
        except IntegrationError as e:
            raise ExternalServiceError(e.message) from e

    @classmethod
    async def create(cls, data: SCompaniesAdd) -> dict:
        if data.inn is not None and not await cls.repository.is_unique(
                field_name="inn",
                value=data.inn,
                case_sensitive=False,
                trim_spaces=True,
        ):
            existing = await cls.find_by_inn(data.inn)
            if existing:
                return existing

        result = await cls.repository.create(data.model_dump(exclude_none=True))
        if not result:
            raise InternalError("Не удалось создать компанию")
        return result

    @classmethod
    async def update(cls, company_id: str, data: SCompaniesAdd) -> dict:
        existing = await cls.repository.find_one(_id=ObjectId(company_id))
        if not existing:
            raise NotFoundError(cls.not_found_detail)

        update_data = data.model_dump(exclude_none=True)
        if "inn" in update_data and not await cls.repository.is_unique(
                field_name="inn",
                value=data.inn,
                exclude_id=company_id,
                case_sensitive=False,
                trim_spaces=True,
        ):
            raise ConflictError("Компания с таким ИНН уже существует")

        result = await cls.repository.update_by_id(object_id=company_id, update_data=update_data)
        if not result:
            raise InternalError("Не удалось обновить компанию")
        return result

    @classmethod
    async def has_dependencies(cls, company_id: str) -> bool:
        oid = ObjectId(company_id)
        count = await deals_repository.count({
            "$or": [{"customerId": oid}, {"providerId": oid}],
            "deletedAt": None,
        })
        return count > 0
