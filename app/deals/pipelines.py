from typing import Dict, List, Optional

from bson import ObjectId


def get_deal_relation_lookups() -> List[Dict]:
    return [
        {"$lookup": {
            "from": "services",
            "localField": "serviceId",
            "foreignField": "_id",
            "as": "service",
        }},
        {"$lookup": {
            "from": "companies",
            "localField": "customerId",
            "foreignField": "_id",
            "as": "customer",
        }},
        {"$lookup": {
            "from": "stages",
            "localField": "stageId",
            "foreignField": "_id",
            "as": "stage",
        }},
        {"$lookup": {
            "from": "materials",
            "localField": "materialId",
            "foreignField": "_id",
            "as": "material",
        }},
        {"$lookup": {
            "from": "adresses",
            "localField": "shippingAddressId",
            "foreignField": "_id",
            "as": "shipping_address",
        }},
        {"$lookup": {
            "from": "adresses",
            "localField": "deliveryAddressId",
            "foreignField": "_id",
            "as": "delivery_address",
        }},
        {"$lookup": {
            "from": "users",
            "localField": "userId",
            "foreignField": "_id",
            "as": "user",
        }},
        {"$addFields": {
            "service": {"$arrayElemAt": ["$service", 0]},
            "customer": {"$arrayElemAt": ["$customer", 0]},
            "stage": {"$arrayElemAt": ["$stage", 0]},
            "material": {"$arrayElemAt": ["$material", 0]},
            "shipping_address": {"$arrayElemAt": ["$shipping_address", 0]},
            "delivery_address": {"$arrayElemAt": ["$delivery_address", 0]},
            "user": {"$arrayElemAt": ["$user", 0]},
        }},
    ]


def build_deal_relations_pipeline(
        deal_id: Optional[str] = None,
        match_filter: Optional[Dict] = None,
) -> List[Dict]:
    pipeline: List[Dict] = []
    if deal_id:
        pipeline.append({"$match": {"_id": ObjectId(deal_id)}})
    elif match_filter:
        pipeline.append({"$match": match_filter})
    pipeline.extend(get_deal_relation_lookups())
    return pipeline
