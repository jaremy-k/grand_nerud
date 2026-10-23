import re

from bson import ObjectId
from pydantic import ValidationError as PydanticValidationError

from app.companies.excel_import import CompanyExcelFormatError, parse_companies_excel
from app.companies.repository import companies_repository
from app.companies.pipelines import build_company_details_pipeline
from app.companies.shemas import CompanyRole, SCompanies, SCompaniesAdd, SCompaniesWithDetails, SCompanyPageQuery
from app.companies.page_pipeline import build_company_page_pipeline
from app.core.pagination import PaginatedResponse
from app.company_materials.repository import company_materials_repository
from app.core.base_entity_service import BaseEntityService
from app.core.mongo_utils import serialize_mongo_docs
from app.deals.repository import deals_repository
from app.exceptions import ConflictError, ExternalServiceError, InternalError, NotFoundError, ValidationError
from app.integrations import get_kontragentpro_client
from app.integrations.exceptions import IntegrationError
from app.leads.repository import leads_repository
from app.tasks.repository import tasks_repository
from app.users.shemas import SUsersGet


class CompaniesService(BaseEntityService):
    repository = companies_repository
    not_found_detail = "Компания не найдена"
    conflict_detail = "Невозможно удалить компанию — имеются связанные объекты"

    @classmethod
    async def list_page(cls, data: SCompanyPageQuery) -> PaginatedResponse:
        result = await cls.repository.read_page(build_company_page_pipeline(data))
        items = [SCompaniesWithDetails.model_validate(item).model_dump(by_alias=True, exclude_none=True, mode="json")
                 for item in serialize_mongo_docs(result["items"])]
        total = result["total"][0]["value"] if result["total"] else 0
        total_pages = (total + data.pageSize - 1) // data.pageSize
        return PaginatedResponse(items=items, total=total, page=data.page, page_size=data.pageSize,
                                 total_pages=total_pages, has_next=data.page < total_pages, has_prev=data.page > 1)

    @classmethod
    async def list_companies(
            cls,
            filters: SCompanies,
            include_deleted: bool = False,
            role: CompanyRole | None = None,
            include_details: bool = False,
            user_id: str | None = None,
            is_privileged: bool = False,
            city: str | None = None,
            administrative_district: str | None = None,
            district: str | None = None,
    ) -> list[dict]:
        query = filters.model_dump(exclude_none=True)
        if role:
            query["roles"] = role
        if not include_deleted:
            query["deletedAt"] = None
        has_geo_filter = bool(city or administrative_district or district)
        if include_details or has_geo_filter:
            if role is None:
                if include_details:
                    raise ValidationError("Для расширенного списка необходимо указать role")
                deal_user_id = None
            else:
                deal_user_id = None if is_privileged else ObjectId(user_id)
            pipeline = build_company_details_pipeline(
                query,
                role,
                deal_user_id,
                city=city,
                administrative_district=administrative_district,
                district=district,
                include_details=include_details,
            )
            return serialize_mongo_docs(await cls.repository.aggregate(pipeline))
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
    async def fetch_by_inn(cls, inn: int) -> dict:
        try:
            return await get_kontragentpro_client().get_company_by_inn(inn)
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

    @staticmethod
    def _merge_unique(existing: list | None, incoming: list | None) -> list:
        result = list(existing or [])
        seen = {str(value).casefold() for value in result}
        for value in incoming or []:
            key = str(value).casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @classmethod
    def _merge_contact_persons(cls, existing: list | None, incoming: list | None) -> list:
        result = [dict(contact) for contact in (existing or []) if isinstance(contact, dict)]
        for contact in incoming or []:
            contact = dict(contact)
            contact_inn = str(contact.get("inn") or "").strip()
            contact_name = str(contact.get("name") or "").strip().casefold()
            match = next((
                item for item in result
                if (
                    contact_inn
                    and str(item.get("inn") or "").strip() == contact_inn
                ) or (
                    str(item.get("name") or "").strip().casefold() == contact_name
                )
            ), None)
            if match is None:
                result.append(contact)
                continue
            for field in ("name", "inn", "position", "isPrimary", "comment"):
                if contact.get(field) not in (None, ""):
                    match[field] = contact[field]
            match["phones"] = cls._merge_unique(match.get("phones"), contact.get("phones"))
            match["emails"] = cls._merge_unique(match.get("emails"), contact.get("emails"))
        return result

    @classmethod
    def _build_import_update(cls, existing: dict, incoming: dict) -> dict:
        update: dict = {}
        for field in ("name", "source"):
            if incoming.get(field) not in (None, ""):
                update[field] = incoming[field]
        for field in ("phones", "emails", "websites", "segments", "roles"):
            update[field] = cls._merge_unique(existing.get(field), incoming.get(field))
        update["contactPersons"] = cls._merge_contact_persons(
            existing.get("contactPersons"),
            incoming.get("contactPersons"),
        )
        return {
            field: value
            for field, value in update.items()
            if existing.get(field) != value
        }

    @staticmethod
    def _pydantic_error_detail(exc: PydanticValidationError) -> str:
        errors = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", []))
            errors.append(f"{location}: {error['msg']}" if location else error["msg"])
        return "; ".join(errors)

    @classmethod
    async def import_excel(cls, content: bytes, role: CompanyRole | None = None,
                           create_leads: bool = False, user: SUsersGet | None = None) -> dict:
        try:
            rows, errors = parse_companies_excel(content, role=role)
        except CompanyExcelFormatError as exc:
            raise ValidationError(str(exc)) from exc
        if create_leads:
            from app.lead_stages.service import LeadStagesService
            from app.leads.service import LeadsService
            if user is None:
                raise ValidationError("Для создания лидов необходим ответственный")
            await LeadStagesService.get_by_kind("new")

        total_rows = len(rows) + len(errors)
        created = 0
        updated = 0
        skipped = 0
        leads_created = 0
        leads_skipped = 0
        for row in rows:
            try:
                incoming = SCompaniesAdd.model_validate(row.data)
            except PydanticValidationError as exc:
                errors.append({
                    "row": row.row_number,
                    "detail": cls._pydantic_error_detail(exc),
                })
                continue

            existing = await cls.find_by_inn(incoming.inn)
            if existing and existing.get("deletedAt") is not None:
                errors.append({"row": row.row_number, "detail": "Компания с этим ИНН находится в архиве"})
                continue
            if not existing:
                company = await cls.create(incoming)
                created += 1
            else:
                update_data = cls._build_import_update(
                    existing,
                    incoming.model_dump(exclude_none=True, mode="json"),
                )
                if not update_data:
                    skipped += 1
                    company = existing
                else:
                    company = await cls.update(str(existing["_id"]), SCompaniesAdd.model_validate(update_data))
                    updated += 1
            if create_leads:
                if await LeadsService.create_for_import(company, user):
                    leads_created += 1
                else:
                    leads_skipped += 1

        return {
            "totalRows": total_rows,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "leadsCreated": leads_created,
            "leadsSkipped": leads_skipped,
            "errors": errors,
        }

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
        deals_count = await deals_repository.count({
            "$or": [{"customerId": oid}, {"providerId": oid}],
            "deletedAt": None,
        })
        materials_count = await company_materials_repository.count({
            "companyId": oid,
            "deletedAt": None,
        })
        leads_count = await leads_repository.count({"companyId": oid, "deletedAt": None})
        tasks_count = await tasks_repository.count({"companyId": oid, "status": "open", "deletedAt": None})
        return any(count > 0 for count in (deals_count, materials_count, leads_count, tasks_count))
