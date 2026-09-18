from bson import ObjectId

from app.companies.pipelines import build_company_details_pipeline


def _lookup_by_alias(pipeline: list[dict], alias: str) -> dict:
    return next(stage["$lookup"] for stage in pipeline if stage.get("$lookup", {}).get("as") == alias)


def test_provider_details_include_addresses_and_material_prices():
    pipeline = build_company_details_pipeline({"roles": "provider"}, "provider")

    assert _lookup_by_alias(pipeline, "addresses")
    assert _lookup_by_alias(pipeline, "materialsWithPrices")
    assert not any(stage.get("$lookup", {}).get("as") == "purchases" for stage in pipeline)


def test_customer_details_include_own_purchases_for_regular_user():
    user_id = ObjectId()
    pipeline = build_company_details_pipeline({"roles": "customer"}, "customer", user_id)
    purchases = _lookup_by_alias(pipeline, "purchases")
    match_expression = purchases["pipeline"][0]["$match"]["$expr"]

    assert _lookup_by_alias(pipeline, "addresses")
    assert {"$eq": ["$userId", user_id]} in match_expression["$and"]
    projection = next(stage["$project"] for stage in purchases["pipeline"] if "$project" in stage)
    assert projection["price"] == "$amountSalesUnit"


def test_customer_details_include_all_purchases_for_privileged_user():
    pipeline = build_company_details_pipeline({"roles": "customer"}, "customer")
    purchases = _lookup_by_alias(pipeline, "purchases")
    conditions = purchases["pipeline"][0]["$match"]["$expr"]["$and"]

    assert not any(condition.get("$eq", [None])[0] == "$userId" for condition in conditions)
