import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.companies.page_pipeline import build_company_page_pipeline
from app.companies.repository import CompaniesRepository
from app.companies.router import router
from app.companies.service import CompaniesService
from app.companies.shemas import SCompanyPageQuery
from app.exceptions import AppError, InternalError
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet


@pytest.fixture
def endpoint(monkeypatch):
    company = {"_id": ObjectId(), "name": "Company", "roles": ["provider"], "phones": ["123", "456"],
               "contactPersons": [{"name": "Contact", "phones": ["789", "012"], "emails": ["one@example.com", "two@example.com"]}],
               "internalField": "do-not-expose"}
    read = AsyncMock(return_value=[{"items": [company], "total": [{"value": 47}]}])
    collection = SimpleNamespace(aggregate=Mock(return_value=SimpleNamespace(to_list=read)))
    repository = CompaniesRepository(collection)
    monkeypatch.setattr(CompaniesService, "repository", repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SUsersGet(_id=ObjectId())

    @app.exception_handler(AppError)
    async def error_handler(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, repository=repository, collection=collection, read=read, company=company)


def test_route_returns_complete_totals_and_public_contacts(endpoint):
    response = endpoint.client.get("/companies/page", params={"page": 2, "pageSize": 15, "role": "provider"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 47 and body["totalPages"] == 4
    assert body["page"] == 2 and body["hasNext"] and body["hasPrev"]
    assert body["items"][0]["_id"] == str(endpoint.company["_id"])
    assert body["items"][0]["phones"] == ["123", "456"]
    assert len(body["items"][0]["contactPersons"][0]["emails"]) == 2
    assert "internalField" not in body["items"][0]
    pipeline = endpoint.collection.aggregate.call_args.args[0]
    assert pipeline[0] == {"$match": {"deletedAt": None, "roles": "provider"}}
    assert pipeline[-1]["$facet"]["items"][:3] == [{"$sort": {"_id": -1}}, {"$skip": 15}, {"$limit": 15}]
    assert pipeline[-1]["$facet"]["total"] == [{"$count": "value"}]


@pytest.mark.parametrize("params", [
    {"page": 0}, {"pageSize": 0}, {"pageSize": 101}, {"search": "x" * 201},
    {"role": "invalid"}, {"sortBy": "bad"}, {"priceSort": "bad"}, {"administrativeDistrict": "invalid"},
    {"maxPrice": -1}, {"maxPrice": "nan"}, {"materialId": "bad"},
    {"priceUnit": "т"}, {"priceSort": "asc"}, {"maxPrice": 100},
    {"materialId": "507f1f77bcf86cd799439011", "priceSort": "desc"},
])
def test_invalid_queries_do_not_read_database(endpoint, params):
    assert endpoint.client.get("/companies/page", params=params).status_code == 422
    endpoint.collection.aggregate.assert_not_called()


def test_page_does_not_collide_with_company_id_route_and_requires_auth(endpoint):
    endpoint.app.dependency_overrides.clear()
    assert endpoint.client.get("/companies/page").status_code == 401
    endpoint.collection.aggregate.assert_not_called()


def test_literal_search_covers_all_contact_formats_before_pagination():
    pipeline = build_company_page_pipeline(SCompanyPageQuery(search=" +7 (999) ", page=3))
    conditions = pipeline[0]["$match"]["$or"]
    assert {"name", "contactPersons.phone", "contactPersons.phones", "contactPersons.emails", "emails"} <= {next(iter(value)) for value in conditions}
    assert {"name": {"$regex": re.escape("+7 (999)"), "$options": "i"}} in conditions
    assert len(pipeline) == 2
    assert pipeline[-1]["$facet"]["items"][1] == {"$skip": 30}


def test_geography_and_material_prices_are_filtered_before_the_shared_facet():
    identifier = str(ObjectId())
    pipeline = build_company_page_pipeline(SCompanyPageQuery(role="provider", includeDetails=True,
        city="Москва", district="Раменки", materialId=identifier, priceUnit="тонна", maxPrice=1500, priceSort="asc"))
    assert {"$match": {"addresses.0": {"$exists": True}}} in pipeline[:-1]
    assert {"$match": {"materialsWithPrices.0": {"$exists": True}}} in pipeline[:-1]
    assert {"$match": {"_comparablePrice": {"$lte": 1500}}} in pipeline[:-1]
    filtered = next(stage["$set"]["materialsWithPrices"]["$filter"] for stage in pipeline if "$set" in stage and "materialsWithPrices" in stage["$set"])
    assert {"$eq": ["$$item.materialId", ObjectId(identifier)]} in filtered["cond"]["$and"]
    assert filtered["cond"]["$and"][-1]["$in"][1] == ["т", "тонна", "тонн", "тонны"]
    assert pipeline[-1]["$facet"]["items"][0] == {"$sort": {"_comparablePrice": 1, "_id": 1}}
    assert not any("$skip" in stage or "$limit" in stage for stage in pipeline[:-1])


@pytest.mark.parametrize("unit,aliases", [("куб.м", ["м³", "м3", "куб.м", "куб. м"]), ("шт.", ["шт", "шт.", "штука", "штук"])])
def test_unit_aliases_do_not_compare_unrelated_units(unit, aliases):
    pipeline = build_company_page_pipeline(SCompanyPageQuery(materialId=str(ObjectId()), priceUnit=unit, priceSort="desc"))
    condition = next(stage["$set"]["materialsWithPrices"]["$filter"] for stage in pipeline if "$set" in stage and "materialsWithPrices" in stage["$set"])
    assert condition["cond"]["$and"][-1]["$in"][1] == aliases
    assert pipeline[-1]["$facet"]["items"][0]["$sort"]["_comparablePrice"] == -1


def test_details_are_loaded_only_for_the_page_when_no_related_filter_is_used():
    pipeline = build_company_page_pipeline(SCompanyPageQuery(includeDetails=True, role="customer", sortBy="name"))
    assert len(pipeline) == 2
    items = pipeline[-1]["$facet"]["items"]
    assert items[0] == {"$sort": {"name": 1, "_id": 1}}
    assert items[2] == {"$limit": 15}
    assert [stage["$lookup"]["as"] for stage in items if "$lookup" in stage] == ["addresses", "materialsWithPrices"]
    assert "purchases" not in str(pipeline)


def test_database_errors_do_not_look_like_empty_pages(endpoint):
    endpoint.read.side_effect = ServerSelectionTimeoutError("private details")
    response = endpoint.client.get("/companies/page")
    assert response.status_code == 500
    assert "private" not in response.json()["detail"]


@pytest.mark.parametrize("document", [[], [{}]])
def test_malformed_facet_is_not_a_zero_page(endpoint, document):
    endpoint.read.return_value = document
    with pytest.raises(InternalError):
        asyncio.run(endpoint.repository.read_page([]))


def test_legitimate_empty_result(endpoint):
    endpoint.read.return_value = [{"items": [], "total": []}]
    body = endpoint.client.get("/companies/page").json()
    assert body["items"] == [] and body["total"] == 0 and body["hasNext"] is False
