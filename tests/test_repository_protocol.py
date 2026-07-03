from bson import ObjectId

from app.deals.repository import deals_repository
from app.materials.repository import materials_repository
from app.repositories.mongo import MongoRepository
from app.repositories.protocols import DealsRepositoryProtocol, EntityRepositoryProtocol


def test_mongo_repository_satisfies_entity_protocol():
    repo = MongoRepository.__new__(MongoRepository)
    assert isinstance(repo, EntityRepositoryProtocol)


def test_materials_repository_satisfies_entity_protocol():
    assert isinstance(materials_repository, EntityRepositoryProtocol)


def test_deals_repository_satisfies_deals_protocol():
    assert isinstance(deals_repository, DealsRepositoryProtocol)


class InMemoryEntityRepository:
    def __init__(self):
        self._docs: dict[ObjectId, dict] = {}

    async def find_one(self, filter_by=None, projection=None, **kwargs):
        query = {**(filter_by or {}), **kwargs}
        for doc in self._docs.values():
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    async def find_many(self, filter_by=None, projection=None, skip=0, limit=100, sort=None, **kwargs):
        return []

    async def find_paginated(self, filter_by=None, projection=None, skip=0, limit=100, sort=None, **kwargs):
        from app.core.pagination import PaginatedResponse
        return PaginatedResponse(
            items=[], total=0, page=1, page_size=limit,
            total_pages=0, has_next=False, has_prev=False,
        )

    async def aggregate(self, pipeline):
        return []

    async def create(self, document):
        oid = ObjectId()
        doc = {**document, "_id": oid}
        self._docs[oid] = doc
        return doc

    async def update_by_id(self, object_id, update_data, upsert=False):
        oid = ObjectId(object_id) if isinstance(object_id, str) else object_id
        if oid not in self._docs:
            return None
        self._docs[oid].update(update_data)
        return self._docs[oid]

    async def update_many(self, filter_by, update_data, upsert=False):
        return 0

    async def delete_one(self, filter_by, **kwargs):
        return False

    async def delete_many(self, filter_by, **kwargs):
        return 0

    async def create_many(self, documents, ordered=True):
        return None

    async def count(self, filter_by=None, **kwargs):
        return 0

    async def is_unique(self, field_name, value, exclude_id=None, case_sensitive=False, trim_spaces=True):
        return True

    async def soft_delete(self, object_id, deleted_at_field="deletedAt"):
        from datetime import datetime, timezone
        return await self.update_by_id(object_id, {deleted_at_field: datetime.now(timezone.utc)})


def test_in_memory_repository_satisfies_protocol():
    assert isinstance(InMemoryEntityRepository(), EntityRepositoryProtocol)