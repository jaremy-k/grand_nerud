from typing import Any

from app.database import database_mongo

CONFIG_ID = "calculator"
_collection = database_mongo["calculator_config"]


async def find_config() -> dict[str, Any] | None:
    return await _collection.find_one({"_id": CONFIG_ID})


async def upsert_config(data: dict[str, Any]) -> dict[str, Any] | None:
    await _collection.replace_one(
        {"_id": CONFIG_ID},
        {"_id": CONFIG_ID, **data},
        upsert=True,
    )
    return await find_config()
