from typing import Any

from bson import ObjectId

from app.core.mongo_utils import convert_objectids_to_str
from app.database import database_mongo

_collection = database_mongo["calculation_rules"]


async def find_by_id(rule_id: str) -> dict[str, Any] | None:
    if not ObjectId.is_valid(rule_id):
        return None
    return await _collection.find_one({"_id": ObjectId(rule_id)})


async def find_active() -> dict[str, Any] | None:
    return await _collection.find_one({"isActive": True}, sort=[("version", -1)])


async def find_all() -> list[dict[str, Any]]:
    cursor = _collection.find({}).sort([("version", -1), ("updatedAt", -1)])
    return convert_objectids_to_str([doc async for doc in cursor])


async def get_next_version() -> int:
    doc = await _collection.find_one({}, sort=[("version", -1)])
    if not doc:
        return 1
    return int(doc.get("version") or 0) + 1


async def insert(document: dict[str, Any]) -> dict[str, Any] | None:
    result = await _collection.insert_one(document)
    return await _collection.find_one({"_id": result.inserted_id})


async def update(
        rule_id: str,
        data: dict[str, Any],
        unset: list[str] | None = None,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(rule_id):
        return None
    oid = ObjectId(rule_id)
    update_doc: dict[str, Any] = {"$set": data}
    if unset:
        update_doc["$unset"] = {field: "" for field in unset}
    await _collection.update_one({"_id": oid}, update_doc)
    return await _collection.find_one({"_id": oid})


async def deactivate_all() -> None:
    await _collection.update_many({"isActive": True}, {"$set": {"isActive": False}})
