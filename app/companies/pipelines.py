from bson import ObjectId

from app.companies.shemas import CompanyRole


def _addresses_lookup() -> dict:
    return {"$lookup": {
        "from": "adresses",
        "let": {
            "companyObjectId": "$_id",
            "companyStringId": {"$toString": "$_id"},
        },
        "pipeline": [
            {"$match": {"$expr": {"$and": [
                {"$eq": [{"$ifNull": ["$deletedAt", None]}, None]},
                {"$or": [
                    {"$eq": ["$companyId", "$$companyObjectId"]},
                    {"$eq": ["$companyId", "$$companyStringId"]},
                ]},
            ]}}},
        ],
        "as": "addresses",
    }}


def _provider_materials_lookup() -> dict:
    return {"$lookup": {
        "from": "company_materials",
        "let": {"companyId": "$_id"},
        "pipeline": [
            {"$match": {"$expr": {"$and": [
                {"$eq": ["$companyId", "$$companyId"]},
                {"$eq": [{"$ifNull": ["$deletedAt", None]}, None]},
            ]}}},
            {"$lookup": {
                "from": "materials",
                "localField": "materialId",
                "foreignField": "_id",
                "as": "material",
            }},
            {"$addFields": {"material": {"$arrayElemAt": ["$material", 0]}}},
            {"$project": {
                "companyId": 1,
                "materialId": 1,
                "price": 1,
                "unit": 1,
                "comment": 1,
                "material": 1,
            }},
        ],
        "as": "materialsWithPrices",
    }}


def _customer_purchases_lookup(user_id: ObjectId | None) -> dict:
    conditions: list[dict] = [
        {"$eq": ["$customerId", "$$companyId"]},
        {"$eq": [{"$ifNull": ["$deletedAt", None]}, None]},
    ]
    if user_id is not None:
        conditions.append({"$eq": ["$userId", user_id]})

    return {"$lookup": {
        "from": "deals",
        "let": {"companyId": "$_id"},
        "pipeline": [
            {"$match": {"$expr": {"$and": conditions}}},
            {"$lookup": {
                "from": "materials",
                "localField": "materialId",
                "foreignField": "_id",
                "as": "material",
            }},
            {"$lookup": {
                "from": "adresses",
                "localField": "deliveryAddressId",
                "foreignField": "_id",
                "as": "delivery_address",
            }},
            {"$addFields": {
                "material": {"$arrayElemAt": ["$material", 0]},
                "delivery_address": {"$arrayElemAt": ["$delivery_address", 0]},
            }},
            {"$project": {
                "materialId": 1,
                "deliveryAddress": 1,
                "deliveryAddressId": 1,
                "quantity": 1,
                "unitMeasurement": 1,
                "amountSalesUnit": 1,
                "amountSalesTotal": 1,
                "price": "$amountSalesUnit",
                "notes": 1,
                "createdAt": 1,
                "material": 1,
                "delivery_address": 1,
            }},
            {"$sort": {"createdAt": -1}},
        ],
        "as": "purchases",
    }}


def build_company_details_pipeline(
        match_filter: dict,
        role: CompanyRole,
        deal_user_id: ObjectId | None = None,
) -> list[dict]:
    pipeline = [
        {"$match": match_filter},
        _addresses_lookup(),
    ]
    if role == "provider":
        pipeline.append(_provider_materials_lookup())
    else:
        pipeline.append(_customer_purchases_lookup(deal_user_id))
    pipeline.append({"$sort": {"name": 1}})
    return pipeline
