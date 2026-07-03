from typing import Awaitable, Callable, Optional

from bson import ObjectId
from fastapi import HTTPException, status

from app.dao.base import MongoDAO


class BaseEntityService:
    dao: type[MongoDAO]
    not_found_detail: str = "Объект не найден"
    conflict_detail: str = "Невозможно удалить — имеются связанные объекты"

    @classmethod
    async def get_by_id(cls, entity_id: str) -> dict:
        result = await cls.dao.find_one_or_none(_id=ObjectId(entity_id))
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=cls.not_found_detail)
        return result

    @classmethod
    async def soft_delete(
            cls,
            entity_id: str,
            check_dependencies: bool = True,
            dependency_checker: Optional[Callable[[str], Awaitable[bool]]] = None,
    ) -> dict:
        entity = await cls.dao.find_one_or_none(_id=ObjectId(entity_id))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=cls.not_found_detail)

        if check_dependencies and dependency_checker and await dependency_checker(entity_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=cls.conflict_detail)

        result = await cls.dao.soft_delete(entity_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось удалить объект",
            )
        return result
