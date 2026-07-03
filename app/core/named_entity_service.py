from typing import Any

from bson import ObjectId
from pydantic import BaseModel

from app.core.base_entity_service import BaseEntityService
from app.core.object_id import parse_object_id
from app.deals.repository import deals_repository
from app.exceptions import ConflictError, InternalError, NotFoundError


class NamedEntityService(BaseEntityService):
    unique_field: str | None = "name"
    default_sort: list[tuple] | None = None
    entity_label: str = "Объект"

    @classmethod
    async def list_entities(
            cls,
            filters: BaseModel,
            include_deleted: bool = False,
    ) -> list[dict]:
        query = filters.model_dump(exclude_none=True)
        if not include_deleted:
            query["deletedAt"] = None
        kwargs: dict[str, Any] = dict(**query)
        if cls.default_sort:
            kwargs["sort"] = cls.default_sort
        return await cls.repository.find_many(**kwargs)

    @classmethod
    async def create(cls, data: BaseModel) -> dict:
        document = data.model_dump(exclude_none=True)
        if cls.unique_field and cls.unique_field in document:
            if not await cls.repository.is_unique(
                    field_name=cls.unique_field,
                    value=document[cls.unique_field],
                    case_sensitive=False,
                    trim_spaces=True,
            ):
                raise ConflictError(f"{cls.entity_label} с таким значением уже существует")
        result = await cls.repository.create(document)
        if not result:
            raise InternalError(f"Не удалось создать {cls.entity_label.lower()}")
        return result

    @classmethod
    async def update(cls, entity_id: str, data: BaseModel) -> dict:
        parse_object_id(entity_id)
        existing = await cls.repository.find_one(_id=ObjectId(entity_id))
        if not existing:
            raise NotFoundError(cls.not_found_detail)

        update_data = data.model_dump(exclude_none=True)
        if (
                cls.unique_field
                and cls.unique_field in update_data
                and not await cls.repository.is_unique(
                    field_name=cls.unique_field,
                    value=update_data[cls.unique_field],
                    exclude_id=entity_id,
                    case_sensitive=False,
                    trim_spaces=True,
                )
        ):
            raise ConflictError(f"{cls.entity_label} с таким значением уже существует")

        result = await cls.repository.update_by_id(object_id=entity_id, update_data=update_data)
        if not result:
            raise InternalError(f"Не удалось обновить {cls.entity_label.lower()}")
        return result

    @classmethod
    async def count_deal_dependencies(cls, field: str, entity_id: str) -> bool:
        count = await deals_repository.count({field: ObjectId(entity_id), "deletedAt": None})
        return count > 0
