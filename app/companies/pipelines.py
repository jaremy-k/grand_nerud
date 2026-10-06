from bson import ObjectId

from app.companies.shemas import CompanyRole


def _addresses_lookup(
        city: str | None = None,
        administrative_district: str | None = None,
        district: str | None = None,
) -> dict:
    conditions = [
        {"$eq": [{"$ifNull": ["$deletedAt", None]}, None]},
        {"$or": [
            {"$eq": ["$companyId", "$$companyObjectId"]},
            {"$eq": ["$companyId", "$$companyStringId"]},
        ]},
    ]
    if city:
        conditions.append({"$eq": ["$city", city]})
    if administrative_district:
        conditions.append({"$eq": ["$administrativeDistrict", administrative_district]})
    if district:
        conditions.append({"$eq": ["$district", district]})

    return {"$lookup": {
        "from": "adresses",
        "let": {
            "companyObjectId": "$_id",
            "companyStringId": {"$toString": "$_id"},
        },
        "pipeline": [
            {"$match": {"$expr": {"$and": conditions}}},
        ],
        "as": "addresses",
    }}


def _company_materials_lookup() -> dict:
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
        role: CompanyRole | None,
        deal_user_id: ObjectId | None = None,
        city: str | None = None,
        administrative_district: str | None = None,
        district: str | None = None,
        include_details: bool = True,
) -> list[dict]:
    pipeline = [
        {"$match": match_filter},
        _addresses_lookup(city, administrative_district, district),
    ]
    if city or administrative_district or district:
        pipeline.append({"$match": {"addresses.0": {"$exists": True}}})
    if include_details:
        pipeline.append(_company_materials_lookup())
        if role == "customer":
            pipeline.append(_customer_purchases_lookup(deal_user_id))
    pipeline.append({"$sort": {"name": 1}})
    return pipeline
