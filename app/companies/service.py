import re

from bson import ObjectId
from fastapi import HTTPException, status

from app.companies.dao import CompaniesDAO
from app.companies.shemas import SCompanies, SCompaniesAdd
from app.core.base_entity_service import BaseEntityService
from app.deals.dao import DealsDAO
from app.exceptions import ExternalServiceException
from app.integrations import get_fns_client
from app.integrations.exceptions import IntegrationError


class CompaniesService(BaseEntityService):
    dao = CompaniesDAO
    not_found_detail = "Компания не найдена"
    conflict_detail = "Невозможно удалить компанию — имеются связанные объекты"

    @classmethod
    async def list_companies(cls, filters: SCompanies, include_deleted: bool = False) -> list[dict]:
        query = filters.model_dump(exclude_none=True)
        if not include_deleted:
            query["deletedAt"] = None
        return await cls.dao.find_all(**query)

    @classmethod
    async def find_by_inn(cls, inn: int | str) -> dict | None:
        value = str(inn).strip() if inn is not None else None
        if value is None:
            return None

        found = await cls.dao.find_one_or_none(filter_by={
            "inn": {"$regex": f"^{re.escape(value)}$", "$options": "i"},
        })
        if found:
            return found

        try:
            return await cls.dao.find_one_or_none(inn=int(value))
        except (ValueError, TypeError):
            return None

    @classmethod
    async def fetch_from_fns(cls, inn: int) -> dict:
        try:
            return await get_fns_client().get_company_by_inn(inn)
        except IntegrationError as e:
            raise ExternalServiceException(detail=e.message) from e

    @classmethod
    async def create(cls, data: SCompaniesAdd) -> dict:
        if data.inn is not None and not await cls.dao.is_unique(
                field_name="inn",
                value=data.inn,
                case_sensitive=False,
                trim_spaces=True,
        ):
            existing = await cls.find_by_inn(data.inn)
            if existing:
                return existing

        result = await cls.dao.add(document=data.model_dump(exclude_none=True))
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать компанию",
            )
        return result

    @classmethod
    async def update(cls, company_id: str, data: SCompaniesAdd) -> dict:
        existing = await cls.dao.find_one_or_none(_id=ObjectId(company_id))
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=cls.not_found_detail)

        update_data = data.model_dump(exclude_none=True)
        if "inn" in update_data and not await cls.dao.is_unique(
                field_name="inn",
                value=data.inn,
                exclude_id=company_id,
                case_sensitive=False,
                trim_spaces=True,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Компания с таким ИНН уже существует",
            )

        result = await cls.dao.update_by_id(object_id=company_id, update_data=update_data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить компанию",
            )
        return result

    @classmethod
    async def has_dependencies(cls, company_id: str) -> bool:
        oid = ObjectId(company_id)
        count = await DealsDAO.count({
            "$or": [{"customerId": oid}, {"providerId": oid}],
            "deletedAt": None,
        })
        return count > 0
