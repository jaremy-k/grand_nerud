from typing import Awaitable, Callable, Optional

from app.core.object_id import parse_object_id
from app.exceptions import ConflictError, InternalError, NotFoundError
from app.repositories.protocols import EntityRepositoryProtocol


class BaseEntityService:
    repository: EntityRepositoryProtocol
    not_found_detail: str = "Объект не найден"
    conflict_detail: str = "Невозможно удалить — имеются связанные объекты"

    @classmethod
    async def get_by_id(cls, entity_id: str) -> dict:
        oid = parse_object_id(entity_id)
        result = await cls.repository.find_one(_id=oid)
        if not result:
            raise NotFoundError(cls.not_found_detail)
        return result

    @classmethod
    async def soft_delete(
            cls,
            entity_id: str,
            check_dependencies: bool = True,
            dependency_checker: Optional[Callable[[str], Awaitable[bool]]] = None,
    ) -> dict:
        oid = parse_object_id(entity_id)
        entity = await cls.repository.find_one(_id=oid)
        if not entity:
            raise NotFoundError(cls.not_found_detail)

        if check_dependencies and dependency_checker and await dependency_checker(entity_id):
            raise ConflictError(cls.conflict_detail)

        result = await cls.repository.soft_delete(entity_id)
        if not result:
            raise InternalError("Не удалось удалить объект")
        return result
