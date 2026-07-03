from bson import ObjectId

from app.core.named_entity_service import NamedEntityService
from app.deals.repository import deals_repository
from app.materials.repository import materials_repository
from app.materials.shemas import SMaterials, SMaterialsAdd


class MaterialsService(NamedEntityService):
    repository = materials_repository
    not_found_detail = "Материал не найден"
    conflict_detail = "Невозможно удалить материал — имеются связанные объекты"
    entity_label = "Материал"
    default_sort = [("name", 1)]

    @classmethod
    async def list_materials(cls, filters: SMaterials, include_deleted: bool = False) -> list[dict]:
        return await cls.list_entities(filters, include_deleted=include_deleted)

    @classmethod
    async def has_dependencies(cls, material_id: str) -> bool:
        count = await deals_repository.count({"materialId": ObjectId(material_id), "deletedAt": None})
        return count > 0
