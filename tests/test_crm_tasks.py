import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError

from app.core.crm import ensure_owner_access
from app.core.mongo_utils import convert_objectids_to_str
from app.core.pagination import PaginatedResponse
from app.deals.service import DealsService
from app.exceptions import AppError, ForbiddenError, InternalError, NotFoundError, ValidationError
from app.tasks import service as tasks_service
from app.tasks.router import router
from app.tasks.service import TasksService
from app.tasks.shemas import STasks, STasksCreate, STasksFilters, STasksPagination, STasksUpdate
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet

NOW = datetime(2026, 10, 12, 10, 30, tzinfo=timezone.utc)


@pytest.fixture
def crm(monkeypatch):
    from app.leads.activities import LeadActivitiesService
    from app.leads.service import LeadsService

    owner, other, admin_id, company_id, lead_id, deal_id = [ObjectId() for _ in range(6)]
    user = SUsersGet(_id=owner)
    admin = SUsersGet(_id=admin_id, admin=True)
    users = {owner: {"_id": owner}, other: {"_id": other}, admin_id: {"_id": admin_id, "admin": True}}
    companies = {company_id: {"_id": company_id, "deletedAt": None}}
    lead = {
        "_id": lead_id, "ownerId": owner, "companyId": company_id,
        "deletedAt": None, "nextContactAt": None, "followUpTaskId": None,
    }
    deal = {
        "_id": deal_id, "userId": owner, "customerId": company_id,
        "sourceLeadId": lead_id, "deletedAt": None,
    }
    leads, deals, tasks = {lead_id: lead}, {deal_id: deal}, {}

    def lookup(records):
        async def find_one(filter_by=None, **kwargs):
            query = {**(filter_by or {}), **kwargs}
            record = records.get(query.get("_id"))
            if record is not None and all(record.get(key) == value for key, value in query.items()):
                return dict(record)
            return None
        return AsyncMock(side_effect=find_one)

    async def create(document):
        record = {**document, "_id": ObjectId()}
        tasks[record["_id"]] = record
        return dict(record)

    async def update_by_id(object_id, update_data):
        oid = ObjectId(str(object_id))
        if oid not in tasks:
            return None
        tasks[oid].update(update_data)
        return dict(tasks[oid])

    async def get_lead(entity_id, caller):
        record = leads.get(ObjectId(str(entity_id)))
        if record is None or record.get("deletedAt") is not None:
            raise NotFoundError()
        ensure_owner_access(record, caller)
        return convert_objectids_to_str(record)

    async def get_historical_lead(entity_id, caller):
        record = leads.get(ObjectId(str(entity_id)))
        if record is None:
            raise NotFoundError()
        ensure_owner_access(record, caller)
        return convert_objectids_to_str(record)

    async def update_leads(filter_by, update_data):
        modified = 0
        for record in leads.values():
            if all(record.get(key) == value for key, value in filter_by.items()):
                record.update(update_data)
                modified += 1
        return modified

    repository = SimpleNamespace(
        find_one=lookup(tasks), create=AsyncMock(side_effect=create),
        update_by_id=AsyncMock(side_effect=update_by_id),
        find_paginated=AsyncMock(return_value=PaginatedResponse(
            items=[], total=0, page=1, page_size=100, total_pages=0, has_next=False, has_prev=False,
        )),
    )
    lead_repository = SimpleNamespace(update_many=AsyncMock(side_effect=update_leads))
    history = AsyncMock(return_value={})
    read_lead = AsyncMock(side_effect=get_lead)
    monkeypatch.setattr(TasksService, "repository", repository)
    monkeypatch.setattr(DealsService, "repository", SimpleNamespace(find_one=lookup(deals)))
    monkeypatch.setattr(LeadsService, "repository", lead_repository)
    monkeypatch.setattr(LeadsService, "get_by_id", read_lead)
    monkeypatch.setattr(LeadsService, "get_for_task", AsyncMock(side_effect=get_historical_lead))
    monkeypatch.setattr(LeadActivitiesService, "record", history)
    monkeypatch.setattr(tasks_service.companies_repository, "find_one", lookup(companies))
    monkeypatch.setattr(tasks_service.users_repository, "find_one", lookup(users))
    monkeypatch.setattr(tasks_service, "utc_now", lambda: NOW)

    def add_task(**overrides):
        record = {
            "_id": ObjectId(), "title": "Call customer", "type": "call", "status": "open",
            "dueAt": NOW, "ownerId": owner, "createdById": owner, "deletedAt": None,
            **overrides,
        }
        tasks[record["_id"]] = record
        if record.get("followUp"):
            lead.update(followUpTaskId=record["_id"], nextContactAt=record["dueAt"])
        return record

    return SimpleNamespace(
        user=user, admin=admin, owner=owner, other=other, users=users,
        company_id=company_id, lead_id=lead_id, deal_id=deal_id,
        lead=lead, deal=deal, tasks=tasks, add_task=add_task, repository=repository,
        lead_repository=lead_repository, read_lead=read_lead, history=history,
    )


@pytest.fixture
def client(crm):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: crm.user

    @app.exception_handler(AppError)
    async def app_error_handler(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    with TestClient(app) as test_client:
        yield test_client


def test_create_defaults_owner_audit_fields_and_serialization(crm):
    data = STasksCreate(title="  Call customer  ", dueAt="2026-10-12T13:30:00+03:00")
    task = asyncio.run(TasksService.create(data, crm.user))

    assert task["title"] == "Call customer"
    assert task["type"] == "call" and task["status"] == "open"
    assert task["dueAt"] == NOW and task["dueAt"].tzinfo == timezone.utc
    assert task["ownerId"] == task["createdById"] == str(crm.owner)
    assert task["createdAt"] == task["updatedAt"] == NOW
    assert ObjectId.is_valid(task["_id"])
    assert task["deletedAt"] is None
    assert STasks.model_validate(task).createdById == str(crm.owner)
    crm.history.assert_not_awaited()


@pytest.mark.parametrize("changes", [
    {"title": " "}, {"title": None}, {"type": "fax"}, {"status": "done"},
    {"dueAt": "2026-10-12T13:30:00"}, {"leadId": "invalid"}, {"followUp": True},
])
def test_create_rejects_invalid_fields(changes):
    with pytest.raises(PydanticValidationError):
        STasksCreate.model_validate({"title": "Call", "dueAt": NOW, **changes})


@pytest.mark.parametrize("field", ["title", "dueAt"])
def test_create_requires_title_and_deadline(field):
    data = {"title": "Call", "dueAt": NOW}
    data.pop(field)
    with pytest.raises(PydanticValidationError):
        STasksCreate.model_validate(data)


@pytest.mark.parametrize("field", ["title", "type", "dueAt", "ownerId", "status"])
def test_patch_rejects_explicit_required_null(field):
    with pytest.raises(PydanticValidationError):
        STasksUpdate.model_validate({field: None})
    assert STasksUpdate().model_dump(exclude_unset=True) == {}


def test_empty_patch_is_a_read_without_history_or_write(crm):
    task = crm.add_task()
    result = asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(), crm.user))
    assert result["_id"] == str(task["_id"])
    crm.repository.update_by_id.assert_not_awaited()
    crm.history.assert_not_awaited()


@pytest.mark.parametrize("operation", ["read", "update", "delete"])
def test_regular_user_cannot_access_another_owners_task(crm, operation):
    task = crm.add_task(ownerId=crm.other)
    calls = {
        "read": lambda: TasksService.get_by_id(str(task["_id"]), crm.user),
        "update": lambda: TasksService.update(str(task["_id"]), STasksUpdate(title="Changed"), crm.user),
        "delete": lambda: TasksService.soft_delete(str(task["_id"]), crm.user),
    }
    with pytest.raises(ForbiddenError):
        asyncio.run(calls[operation]())
    crm.repository.update_by_id.assert_not_awaited()


def test_regular_user_cannot_assign_or_reassign_tasks(crm):
    with pytest.raises(ForbiddenError):
        asyncio.run(TasksService.create(STasksCreate(title="Call", dueAt=NOW, ownerId=crm.other), crm.user))
    task = crm.add_task()
    with pytest.raises(ForbiddenError):
        asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(ownerId=crm.other), crm.user))
    crm.repository.create.assert_not_awaited()
    crm.repository.update_by_id.assert_not_awaited()


def test_regular_list_is_owner_scoped_and_cannot_filter_another_owner(crm):
    asyncio.run(TasksService.list_tasks(STasksFilters(), STasksPagination(page=3, pageSize=20), crm.user))
    kwargs = crm.repository.find_paginated.await_args.kwargs
    assert kwargs["filter_by"] == {"deletedAt": None, "ownerId": crm.owner}
    assert kwargs["skip"] == 40 and kwargs["limit"] == 20
    assert kwargs["sort"] == [("dueAt", 1), ("_id", 1)]
    with pytest.raises(ForbiddenError):
        asyncio.run(TasksService.list_tasks(STasksFilters(ownerId=crm.other), STasksPagination(), crm.user))


@pytest.mark.parametrize("role", ["admin", "manager"])
def test_privileged_users_can_read_other_tasks_and_filter_any_owner(crm, role):
    caller = SUsersGet(_id=crm.admin.id, **{role: True})
    task = crm.add_task(ownerId=crm.other)
    assert asyncio.run(TasksService.get_by_id(str(task["_id"]), caller))["ownerId"] == str(crm.other)
    asyncio.run(TasksService.list_tasks(STasksFilters(), STasksPagination(), caller))
    assert "ownerId" not in crm.repository.find_paginated.await_args.kwargs["filter_by"]
    asyncio.run(TasksService.list_tasks(STasksFilters(ownerId=crm.other), STasksPagination(), caller))
    assert crm.repository.find_paginated.await_args.kwargs["filter_by"]["ownerId"] == crm.other


@pytest.mark.parametrize("field", ["leadId", "dealId"])
def test_privileged_actor_cannot_assign_inaccessible_link_to_regular_assignee(crm, field):
    link_id = crm.lead_id if field == "leadId" else crm.deal_id
    with pytest.raises(ForbiddenError):
        asyncio.run(TasksService.create(
            STasksCreate(title="Call", dueAt=NOW, ownerId=crm.other, **{field: link_id}), crm.admin,
        ))
    crm.repository.create.assert_not_awaited()


def test_reassign_checks_existing_links_against_the_assignee(crm):
    task = crm.add_task(leadId=crm.lead_id, dealId=crm.deal_id, companyId=crm.company_id)
    with pytest.raises(ForbiddenError):
        asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(ownerId=crm.other), crm.admin))
    crm.repository.update_by_id.assert_not_awaited()


def test_privileged_assignee_may_access_links_owned_by_someone_else(crm):
    crm.users[crm.other]["manager"] = True
    task = asyncio.run(TasksService.create(STasksCreate(
        title="Call", dueAt=NOW, ownerId=crm.other, leadId=crm.lead_id,
        dealId=crm.deal_id, companyId=crm.company_id,
    ), crm.admin))
    assert task["ownerId"] == str(crm.other)
    assert task["createdById"] == crm.admin.id


@pytest.mark.parametrize("field", ["leadId", "dealId", "companyId", "ownerId"])
def test_create_requires_active_foreign_records(crm, field):
    caller = crm.admin if field == "ownerId" else crm.user
    with pytest.raises(NotFoundError):
        asyncio.run(TasksService.create(STasksCreate(title="Call", dueAt=NOW, **{field: ObjectId()}), caller))
    crm.repository.create.assert_not_awaited()


@pytest.mark.parametrize("link", ["lead", "deal"])
def test_company_must_match_each_link(crm, link):
    if link == "lead":
        crm.lead["companyId"] = ObjectId()
    else:
        crm.deal["customerId"] = ObjectId()
    with pytest.raises(ValidationError):
        asyncio.run(TasksService.create(STasksCreate(
            title="Call", dueAt=NOW, companyId=crm.company_id,
            **{f"{link}Id": crm.lead_id if link == "lead" else crm.deal_id},
        ), crm.user))
    crm.repository.create.assert_not_awaited()


def test_combined_lead_deal_requires_source_lead_and_matching_company(crm):
    data = STasksCreate(title="Call", dueAt=NOW, leadId=crm.lead_id, dealId=crm.deal_id)
    crm.deal["sourceLeadId"] = ObjectId()
    with pytest.raises(ValidationError):
        asyncio.run(TasksService.create(data, crm.user))
    crm.deal["sourceLeadId"] = crm.lead_id
    crm.deal["customerId"] = ObjectId()
    with pytest.raises(ValidationError):
        asyncio.run(TasksService.create(data, crm.user))


@pytest.mark.parametrize("link", ["lead", "deal"])
@pytest.mark.parametrize("operation", ["read", "update", "delete", "list"])
def test_historical_task_rechecks_link_access_even_after_conversion(crm, link, operation):
    crm.lead["dealId"] = crm.deal_id
    crm.lead["conversionDealId"] = crm.deal_id
    if link == "lead":
        crm.lead["ownerId"] = crm.other
    else:
        crm.deal["userId"] = crm.other
    task = crm.add_task(status="completed", **{f"{link}Id": crm.lead_id if link == "lead" else crm.deal_id})
    crm.repository.find_paginated.return_value = PaginatedResponse(
        items=[task], total=1, page=1, page_size=100, total_pages=1, has_next=False, has_prev=False,
    )
    calls = {
        "read": lambda: TasksService.get_by_id(str(task["_id"]), crm.user),
        "update": lambda: TasksService.update(str(task["_id"]), STasksUpdate(comment="Changed"), crm.user),
        "delete": lambda: TasksService.soft_delete(str(task["_id"]), crm.user),
        "list": lambda: TasksService.list_tasks(STasksFilters(), STasksPagination(), crm.user),
    }
    with pytest.raises(ForbiddenError):
        asyncio.run(calls[operation]())
    crm.repository.update_by_id.assert_not_awaited()


def test_converted_lead_history_remains_readable_by_owner(crm):
    crm.lead.update(dealId=crm.deal_id, conversionDealId=crm.deal_id)
    task = crm.add_task(leadId=crm.lead_id, dealId=crm.deal_id, status="completed")
    result = asyncio.run(TasksService.get_by_id(str(task["_id"]), crm.user))
    assert result["leadId"] == str(crm.lead_id)
    with pytest.raises(ForbiddenError):
        asyncio.run(TasksService.get_by_id(str(task["_id"]), SUsersGet(_id=crm.other)))


def test_patch_explicit_null_clears_optional_fields_and_records_old_lead(crm):
    task = crm.add_task(
        companyId=crm.company_id, leadId=crm.lead_id, dealId=crm.deal_id,
        comment="Old comment", result="Old result",
    )
    cleared = {field: None for field in ("companyId", "leadId", "dealId", "comment", "result")}
    result = asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(**cleared), crm.user))
    assert all(result[field] is None for field in cleared)
    assert result["title"] == task["title"] and result["type"] == "call"
    assert crm.history.await_args.args[:3] == (str(crm.lead_id), crm.user, "task_updated")
    assert isinstance(crm.history.await_args.args[3], str)


@pytest.mark.parametrize("field", ["leadId", "companyId"])
@pytest.mark.parametrize("value", [None, "507f1f77bcf86cd799439011"])
def test_followup_cannot_change_source_relations(crm, field, value):
    task = crm.add_task(followUp=True, leadId=crm.lead_id, companyId=crm.company_id)
    with pytest.raises(ValidationError):
        asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(**{field: value}), crm.user))
    crm.repository.update_by_id.assert_not_awaited()


def test_followup_due_date_patch_synchronizes_lead_and_keeps_same_relations(crm):
    task = crm.add_task(followUp=True, leadId=crm.lead_id, companyId=crm.company_id)
    new_due = NOW + timedelta(days=1)
    result = asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(
        dueAt=new_due, leadId=str(crm.lead_id), companyId=str(crm.company_id),
    ), crm.user))
    assert result["dueAt"] == crm.lead["nextContactAt"] == new_due
    assert crm.lead["followUpTaskId"] == task["_id"]
    assert crm.history.await_args.args[2] == "task_updated"


@pytest.mark.parametrize("status,kind", [("completed", "task_completed"), ("cancelled", "task_cancelled")])
def test_followup_terminal_status_clears_reminder_and_records_event(crm, status, kind):
    task = crm.add_task(followUp=True, leadId=crm.lead_id, companyId=crm.company_id)
    result = asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(
        status=status, result="Customer contacted",
    ), crm.user))
    assert result["status"] == status and result["result"] == "Customer contacted"
    assert crm.lead["nextContactAt"] is None and crm.lead["followUpTaskId"] is None
    assert crm.history.await_args.args[2] == kind
    assert isinstance(crm.history.await_args.args[3], str)
    if status == "completed":
        assert crm.history.await_args.args[3] == "Customer contacted"
    assert crm.history.await_args.kwargs["details"]["taskId"] == str(task["_id"])


@pytest.mark.parametrize("event", ["create", "update", "complete", "cancel", "delete"])
def test_all_history_events_have_russian_fallback_comments(crm, event):
    if event == "create":
        asyncio.run(TasksService.create(STasksCreate(title="Call", dueAt=NOW, leadId=crm.lead_id), crm.user))
    else:
        task = crm.add_task(leadId=crm.lead_id)
        if event == "delete":
            asyncio.run(TasksService.soft_delete(str(task["_id"]), crm.user))
        else:
            changes = {"update": {"title": "Changed"}, "complete": {"status": "completed"},
                       "cancel": {"status": "cancelled"}}[event]
            asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(**changes), crm.user))
    comment = crm.history.await_args.args[3]
    assert isinstance(comment, str) and comment.strip()
    assert any("\u0400" <= char <= "\u04ff" for char in comment)


def test_followup_soft_delete_clears_reminder_and_is_no_longer_readable(crm):
    task = crm.add_task(followUp=True, leadId=crm.lead_id)
    result = asyncio.run(TasksService.soft_delete(str(task["_id"]), crm.user))
    assert result["deletedAt"] == result["updatedAt"] == NOW
    assert crm.lead["nextContactAt"] is None and crm.lead["followUpTaskId"] is None
    assert crm.history.await_args.args[2] == "task_deleted"
    with pytest.raises(NotFoundError):
        asyncio.run(TasksService.get_by_id(str(task["_id"]), crm.user))


def test_older_followup_completion_does_not_clear_newer_reminder(crm):
    task = crm.add_task(followUp=True, leadId=crm.lead_id)
    new_task_id = ObjectId()
    next_contact = NOW + timedelta(days=2)
    crm.lead.update(followUpTaskId=new_task_id, nextContactAt=next_contact)
    asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(status="completed"), crm.user))
    assert crm.lead["followUpTaskId"] == new_task_id and crm.lead["nextContactAt"] == next_contact


@pytest.mark.parametrize("blocked_field", ["dealId", "conversionDealId", "deletedAt", None])
def test_reopening_followup_cannot_resurrect_converted_or_deleted_lead(crm, blocked_field):
    task = crm.add_task(followUp=True, leadId=crm.lead_id, status="completed")
    crm.lead.update(followUpTaskId=None, nextContactAt=None)
    if blocked_field:
        crm.lead[blocked_field] = NOW if blocked_field == "deletedAt" else crm.deal_id
    call = TasksService.update(str(task["_id"]), STasksUpdate(status="open"), crm.user)
    if blocked_field == "deletedAt":
        with pytest.raises(NotFoundError):
            asyncio.run(call)
    else:
        asyncio.run(call)
    if blocked_field:
        assert crm.lead["nextContactAt"] is None and crm.lead["followUpTaskId"] is None
    else:
        assert crm.lead["nextContactAt"] == NOW and crm.lead["followUpTaskId"] == task["_id"]


@pytest.mark.parametrize("blocked_field", ["dealId", "conversionDealId"])
def test_rescheduling_open_followup_does_not_restore_converted_reminder(crm, blocked_field):
    task = crm.add_task(followUp=True, leadId=crm.lead_id)
    crm.lead.update(nextContactAt=None, followUpTaskId=task["_id"])
    crm.lead[blocked_field] = crm.deal_id
    asyncio.run(TasksService.update(str(task["_id"]), STasksUpdate(dueAt=NOW + timedelta(days=1)), crm.user))
    assert crm.lead["nextContactAt"] is None


@pytest.mark.parametrize("bucket,bounds", [
    ("today", {"$gte": datetime(2026, 10, 11, 21, tzinfo=timezone.utc),
               "$lt": datetime(2026, 10, 12, 21, tzinfo=timezone.utc)}),
    ("overdue", {"$lt": NOW}),
    ("upcoming", {"$gte": datetime(2026, 10, 12, 21, tzinfo=timezone.utc)}),
])
def test_moscow_bucket_bounds_are_utc_and_only_open(crm, bucket, bounds):
    asyncio.run(TasksService.list_tasks(STasksFilters(bucket=bucket), STasksPagination(), crm.user))
    query = crm.repository.find_paginated.await_args.kwargs["filter_by"]
    assert query["dueAt"] == bounds and query["status"] == "open"
    if bucket == "overdue":
        assert NOW - timedelta(hours=1) < query["dueAt"]["$lt"]
        assert not NOW < query["dueAt"]["$lt"]


@pytest.mark.parametrize("now,start,end", [
    (datetime(2026, 3, 8, 12, tzinfo=timezone.utc), datetime(2026, 3, 8, 5, tzinfo=timezone.utc),
     datetime(2026, 3, 9, 4, tzinfo=timezone.utc)),
    (datetime(2026, 11, 1, 12, tzinfo=timezone.utc), datetime(2026, 11, 1, 4, tzinfo=timezone.utc),
     datetime(2026, 11, 2, 5, tzinfo=timezone.utc)),
    (datetime(2026, 10, 12, 22, tzinfo=timezone.utc), datetime(2026, 10, 12, 21, tzinfo=timezone.utc),
     datetime(2026, 10, 13, 21, tzinfo=timezone.utc)),
])
def test_today_handles_dst_and_local_date_rollover(crm, monkeypatch, now, start, end):
    monkeypatch.setattr(tasks_service, "utc_now", lambda: now)
    zone = "Europe/Moscow" if now.month == 10 else "America/New_York"
    asyncio.run(TasksService.list_tasks(STasksFilters(bucket="today", timezone=zone), STasksPagination(), crm.user))
    assert crm.repository.find_paginated.await_args.kwargs["filter_by"]["dueAt"] == {"$gte": start, "$lt": end}


def test_date_only_range_includes_entire_local_end_day(crm):
    asyncio.run(TasksService.list_tasks(
        STasksFilters(dateFrom=date(2026, 10, 12), dateTo=date(2026, 10, 12)), STasksPagination(), crm.user,
    ))
    assert crm.repository.find_paginated.await_args.kwargs["filter_by"]["dueAt"] == {
        "$gte": datetime(2026, 10, 11, 21, tzinfo=timezone.utc),
        "$lt": datetime(2026, 10, 12, 21, tzinfo=timezone.utc),
    }


def test_date_filters_intersect_bucket_instead_of_overwriting_it(crm):
    asyncio.run(TasksService.list_tasks(
        STasksFilters(dateFrom=NOW, dateTo=NOW + timedelta(hours=1), bucket="today"), STasksPagination(), crm.user,
    ))
    query = crm.repository.find_paginated.await_args.kwargs["filter_by"]
    assert query["$and"] == [
        {"dueAt": {"$gte": NOW, "$lte": NOW + timedelta(hours=1)}},
        {"dueAt": {"$gte": datetime(2026, 10, 11, 21, tzinfo=timezone.utc),
                   "$lt": datetime(2026, 10, 12, 21, tzinfo=timezone.utc)}},
    ]


@pytest.mark.parametrize("filters", [
    {"timezone": "Bad/Timezone"}, {"timezone": ""},
    {"dateFrom": NOW + timedelta(days=1), "dateTo": NOW},
    {"bucket": "today", "status": "completed"}, {"bucket": "overdue", "status": "cancelled"},
])
def test_invalid_date_queries_raise_app_error_before_read(crm, filters):
    with pytest.raises(ValidationError):
        asyncio.run(TasksService.list_tasks(STasksFilters(**filters), STasksPagination(), crm.user))
    crm.repository.find_paginated.assert_not_awaited()


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_repository_write_failure_raises_app_error_without_history(crm, operation):
    task = crm.add_task()
    crm.repository.create.side_effect = None
    crm.repository.create.return_value = None
    crm.repository.update_by_id.side_effect = None
    crm.repository.update_by_id.return_value = None
    calls = {
        "create": lambda: TasksService.create(STasksCreate(title="Call", dueAt=NOW), crm.user),
        "update": lambda: TasksService.update(str(task["_id"]), STasksUpdate(title="Changed"), crm.user),
        "delete": lambda: TasksService.soft_delete(str(task["_id"]), crm.user),
    }
    with pytest.raises(InternalError):
        asyncio.run(calls[operation]())
    crm.history.assert_not_awaited()


def test_router_crud_and_response_ids(client, crm):
    created = client.post("/tasks", json={"title": "Call", "dueAt": NOW.isoformat()})
    assert created.status_code == 201
    task = created.json()
    assert task["createdById"] == task["ownerId"] == str(crm.owner)
    assert task["followUp"] is False
    task_id = task["_id"]
    assert client.get(f"/tasks/{task_id}").status_code == 200
    updated = client.patch(f"/tasks/{task_id}", json={"status": "completed", "result": "Reached customer"})
    assert updated.status_code == 200 and updated.json()["result"] == "Reached customer"
    assert client.delete(f"/tasks/{task_id}").json()["deletedAt"] is not None
    assert client.get(f"/tasks/{task_id}").status_code == 404


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": 1_000_001}, {"pageSize": 0}, {"pageSize": 101},
    {"ownerId": "bad"}, {"leadId": "bad"}, {"dateFrom": "2026-10-12T13:30:00"},
    {"timezone": "Bad/Timezone"}, {"bucket": "bad"}, {"status": "done"},
])
def test_router_rejects_invalid_list_queries(client, params):
    assert client.get("/tasks", params=params).status_code == 422


def test_router_list_accepts_all_filters_and_serializes_pagination(client, crm):
    result = client.get("/tasks", params={
        "page": 2, "pageSize": 10, "ownerId": str(crm.owner), "companyId": str(crm.company_id),
        "leadId": str(crm.lead_id), "dealId": str(crm.deal_id), "status": "open", "type": "meeting",
        "dateFrom": "2026-10-12", "dateTo": "2026-10-13", "bucket": "upcoming",
        "timezone": "Europe/Moscow",
    })
    assert result.status_code == 200
    assert set(result.json()) == {"items", "total", "page", "pageSize", "totalPages", "hasNext", "hasPrev"}
    kwargs = crm.repository.find_paginated.await_args.kwargs
    assert kwargs["skip"] == 10 and kwargs["limit"] == 10
    query = kwargs["filter_by"]
    assert query["leadId"] == crm.lead_id and query["dealId"] == crm.deal_id
    assert query["companyId"] == crm.company_id and query["type"] == "meeting"
    assert query["status"] == "open" and len(query["$and"]) == 2


def test_every_route_requires_current_user():
    assert len(router.routes) == 5
    for route in router.routes:
        assert get_current_user in {dependency.call for dependency in route.dependant.dependencies}


def test_openapi_generation_includes_created_by_and_patch_routes(client):
    document = client.get("/openapi.json")
    assert document.status_code == 200
    schemas = document.json()["components"]["schemas"]
    assert "createdById" in schemas["STasks"]["properties"]
    assert "patch" in document.json()["paths"]["/tasks/{id}"]


def test_task_dates_decoded_from_mongo_keep_utc_in_http_response(client, crm):
    task = crm.add_task(dueAt=NOW.replace(tzinfo=None))
    response = client.get(f"/tasks/{task['_id']}")
    assert response.status_code == 200
    assert response.json()["dueAt"] == "2026-10-12T10:30:00Z"
