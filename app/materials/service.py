from bson import ObjectId
from fastapi import HTTPException, status

from app.core.base_entity_service import BaseEntityService
from app.deals.dao import DealsDAO
from app.materials.dao import MaterialsDAO
from app.materials.shemas import SMaterials, SMaterialsAdd


class MaterialsService(BaseEntityService):
    dao = MaterialsDAO
    not_found_detail = "Материал не найден"
    conflict_detail = "Невозможно удалить материал — имеются связанные объекты"

    @classmethod
    async def list_materials(cls, filters: SMaterials, include_deleted: bool = False) -> list[dict]:
        query = filters.model_dump(exclude_none=True)
        if not include_deleted:
            query["deletedAt"] = None
        return await cls.dao.find_all(**query, sort=[("name", 1)])

    @classmethod
    async def create(cls, data: SMaterialsAdd) -> dict:
        if not await cls.dao.is_unique(
                field_name="name",
                value=data.name,
                case_sensitive=False,
                trim_spaces=True,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Материал с таким именем уже существует",
            )
        result = await cls.dao.add(document=data.model_dump(exclude_none=True))
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать материал",
            )
        return result

    @classmethod
    async def update(cls, material_id: str, data: SMaterialsAdd) -> dict:
        existing = await cls.dao.find_one_or_none(_id=ObjectId(material_id))
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=cls.not_found_detail)

        update_data = data.model_dump(exclude_none=True)
        if "name" in update_data and not await cls.dao.is_unique(
                field_name="name",
                value=data.name,
                exclude_id=material_id,
                case_sensitive=False,
                trim_spaces=True,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Материал с таким именем уже существует",
            )

        result = await cls.dao.update_by_id(object_id=material_id, update_data=update_data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить материал",
            )
        return result

    @classmethod
    async def has_dependencies(cls, material_id: str) -> bool:
        count = await DealsDAO.count({"materialId": ObjectId(material_id), "deletedAt": None})
        return count > 0
