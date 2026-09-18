from datetime import datetime, timezone

from bson import ObjectId

from app.companies.repository import companies_repository
from app.company_materials.repository import company_materials_repository
from app.company_materials.shemas import SCompanyMaterialInput
from app.core.base_entity_service import BaseEntityService
from app.core.mongo_utils import serialize_mongo_doc, serialize_mongo_docs
from app.core.object_id import parse_object_id
from app.exceptions import ConflictError, InternalError, NotFoundError, ValidationError
from app.materials.repository import materials_repository


class CompanyMaterialsService(BaseEntityService):
    repository = company_materials_repository
    not_found_detail = "Материал компании не найден"

    @classmethod
    async def _validate_relations(cls, company_id: ObjectId, material_id: ObjectId) -> None:
        company = await companies_repository.find_one(_id=company_id, deletedAt=None)
        if not company:
            raise NotFoundError("Компания не найдена")

        material = await materials_repository.find_one(_id=material_id, deletedAt=None)
        if not material:
            raise NotFoundError("Материал не найден")

    @classmethod
    async def _ensure_unique(
            cls,
            company_id: ObjectId,
            material_id: ObjectId,
            exclude_id: str | None = None,
    ) -> None:
        query = {
            "companyId": company_id,
            "materialId": material_id,
            "deletedAt": None,
        }
        if exclude_id:
            query["_id"] = {"$ne": parse_object_id(exclude_id)}
        if await cls.repository.find_one(filter_by=query):
            raise ConflictError("Этот материал уже добавлен компании")

    @staticmethod
    def _relations_pipeline(match: dict) -> list[dict]:
        return [
            {"$match": match},
            {"$lookup": {
                "from": "companies",
                "localField": "companyId",
                "foreignField": "_id",
                "as": "company",
            }},
            {"$lookup": {
                "from": "materials",
                "localField": "materialId",
                "foreignField": "_id",
                "as": "material",
            }},
            {"$addFields": {
                "company": {"$arrayElemAt": ["$company", 0]},
                "material": {"$arrayElemAt": ["$material", 0]},
            }},
            {"$sort": {"createdAt": -1}},
        ]

    @classmethod
    async def list_with_relations(
            cls,
            company_id: str | None = None,
            material_id: str | None = None,
            include_deleted: bool = False,
    ) -> list[dict]:
        match = {}
        if company_id:
            match["companyId"] = parse_object_id(company_id, "companyId")
        if material_id:
            match["materialId"] = parse_object_id(material_id, "materialId")
        if not include_deleted:
            match["deletedAt"] = None
        result = await cls.repository.aggregate(cls._relations_pipeline(match))
        return serialize_mongo_docs(result)

    @classmethod
    async def get_with_relations(cls, entity_id: str) -> dict:
        oid = parse_object_id(entity_id)
        result = await cls.repository.aggregate(cls._relations_pipeline({"_id": oid}))
        if not result:
            raise NotFoundError(cls.not_found_detail)
        return serialize_mongo_doc(result[0])

    @classmethod
    async def create(cls, data: SCompanyMaterialInput) -> dict:
        payload = data.model_dump(exclude_none=True)
        company_id = payload.get("companyId")
        material_id = payload.get("materialId")
        if company_id is None or material_id is None or payload.get("price") is None or not payload.get("unit"):
            raise ValidationError("Необходимо указать компанию, материал, цену и единицу измерения")

        await cls._validate_relations(company_id, material_id)
        await cls._ensure_unique(company_id, material_id)
        payload["createdAt"] = datetime.now(timezone.utc)
        payload["deletedAt"] = None
        result = await cls.repository.create(payload)
        if not result:
            raise InternalError("Не удалось добавить материал компании")
        return result

    @classmethod
    async def update(cls, entity_id: str, data: SCompanyMaterialInput) -> dict:
        oid = parse_object_id(entity_id)
        existing = await cls.repository.find_one(_id=oid, deletedAt=None)
        if not existing:
            raise NotFoundError(cls.not_found_detail)

        payload = data.model_dump(exclude_none=True)
        company_id = payload.get("companyId", existing["companyId"])
        material_id = payload.get("materialId", existing["materialId"])
        await cls._validate_relations(company_id, material_id)
        await cls._ensure_unique(company_id, material_id, exclude_id=entity_id)
        payload["updatedAt"] = datetime.now(timezone.utc)
        result = await cls.repository.update_by_id(entity_id, payload)
        if not result:
            raise InternalError("Не удалось обновить материал компании")
        return result
