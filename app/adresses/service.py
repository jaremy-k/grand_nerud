from bson import ObjectId

from app.adresses.repository import adresses_repository
from app.adresses.shemas import SAdressesAdd
from app.core.base_entity_service import BaseEntityService
from app.core.object_id import parse_object_id
from app.deals.repository import deals_repository
from app.exceptions import InternalError, NotFoundError


class AdressesService(BaseEntityService):
    repository = adresses_repository
    not_found_detail = "Адрес не найден"
    conflict_detail = "Невозможно удалить адрес — имеются связанные сделки"
    entity_label = "Адрес"

    @classmethod
    async def list_entities(cls, filters, include_deleted: bool = False) -> list[dict]:
        query = filters.model_dump(exclude_none=True)
        if not include_deleted:
            query["deletedAt"] = None
        return await cls.repository.find_many(**query)

    @classmethod
    async def create(cls, data: SAdressesAdd) -> dict:
        result = await cls.repository.create(data.model_dump(exclude_none=True))
        if not result:
            raise InternalError("Не удалось создать адрес")
        return result

    @classmethod
    async def update(cls, entity_id: str, data: SAdressesAdd) -> dict:
        parse_object_id(entity_id)
        existing = await cls.repository.find_one(_id=ObjectId(entity_id))
        if not existing:
            raise NotFoundError(cls.not_found_detail)

        result = await cls.repository.update_by_id(
            object_id=entity_id,
            update_data=data.model_dump(exclude_none=True),
        )
        if not result:
            raise InternalError("Не удалось обновить адрес")
        return result

    @classmethod
    async def has_dependencies(cls, entity_id: str) -> bool:
        oid = ObjectId(entity_id)
        count = await deals_repository.count({
            "$or": [{"shippingAddressId": oid}, {"deliveryAddressId": oid}],
            "deletedAt": None,
        })
        return count > 0
