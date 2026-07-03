from bson import ObjectId

from app.core.base_entity_service import BaseEntityService
from app.core.object_id import parse_object_id
from app.exceptions import ConflictError, ForbiddenError, InternalError, NotFoundError
from app.users.auth import get_password_hash
from app.users.repository import users_repository
from app.users.shemas import SUsersUpdate
from app.vehicles.repository import vehicles_repository
from app.vehicles.shemas import SVehiclesAdd


class VehiclesService(BaseEntityService):
    repository = vehicles_repository
    not_found_detail = "Транспорт не найден"
    conflict_detail = "Невозможно удалить транспорт — имеются связанные объекты"
    entity_label = "Транспорт"

    @classmethod
    async def list_entities(cls, filters, include_deleted: bool = False) -> list[dict]:
        query = filters.model_dump(exclude_none=True)
        if not include_deleted:
            query["deletedAt"] = None
        return await cls.repository.find_many(**query)

    @classmethod
    async def create(cls, data: SVehiclesAdd) -> dict:
        document = data.model_dump(exclude_none=True)
        if document.get("number") and document.get("region") is not None:
            existing = await cls.repository.find_one(
                number=document["number"],
                region=document["region"],
                deletedAt=None,
            )
            if existing:
                raise ConflictError("Транспорт с таким номером уже существует")
        result = await cls.repository.create(document)
        if not result:
            raise InternalError("Не удалось создать транспорт")
        return result

    @classmethod
    async def update(cls, entity_id: str, data: SVehiclesAdd) -> dict:
        parse_object_id(entity_id)
        existing = await cls.repository.find_one(_id=ObjectId(entity_id))
        if not existing:
            raise NotFoundError(cls.not_found_detail)

        result = await cls.repository.update_by_id(
            object_id=entity_id,
            update_data=data.model_dump(exclude_none=True),
        )
        if not result:
            raise InternalError("Не удалось обновить транспорт")
        return result

    @classmethod
    async def has_dependencies(cls, entity_id: str) -> bool:
        return False
