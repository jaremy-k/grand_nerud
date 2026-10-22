import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.exceptions import AppError, ForbiddenError, InternalError
from app.tasks.service import TasksService
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet
from app.workspace import service as workspace_service
from app.workspace.repository import WorkspaceRepository
from app.workspace.router import router
from app.workspace.service import WorkspaceService

NOW = datetime(2026, 10, 12, 10, 30, tzinfo=timezone.utc)


@pytest.fixture
def workspace(monkeypatch):
    owner, other, task_id, lead_id, company_id, stage_id = [ObjectId() for _ in range(6)]
    user = SUsersGet(_id=owner)
    task = {
        "_id": task_id, "ownerId": owner, "title": "Call customer",
        "dueAt": NOW - timedelta(hours=1), "status": "open", "type": "call",
        "companyId": company_id, "leadId": lead_id,
        "company": {"_id": company_id, "name": "Company"},
        "lead": {"_id": lead_id, "title": "New lead"},
    }
    lead = {
        "_id": lead_id, "ownerId": owner, "createdById": owner,
        "title": "New lead", "stageId": stage_id, "materialIds": [],
        "createdAt": NOW, "updatedAt": NOW, "deletedAt": None,
        "conversionInput": {"internal": True}, "importKey": "private",
    }
    task_document = {
        "overdueItems": [task], "overdueTotal": [{"value": 12}],
        "todayItems": [task], "todayTotal": [{"value": 27}],
        "upcomingItems": [], "upcomingTotal": [],
    }
    lead_document = {"items": [lead], "total": [{"value": 18}]}
    task_read = AsyncMock(return_value=[task_document])
    lead_read = AsyncMock(return_value=[lead_document])
    repository = WorkspaceRepository()
    repository.tasks_collection = SimpleNamespace(aggregate=Mock(return_value=SimpleNamespace(to_list=task_read)))
    repository.leads_collection = SimpleNamespace(aggregate=Mock(return_value=SimpleNamespace(to_list=lead_read)))
    monkeypatch.setattr(WorkspaceService, "repository", repository)
    monkeypatch.setattr(workspace_service, "utc_now", lambda: NOW)
    links = AsyncMock(return_value=(None, None))
    monkeypatch.setattr(TasksService, "_linked_records", links)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user

    @app.exception_handler(AppError)
    async def error_handler(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return SimpleNamespace(
        user=user, owner=owner, other=other, task=task, lead=lead, repository=repository,
        task_read=task_read, lead_read=lead_read, links=links, app=app,
    )


@pytest.fixture
def client(workspace):
    with TestClient(workspace.app) as value:
        yield value


def test_tasks_use_complete_facet_totals_and_one_shared_clock(client, workspace):
    response = client.get("/workspace/tasks", params={"limit": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "mine" and body["ownerId"] == str(workspace.owner)
    assert body["generatedAt"] == "2026-10-12T10:30:00Z"
    assert body["localDate"] == "2026-10-12" and body["timezone"] == "Europe/Moscow"
    assert body["overdue"]["total"] == 12 and body["today"]["total"] == 27
    assert body["overdue"]["hasMore"] is True
    assert body["upcoming"] == {"items": [], "total": 0, "hasMore": False}
    task = body["overdue"]["items"][0]
    assert task["_id"] == str(workspace.task["_id"])
    assert task["company"] == {"_id": str(workspace.task["companyId"]), "name": "Company"}
    assert task["lead"] == {"_id": str(workspace.task["leadId"]), "title": "New lead"}
    workspace.repository.tasks_collection.aggregate.assert_called_once()
    pipeline = workspace.repository.tasks_collection.aggregate.call_args.args[0]
    assert pipeline[0] == {"$match": {"deletedAt": None, "status": "open", "ownerId": workspace.owner}}
    facets = pipeline[1]["$facet"]
    assert facets["overdueTotal"][0] == {"$match": {"dueAt": {"$lt": NOW}}}
    assert facets["todayTotal"][0] == {"$match": {"dueAt": {
        "$gte": datetime(2026, 10, 11, 21, tzinfo=timezone.utc),
        "$lt": datetime(2026, 10, 12, 21, tzinfo=timezone.utc),
    }}}
    for bucket in ("overdue", "today", "upcoming"):
        assert facets[f"{bucket}Items"][0] == facets[f"{bucket}Total"][0]
        assert facets[f"{bucket}Items"][1:3] == [{"$sort": {"dueAt": 1, "_id": 1}}, {"$limit": 3}]
    workspace.links.assert_awaited_once()
    assert response.headers["cache-control"] == "no-store"


def test_new_leads_filter_stage_kind_and_strip_internal_fields(client, workspace):
    response = client.get("/workspace/leads")
    assert response.status_code == 200
    preview = response.json()["newLeads"]
    assert preview["total"] == 18 and preview["hasMore"] is True
    lead = preview["items"][0]
    assert "conversionInput" not in lead and "importKey" not in lead
    pipeline = workspace.repository.leads_collection.aggregate.call_args.args[0]
    assert pipeline[0]["$match"] == {"deletedAt": None, "ownerId": workspace.owner}
    assert {"$match": {"_workspaceStage": {"$elemMatch": {"kind": "new", "deletedAt": None}}}} in pipeline
    assert pipeline[-1]["$facet"]["items"][:2] == [
        {"$sort": {"createdAt": -1, "_id": -1}}, {"$limit": 6},
    ]


@pytest.mark.parametrize("path", ["/workspace/tasks", "/workspace/leads"])
@pytest.mark.parametrize("role", ["admin", "manager"])
def test_privileged_defaults_still_mine_and_team_is_explicit(client, workspace, path, role):
    setattr(workspace.user, role, True)
    assert client.get(path).json()["ownerId"] == str(workspace.owner)
    assert client.get(path, params={"scope": "team"}).json()["scope"] == "team"
    collection = workspace.repository.tasks_collection if path.endswith("tasks") else workspace.repository.leads_collection
    assert "ownerId" not in collection.aggregate.call_args.args[0][0]["$match"]
    response = client.get(path, params={"ownerId": str(workspace.other)})
    assert response.status_code == 200
    assert response.json()["scope"] == "owner"
    assert collection.aggregate.call_args.args[0][0]["$match"]["ownerId"] == workspace.other


@pytest.mark.parametrize("path", ["/workspace/tasks", "/workspace/leads"])
@pytest.mark.parametrize("params", [{"scope": "team"}, {"ownerId": "507f1f77bcf86cd799439011"}])
def test_regular_user_cannot_request_team_or_other_owner(client, workspace, path, params):
    assert client.get(path, params=params).status_code == 403
    workspace.repository.tasks_collection.aggregate.assert_not_called()
    workspace.repository.leads_collection.aggregate.assert_not_called()


@pytest.mark.parametrize("path", ["/workspace/tasks", "/workspace/leads"])
@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 21}, {"scope": "all"}, {"ownerId": "bad"},
    {"ownerId": ""}, {"timezone": "Bad/Timezone"}, {"timezone": ""},
])
def test_invalid_queries_fail_before_database(client, workspace, path, params):
    assert client.get(path, params=params).status_code == 422
    workspace.repository.tasks_collection.aggregate.assert_not_called()
    workspace.repository.leads_collection.aggregate.assert_not_called()


@pytest.mark.parametrize("path", ["/workspace/tasks", "/workspace/leads"])
def test_team_and_owner_cannot_be_combined(client, workspace, path):
    workspace.user.manager = True
    assert client.get(path, params={"scope": "team", "ownerId": str(workspace.owner)}).status_code == 422


@pytest.mark.parametrize("now,zone,start,end", [
    (datetime(2026, 10, 12, 22, tzinfo=timezone.utc), "Europe/Moscow",
     datetime(2026, 10, 12, 21, tzinfo=timezone.utc), datetime(2026, 10, 13, 21, tzinfo=timezone.utc)),
    (datetime(2026, 3, 8, 12, tzinfo=timezone.utc), "America/New_York",
     datetime(2026, 3, 8, 5, tzinfo=timezone.utc), datetime(2026, 3, 9, 4, tzinfo=timezone.utc)),
])
def test_calendar_boundaries_and_dst(workspace, monkeypatch, now, zone, start, end):
    monkeypatch.setattr(workspace_service, "utc_now", lambda: now)
    asyncio.run(WorkspaceService.tasks(workspace.user, timezone=zone))
    facets = workspace.repository.tasks_collection.aggregate.call_args.args[0][1]["$facet"]
    assert facets["todayTotal"][0]["$match"]["dueAt"] == {"$gte": start, "$lt": end}
    assert facets["upcomingTotal"][0]["$match"]["dueAt"] == {"$gte": end}
    assert facets["overdueTotal"][0]["$match"]["dueAt"] == {"$lt": now}


def test_link_permissions_are_rechecked_before_tasks_are_returned(client, workspace):
    workspace.links.side_effect = ForbiddenError()
    assert client.get("/workspace/tasks").status_code == 403


@pytest.mark.parametrize("path", ["/workspace/tasks", "/workspace/leads"])
def test_database_failures_are_errors_not_zero_counters(client, workspace, path):
    collection = workspace.repository.tasks_collection if path.endswith("tasks") else workspace.repository.leads_collection
    collection.aggregate.side_effect = ServerSelectionTimeoutError("sensitive database detail")
    response = client.get(path)
    assert response.status_code == 500
    assert "total" not in response.json()
    assert "sensitive" not in response.json()["detail"]


@pytest.mark.parametrize("path", ["/workspace/tasks", "/workspace/leads"])
def test_empty_aggregation_response_is_not_a_valid_empty_workspace(client, workspace, path):
    reader = workspace.task_read if path.endswith("tasks") else workspace.lead_read
    reader.return_value = []
    assert client.get(path).status_code == 500


def test_legitimate_empty_facets_have_zero_totals(client, workspace):
    workspace.task_read.return_value = [{
        f"{bucket}{kind}": [] for bucket in ("overdue", "today", "upcoming") for kind in ("Items", "Total")
    }]
    workspace.lead_read.return_value = [{"items": [], "total": []}]
    assert client.get("/workspace/tasks").json()["today"] == {"items": [], "total": 0, "hasMore": False}
    assert client.get("/workspace/leads").json()["newLeads"]["total"] == 0


@pytest.mark.parametrize("path", ["/workspace/tasks", "/workspace/leads"])
def test_routes_require_authentication(client, workspace, path):
    workspace.app.dependency_overrides.clear()
    assert client.get(path).status_code == 401
    workspace.repository.tasks_collection.aggregate.assert_not_called()
    workspace.repository.leads_collection.aggregate.assert_not_called()


def test_missing_authenticated_id_cannot_broaden_scope(client, workspace):
    workspace.user.id = None
    workspace.user.admin = True
    assert client.get("/workspace/tasks").status_code == 403
    workspace.repository.tasks_collection.aggregate.assert_not_called()


def test_openapi_and_main_app_include_workspace_routes(client):
    from app.main import app

    document = client.get("/openapi.json").json()
    assert {"/workspace/tasks", "/workspace/leads"} <= document["paths"].keys()
    assert {"/workspace/tasks", "/workspace/leads"} <= {route.path for route in app.routes}
