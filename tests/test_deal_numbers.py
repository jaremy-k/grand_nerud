import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

from app.deals.numbering import initialize_deal_numbers, next_deal_number
from app.deals.repository import DealsRepository
from app.deals.shemas import SDealsInput, SDealsWithRelations
from app.exceptions import InternalError


class Counter:
    def __init__(self, value=0):
        self.value = value
        self.lock = asyncio.Lock()

    async def find_one_and_update(self, query, update, **kwargs):
        assert query == {"_id": "deal_number"} and update == {"$inc": {"value": 1}}
        async with self.lock:
            self.value += 1
            value = self.value
        await asyncio.sleep(0)
        return {"value": value}

    async def update_one(self, query, update, **kwargs):
        self.value = max(self.value, update["$max"]["value"])


class Cursor:
    def __init__(self, values):
        self.values = list(values)

    def sort(self, field, direction=None):
        fields = field if isinstance(field, list) else [(field, direction)]
        for key, order in reversed(fields):
            self.values.sort(key=lambda item: str(item.get(key, "")) if key == "_id" else item.get(key, 0), reverse=order == -1)
        return self

    def limit(self, size):
        self.values = self.values[:size]
        return self

    async def to_list(self, **kwargs):
        return deepcopy(self.values)

    def __aiter__(self):
        async def iterate():
            for value in list(self.values):
                yield deepcopy(value)
        return iterate()


class Collection:
    def __init__(self, values=()):
        self.documents = {item["_id"]: deepcopy(item) for item in values}
        self.indexes = []

    async def find_one(self, query):
        await asyncio.sleep(0)
        return deepcopy(self.documents.get(query["_id"]))

    async def insert_one(self, document):
        if document["_id"] in self.documents:
            raise DuplicateKeyError("duplicate id")
        assert all(item.get("number") != document["number"] for item in self.documents.values())
        self.documents[document["_id"]] = deepcopy(document)

    async def create_index(self, field, **options):
        self.indexes.append((field, options))

    def find(self, query):
        values = list(self.documents.values())
        if "numberSequence" in query:
            values = [item for item in values if isinstance(item.get("numberSequence"), int)]
        else:
            values = [item for item in values if not item.get("number")]
        return Cursor(values)

    async def update_one(self, query, update):
        doc = self.documents[query["_id"]]
        if not doc.get("number"):
            doc.update(update["$set"])


def test_concurrent_deals_get_unique_server_numbers():
    async def run():
        counters, deals = Counter(), Collection()
        repo = DealsRepository(deals, counters)
        results = await asyncio.gather(*(repo.create({"customerId": ObjectId()}) for _ in range(40)))
        assert {item["numberSequence"] for item in results} == set(range(1, 41))
        assert len({item["number"] for item in results}) == 40
        assert results[0]["number"].startswith("СД-")
    asyncio.run(run())


def test_retry_of_same_lead_conversion_does_not_renumber_deal():
    async def run():
        counters, collection = Counter(), Collection()
        repo = DealsRepository(collection, counters)
        identifier = ObjectId()
        first, second = await asyncio.gather(repo.create({"_id": identifier}), repo.create({"_id": identifier}))
        assert first["number"] == second["number"]
        stored = await repo.create({"_id": identifier, "number": "forged"})
        assert stored["number"] == first["number"]
        assert len(collection.documents) == 1
    asyncio.run(run())


def test_migration_is_repeatable_and_never_reuses_archived_numbers():
    async def run():
        archived = {"_id": ObjectId(), "number": "СД-000042", "numberSequence": 42, "deletedAt": "archived"}
        legacy = {"_id": ObjectId(), "createdAt": 1}
        collection, counters = Collection([archived, legacy]), Counter(90)
        await initialize_deal_numbers(collection, counters)
        first = deepcopy(collection.documents)
        assert first[legacy["_id"]]["number"] == "СД-000091"
        assert first[archived["_id"]] == archived
        await initialize_deal_numbers(collection, counters)
        assert collection.documents == first
        assert counters.value == 91
        assert all(options["unique"] for _, options in collection.indexes)
        created = await DealsRepository(collection, counters).create({})
        assert created["number"] == "СД-000092"
    asyncio.run(run())


def test_existing_maximum_seeds_a_missing_counter():
    async def run():
        collection = Collection([{"_id": ObjectId(), "number": "СД-000099", "numberSequence": 99}, {"_id": ObjectId()}])
        counter = Counter()
        await initialize_deal_numbers(collection, counter)
        assert counter.value == 100
        assert {value["number"] for value in collection.documents.values()} == {"СД-000099", "СД-000100"}
    asyncio.run(run())


def test_number_cannot_be_changed_through_public_write_schema():
    assert "number" not in SDealsInput.model_validate({"number": "forged", "numberSequence": 999}).model_dump()
    assert SDealsWithRelations.model_validate({"number": "СД-000123", "numberSequence": 123}).number == "СД-000123"


def test_numbers_expand_beyond_six_digits_without_collision():
    fields = asyncio.run(next_deal_number(Counter(999999)))
    assert fields == {"number": "СД-1000000", "numberSequence": 1000000}


@pytest.mark.parametrize("value", [None, {}, {"value": -1}, {"value": True}, {"value": "1"}])
def test_bad_counter_is_an_error(value):
    with pytest.raises(InternalError):
        asyncio.run(next_deal_number(SimpleNamespace(find_one_and_update=AsyncMock(return_value=value))))


def test_database_failure_does_not_return_an_unnumbered_success():
    repository = DealsRepository(SimpleNamespace(find_one=AsyncMock(side_effect=ServerSelectionTimeoutError("private"))), Counter())
    with pytest.raises(InternalError):
        asyncio.run(repository.create({}))
