from pymongo import ReturnDocument

from app.exceptions import InternalError


async def next_deal_number(counters) -> dict:
    counter = await counters.find_one_and_update(
        {"_id": "deal_number"}, {"$inc": {"value": 1}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    sequence = counter.get("value") if counter else None
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise InternalError("Не удалось присвоить номер сделки")
    return {"numberSequence": sequence, "number": f"СД-{sequence:06d}"}


async def initialize_deal_numbers(deals, counters) -> None:
    await deals.create_index("number", name="deal_number_unique", unique=True,
                             partialFilterExpression={"number": {"$type": "string", "$gt": ""}})
    await deals.create_index("numberSequence", name="deal_number_sequence_unique", unique=True,
                             partialFilterExpression={"numberSequence": {"$type": "number"}})
    highest = await deals.find({"numberSequence": {"$type": "number"}}).sort("numberSequence", -1).limit(1).to_list(length=1)
    await counters.update_one({"_id": "deal_number"}, {"$max": {"value": highest[0]["numberSequence"] if highest else 0}}, upsert=True)
    # Each update reserves its number atomically and never renumbers an assigned deal.
    async for deal in deals.find({"number": {"$in": [None, ""]}}).sort([("createdAt", 1), ("_id", 1)]):
        fields = await next_deal_number(counters)
        await deals.update_one({"_id": deal["_id"], "number": {"$in": [None, ""]}}, {"$set": fields})
