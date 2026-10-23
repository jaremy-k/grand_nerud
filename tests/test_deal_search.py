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

from app.core.pagination import PaginatedResponse, PaginationParams
from app.deals.repository import DealsRepository
from app.deals.router import router
from app.deals.service import DealsService
from app.deals.shemas import SDeals
from app.exceptions import AppError, InternalError
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet


@pytest.fixture
def endpoint(monkeypatch):
    user = SUsersGet(_id=ObjectId())
    repository = SimpleNamespace(find_paginated_with_relations=AsyncMock(return_value=PaginatedResponse(
        items=[], total=0, page=1, page_size=20, total_pages=0, has_next=False, has_prev=False,
    )))
    monkeypatch.setattr(DealsService, "repository", repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user

    @app.exception_handler(AppError)
    async def error_handler(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, user=user, repository=repository, app=app)


def test_search_and_company_filter_are_applied_before_pagination(endpoint):
    company, material, another_owner = [ObjectId() for _ in range(3)]
    response = endpoint.client.get("/deals", params={
        "search": "  Песок + щебень  ", "companyId": str(company), "materialId": str(material),
        "userId": str(another_owner), "page": 3, "page_size": 20, "includeRelations": True,
    })
    assert response.status_code == 200
    kwargs = endpoint.repository.find_paginated_with_relations.call_args.kwargs
    assert kwargs["filter_by"]["userId"] == ObjectId(endpoint.user.id)
    assert kwargs["filter_by"]["materialId"] == material
    assert kwargs["filter_by"]["deletedAt"] is None
    assert kwargs["filter_by"]["$or"] == [{"customerId": company}, {"providerId": company}]
    assert kwargs["search"] == "Песок + щебень"
    assert kwargs["skip"] == 40 and kwargs["limit"] == 20
    assert kwargs["include_relations"] is True
    assert response.json()["totalPages"] == 0


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_privileged_can_filter_by_owner_without_implicit_replacement(endpoint, role):
    setattr(endpoint.user, role, True)
    other = ObjectId()
    assert endpoint.client.get("/deals", params={"userId": str(other)}).status_code == 200
    assert endpoint.repository.find_paginated_with_relations.call_args.kwargs["filter_by"]["userId"] == other
    assert endpoint.client.get("/deals").status_code == 200
    assert "userId" not in endpoint.repository.find_paginated_with_relations.call_args.kwargs["filter_by"]


def test_customer_role_filter_can_be_combined_with_generic_company(endpoint):
    company = ObjectId()
    assert endpoint.client.get("/deals", params={"customerId": str(company), "companyId": str(company)}).status_code == 200
    query = endpoint.repository.find_paginated_with_relations.call_args.kwargs["filter_by"]
    assert query["customerId"] == company
    assert query["$or"] == [{"customerId": company}, {"providerId": company}]


@pytest.mark.parametrize("params", [
    {"companyId": "invalid"}, {"companyId": ""}, {"search": "x" * 201},
    {"page": 0}, {"page_size": 0}, {"page_size": 201}, {"page": -1},
])
def test_invalid_input_is_rejected_before_reading_database(endpoint, params):
    assert endpoint.client.get("/deals", params=params).status_code == 422
    endpoint.repository.find_paginated_with_relations.assert_not_called()


def test_search_requires_authentication(endpoint):
    endpoint.app.dependency_overrides.clear()
    assert endpoint.client.get("/deals", params={"search": "sand"}).status_code == 401
    endpoint.repository.find_paginated_with_relations.assert_not_called()


def test_missing_employee_id_cannot_broaden_search(endpoint):
    endpoint.user.id = None
    assert endpoint.client.get("/deals", params={"search": "sand"}).status_code == 403
    endpoint.repository.find_paginated_with_relations.assert_not_called()


def test_stable_sort_and_blank_search(endpoint):
    assert endpoint.client.get("/deals", params={"search": "   ", "sortBy": "quantity", "sortOrder": "desc"}).status_code == 200
    kwargs = endpoint.repository.find_paginated_with_relations.call_args.kwargs
    assert kwargs["search"] == ""
    assert kwargs["sort"] == [("quantity", -1), ("_id", -1)]
    endpoint.client.get("/deals", params={"sortBy": "_id"})
    assert endpoint.repository.find_paginated_with_relations.call_args.kwargs["sort"] == [("_id", 1)]


def test_service_validates_search_length_outside_http(endpoint):
    with pytest.raises(AppError):
        asyncio.run(DealsService.list_deals(SDeals(), PaginationParams(), endpoint.user, search="x" * 201))
    endpoint.repository.find_paginated_with_relations.assert_not_called()


@pytest.fixture
def collection():
    identifier = ObjectId()
    read = AsyncMock(return_value=[{"items": [{"_id": identifier}], "total": [{"value": 57}]}])
    value = SimpleNamespace(aggregate=Mock(return_value=SimpleNamespace(to_list=read)), count_documents=AsyncMock())
    return SimpleNamespace(value=value, read=read, repository=DealsRepository(value), identifier=identifier)


@pytest.mark.parametrize("relations", [False, True])
def test_repository_search_counts_full_result_and_limits_only_items(collection, relations):
    query = {"userId": ObjectId(), "deletedAt": None, "customerId": ObjectId()}
    result = asyncio.run(collection.repository.find_paginated_with_relations(
        filter_by=query, search="Песок (мытый) +", skip=20, limit=20,
        sort=[("createdAt", -1), ("_id", -1)], include_relations=relations,
    ))
    assert result.total == 57 and result.page == 2 and result.total_pages == 3
    assert result.items == [{"_id": str(collection.identifier)}]
    assert result.has_next is True
    pipeline = collection.value.aggregate.call_args.args[0]
    assert pipeline[0] == {"$match": query}
    assert not any("$skip" in stage or "$limit" in stage for stage in pipeline[:-1])
    matches = pipeline[-2]["$match"]["$or"]
    assert {"_searchCustomer.name", "_searchProvider.inn", "_searchMaterial.name"} <= {next(iter(item)) for item in matches}
    for condition in matches:
        assert next(iter(condition.values())) == {"$regex": re.escape("Песок (мытый) +"), "$options": "i"}
    facet = pipeline[-1]["$facet"]
    assert facet["total"] == [{"$count": "value"}]
    assert facet["items"][:3] == [{"$sort": {"createdAt": -1, "_id": -1}}, {"$skip": 20}, {"$limit": 20}]
    assert facet["items"][3] == {"$project": {"_searchCustomer": 0, "_searchProvider": 0, "_searchMaterial": 0}}
    assert any("$lookup" in stage for stage in facet["items"]) is relations
    collection.value.count_documents.assert_not_called()
    collection.read.assert_awaited_once_with(length=1)


def test_full_id_is_searchable_without_string_regex_on_objectid(collection):
    asyncio.run(collection.repository.find_paginated_with_relations(search=str(collection.identifier)))
    matches = collection.value.aggregate.call_args.args[0][-2]["$match"]["$or"]
    assert {"_id": collection.identifier} in matches


def test_empty_search_result_is_legitimate_zero(collection):
    collection.read.return_value = [{"items": [], "total": []}]
    result = asyncio.run(collection.repository.find_paginated_with_relations(search="missing"))
    assert result.total == 0 and result.items == []


@pytest.mark.parametrize("document", [[], [{}], [{"items": []}]])
def test_missing_facet_is_an_error_not_empty_result(collection, document):
    collection.read.return_value = document
    with pytest.raises(InternalError):
        asyncio.run(collection.repository.find_paginated_with_relations(search="sand"))


@pytest.mark.parametrize("search", ["sand", ""])
@pytest.mark.parametrize("relations", [False, True])
def test_database_failure_is_not_silenced(collection, search, relations):
    collection.read.side_effect = ServerSelectionTimeoutError("private details")
    collection.value.count_documents.side_effect = ServerSelectionTimeoutError("private details")
    with pytest.raises(InternalError) as error:
        asyncio.run(collection.repository.find_paginated_with_relations(search=search, include_relations=relations))
    assert "private" not in str(error.value)


def test_repository_does_not_mutate_callers_filter(collection):
    query = {"deletedAt": None}
    asyncio.run(collection.repository.find_paginated_with_relations(filter_by=query, search="sand", customerId=ObjectId()))
    assert query == {"deletedAt": None}


def test_openapi_describes_new_search_parameters(endpoint):
    parameters = endpoint.client.get("/openapi.json").json()["paths"]["/deals"]["get"]["parameters"]
    assert {"search", "companyId", "materialId", "customerId", "providerId"} <= {value["name"] for value in parameters}
