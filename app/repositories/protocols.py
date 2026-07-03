from typing import Any, Optional, Protocol, runtime_checkable

from bson import ObjectId

from app.core.pagination import PaginatedResponse


@runtime_checkable
class EntityRepositoryProtocol(Protocol):
    async def find_one(
            self,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            **kwargs,
    ) -> Optional[dict[str, Any]]: ...

    async def find_many(
            self,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
            **kwargs,
    ) -> list[dict[str, Any]]: ...

    async def find_paginated(
            self,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
            **kwargs,
    ) -> PaginatedResponse: ...

    async def aggregate(self, pipeline: list[dict]) -> list[dict[str, Any]]: ...

    async def create(self, document: dict) -> Optional[dict[str, Any]]: ...

    async def update_by_id(
            self,
            object_id: str | ObjectId,
            update_data: dict,
            upsert: bool = False,
    ) -> Optional[dict[str, Any]]: ...

    async def update_many(self, filter_by: dict, update_data: dict, upsert: bool = False) -> int: ...

    async def delete_one(self, filter_by: dict, **kwargs) -> bool: ...

    async def delete_many(self, filter_by: dict, **kwargs) -> int: ...

    async def create_many(
            self,
            documents: list[dict],
            ordered: bool = True,
    ) -> Optional[list[ObjectId]]: ...

    async def count(self, filter_by: Optional[dict] = None, **kwargs) -> int: ...

    async def is_unique(
            self,
            field_name: str,
            value: Optional[str | int],
            exclude_id: Optional[str | ObjectId] = None,
            case_sensitive: bool = False,
            trim_spaces: bool = True,
    ) -> bool: ...

    async def soft_delete(
            self,
            object_id: str | ObjectId,
            deleted_at_field: str = "deletedAt",
    ) -> Optional[dict[str, Any]]: ...


@runtime_checkable
class DealsRepositoryProtocol(EntityRepositoryProtocol, Protocol):
    async def find_paginated_with_relations(
            self,
            filter_by: Optional[dict] = None,
            projection: Optional[dict] = None,
            skip: int = 0,
            limit: int = 100,
            sort: Optional[list[tuple]] = None,
            include_relations: bool = False,
            **kwargs,
    ) -> PaginatedResponse: ...
