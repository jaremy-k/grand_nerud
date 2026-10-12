import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.crm import utc_now
from app.core.mongo_utils import convert_objectids_to_str
from app.core.pagination import PaginatedResponse
from app.deals.service import DealsService
from app.exceptions import ConflictError, ForbiddenError, ValidationError
from app.lead_stages.service import LeadStagesService
from app.leads.activities import LeadActivitiesService
from app.leads.service import LeadsService
from app.leads.shemas import SLeadCreate, SLeadUpdate
from app.deals.shemas import SDealsInput
from app.tasks.service import TasksService
from app.tasks.shemas import STasksCreate, STasksFilters, STasksPagination, STasksUpdate
from app.users.shemas import SUsersGet


class MemoryRepository:
    def __init__(self, records=()):
        self.records = {record["_id"]: deepcopy(record) for record in records}

    @staticmethod
    def matches(record, query):
        for field, value in query.items():
            current = record.get(field)
            if isinstance(value, dict):
                if "$ne" in value and current == value["$ne"]:
                    return False
                if "$in" in value and current not in value["$in"]:
                    return False
            elif current != value:
                return False
        return True

    async def find_one(self, filter_by=None, **kwargs):
        query = {**(filter_by or {}), **kwargs}
        return next((deepcopy(r) for r in self.records.values() if self.matches(r, query)), None)

    async def find_many(self, filter_by=None, sort=None, limit=100, **kwargs):
        query = {**(filter_by or {}), **kwargs}
        rows = [deepcopy(r) for r in self.records.values() if self.matches(r, query)]
        return rows[:limit] if limit else rows

    async def count(self, filter_by=None, **kwargs):
        return len(await self.find_many(filter_by, limit=0, **kwargs))

    async def create(self, document):
        document = deepcopy(document)
        document.setdefault("_id", ObjectId())
        if document["_id"] in self.records:
            return None
        self.records[document["_id"]] = document
        return deepcopy(document)

    async def add_role(self, company_id, role):
        record = self.records[company_id]
        record.setdefault("roles", [])
        if role not in record["roles"]:
            record["roles"].append(role)
        return deepcopy(record)

    async def update_by_id(self, object_id, update_data):
        oid = ObjectId(object_id)
        if oid not in self.records:
            return None
        self.records[oid].update(deepcopy(update_data))
        return deepcopy(self.records[oid])

    async def update_followup(self, task, payload):
        current = self.records[task["_id"]]
        if current.get("status") != "open" or current.get("updatedAt") != task.get("updatedAt"):
            return None
        return await self.update_by_id(task["_id"], payload)

    async def update_many(self, filter_by, update_data):
        count = 0
        for row in self.records.values():
            if self.matches(row, filter_by):
                row.update(deepcopy(update_data))
                count += 1
        return count

    async def aggregate(self, pipeline):
        return await self.find_many(pipeline[0]["$match"], limit=0)

    async def find_paginated(self, filter_by=None, skip=0, limit=100, sort=None, **kwargs):
        rows = await self.find_many(filter_by, limit=0, **kwargs)
        return PaginatedResponse(
            items=convert_objectids_to_str(rows[skip:skip + limit]), total=len(rows),
            page=skip // limit + 1, page_size=limit, total_pages=(len(rows) + limit - 1) // limit,
            has_next=skip + limit < len(rows), has_prev=skip > 0,
        )

    async def update_unconverted(self, lead, payload):
        current = self.records[lead["_id"]]
        if current.get("conversionDealId") or current.get("dealId") or current["updatedAt"] != lead["updatedAt"]:
            return None
        return await self.update_by_id(lead["_id"], payload)

    async def attach_followup(self, lead, task_id):
        current = self.records[lead["_id"]]
        if current.get("deletedAt") or current.get("dealId") or current.get("conversionDealId"):
            return None
        if current["updatedAt"] != lead["updatedAt"] or current.get("nextContactAt") != lead.get("nextContactAt"):
            return None
        return await self.update_by_id(lead["_id"], {"followUpTaskId": task_id})

    async def clear_followup(self, lead):
        current = self.records[lead["_id"]]
        if current["updatedAt"] != lead["updatedAt"] or current.get("followUpTaskId") != lead.get("followUpTaskId"):
            return None
        return await self.update_by_id(lead["_id"], {"nextContactAt": None, "followUpTaskId": None, "updatedAt": utc_now()})

    async def reserve_conversion(self, lead, payload, deal_id, document):
        return await self.update_unconverted(lead, {
            "conversionDealId": deal_id, "conversionInput": payload,
            "conversionDocument": document, "updatedAt": utc_now(),
        })


@pytest.fixture
def workflow(monkeypatch):
    user = SUsersGet(_id=str(ObjectId()), name="Менеджер")
    stages = MemoryRepository([
        {"_id": ObjectId(), "kind": kind, "name": kind, "order": order, "deletedAt": None}
        for order, kind in enumerate(("new", "in_progress", "qualified", "deferred", "unqualified", "converted"))
    ])
    leads = MemoryRepository()
    tasks = MemoryRepository()
    activities = MemoryRepository()
    deals = MemoryRepository()
    insert_deal = deals.create
    async def concurrent_insert(document):
        await asyncio.sleep(0)
        return await insert_deal(document)
    monkeypatch.setattr(deals, "create", concurrent_insert)
    monkeypatch.setattr(LeadsService, "repository", leads)
    monkeypatch.setattr(LeadStagesService, "repository", stages)
    monkeypatch.setattr(LeadActivitiesService, "repository", activities)
    monkeypatch.setattr("app.leads.service.tasks_repository", tasks)
    monkeypatch.setattr(TasksService, "repository", tasks)
    monkeypatch.setattr(DealsService, "repository", deals)
    company = {"_id": ObjectId(), "name": "ООО Тест", "roles": ["provider"], "deletedAt": None}
    material = {"_id": ObjectId(), "name": "Песок", "deletedAt": None}
    service = {"_id": ObjectId(), "name": "Продажа", "deletedAt": None}
    deal_stage = {"_id": ObjectId(), "name": "Согласование", "deletedAt": None}
    for field, rows in (
        ("companies_repository", [company]), ("materials_repository", [material]),
        ("services_repository", [service]), ("stages_repository", [deal_stage]),
    ):
        monkeypatch.setattr(f"app.leads.service.{field}", MemoryRepository(rows))
    monkeypatch.setattr(DealsService, "_compute_snapshots", AsyncMock(return_value=({}, str(ObjectId()), 1)))
    monkeypatch.setattr(DealsService, "_enrich_response", AsyncMock(side_effect=lambda deal, user: deal))
    return {
        "user": user, "leads": leads, "tasks": tasks, "activities": activities,
        "deals": deals, "stages": stages, "company": company, "material": material,
        "service": service, "deal_stage": deal_stage,
    }


def stage_id(workflow, kind):
    return str(next(row["_id"] for row in workflow["stages"].records.values() if row["kind"] == kind))


def test_lead_can_exist_before_company_or_material_is_known(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(title="Первый звонок"), workflow["user"])
        assert lead["stageId"] == stage_id(workflow, "new")
        assert lead.get("companyId") is None
        assert lead["materialIds"] == []
        assert len(workflow["activities"].records) == 1
    asyncio.run(scenario())


def test_foreign_owner_cannot_read_or_modify_lead(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(title="Лид"), workflow["user"])
        stranger = SUsersGet(_id=str(ObjectId()))
        with pytest.raises(ForbiddenError):
            await LeadsService.get_by_id(lead["_id"], stranger)
        with pytest.raises(ForbiddenError):
            await LeadsService.update(lead["_id"], SLeadUpdate(notes="Чужая запись"), stranger)
        with pytest.raises(ForbiddenError):
            await LeadsService.create(SLeadCreate(title="Лид", ownerId=stranger.id), workflow["user"])
    asyncio.run(scenario())


def test_deferred_lead_requires_date_and_creates_one_reschedulable_call(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(title="Сезонная закупка"), workflow["user"])
        with pytest.raises(ValidationError):
            await LeadsService.update(lead["_id"], SLeadUpdate(stageId=stage_id(workflow, "deferred")), workflow["user"])
        date = datetime(2027, 3, 15, 9, tzinfo=timezone.utc)
        lead = await LeadsService.update(lead["_id"], SLeadUpdate(
            stageId=stage_id(workflow, "deferred"), nextContactAt=date,
        ), workflow["user"])
        task_id = lead["followUpTaskId"]
        assert len(workflow["tasks"].records) == 1
        assert workflow["tasks"].records[ObjectId(task_id)]["dueAt"] == date
        new_date = datetime(2027, 3, 20, 9, tzinfo=timezone.utc)
        lead = await LeadsService.update(lead["_id"], SLeadUpdate(nextContactAt=new_date), workflow["user"])
        assert lead["followUpTaskId"] == task_id
        assert workflow["tasks"].records[ObjectId(task_id)]["dueAt"] == new_date
    asyncio.run(scenario())


def test_unqualified_lead_requires_reason_and_cancels_followup(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Обработка", nextContactAt=datetime(2027, 3, 15, 9, tzinfo=timezone.utc),
        ), workflow["user"])
        with pytest.raises(ValidationError):
            await LeadsService.update(lead["_id"], SLeadUpdate(stageId=stage_id(workflow, "unqualified")), workflow["user"])
        lead = await LeadsService.update(lead["_id"], SLeadUpdate(
            stageId=stage_id(workflow, "unqualified"), lossReason="Не закупает нерудные материалы",
        ), workflow["user"])
        assert lead["nextContactAt"] is None
        assert next(iter(workflow["tasks"].records.values()))["status"] == "cancelled"
    asyncio.run(scenario())


def test_completing_auto_call_updates_lead_and_records_outcome(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Сезонная закупка", stageId=stage_id(workflow, "deferred"),
            nextContactAt=datetime(2027, 3, 15, 9, tzinfo=timezone.utc),
        ), workflow["user"])
        await TasksService.update(lead["followUpTaskId"], STasksUpdate(
            status="completed", result="Потребность подтверждена",
        ), workflow["user"])
        current = workflow["leads"].records[ObjectId(lead["_id"])]
        assert current["nextContactAt"] is None
        assert current["followUpTaskId"] is None
        event = next(a for a in workflow["activities"].records.values() if a["type"] == "task_completed")
        assert event["comment"] == "Потребность подтверждена"
        assert event["userId"] == ObjectId(workflow["user"].id)
        updated = await LeadsService.update(lead["_id"], SLeadUpdate(notes="Уточняем объём"), workflow["user"])
        assert updated["notes"] == "Уточняем объём"
    asyncio.run(scenario())


def test_conversion_is_idempotent_and_preserves_owner_and_lead_link(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Закупка песка", companyId=str(workflow["company"]["_id"]),
            materialIds=[str(workflow["material"]["_id"])], quantity=100,
        ), workflow["user"])
        data = SDealsInput(serviceId=str(workflow["service"]["_id"]), stageId=str(workflow["deal_stage"]["_id"]), amountSalesUnit=1500)
        with pytest.raises(ConflictError):
            await LeadsService.convert(lead["_id"], data, workflow["user"])
        await LeadsService.update(lead["_id"], SLeadUpdate(stageId=stage_id(workflow, "qualified")), workflow["user"])
        first, second = await asyncio.gather(
            LeadsService.convert(lead["_id"], data, workflow["user"]),
            LeadsService.convert(lead["_id"], data, workflow["user"]),
        )
        assert first["lead"]["dealId"] == second["lead"]["dealId"]
        assert len(workflow["deals"].records) == 1
        deal = next(iter(workflow["deals"].records.values()))
        assert deal["sourceLeadId"] == ObjectId(lead["_id"])
        assert deal["userId"] == ObjectId(workflow["user"].id)
        assert deal["quantity"] == 100
        assert deal["customerId"] == workflow["company"]["_id"]
        from app.leads import service as leads_module
        assert leads_module.companies_repository.records[deal["customerId"]]["roles"] == ["provider", "customer"]
        assert len([a for a in workflow["activities"].records.values() if a["type"] == "converted"]) == 1
        assert "conversionInput" not in first["lead"]
        assert first["lead"]["conversionPending"] is False
    asyncio.run(scenario())


def test_conversion_can_resume_after_deal_creation_before_lead_link_is_saved(workflow, monkeypatch):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Лид", companyId=str(workflow["company"]["_id"]),
            materialIds=[str(workflow["material"]["_id"])], stageId=stage_id(workflow, "qualified"),
        ), workflow["user"])
        data = SDealsInput(serviceId=str(workflow["service"]["_id"]), stageId=str(workflow["deal_stage"]["_id"]))
        update = workflow["leads"].update_by_id
        async def fail_link(oid, payload):
            if "dealId" in payload:
                return None
            return await update(oid, payload)
        monkeypatch.setattr(workflow["leads"], "update_by_id", fail_link)
        from app.exceptions import InternalError
        with pytest.raises(InternalError):
            await LeadsService.convert(lead["_id"], data, workflow["user"])
        monkeypatch.setattr(workflow["leads"], "update_by_id", update)
        result = await LeadsService.convert(lead["_id"], data, workflow["user"])
        assert result["lead"]["stageId"] == stage_id(workflow, "converted")
        assert len(workflow["deals"].records) == 1
    asyncio.run(scenario())


def test_repeated_excel_import_creates_one_initial_lead(workflow):
    async def scenario():
        assert await LeadsService.create_for_import(workflow["company"], workflow["user"])
        assert not await LeadsService.create_for_import(workflow["company"], workflow["user"])
        assert len(workflow["leads"].records) == 1
    asyncio.run(scenario())


def test_http_create_lead_and_stage_validation(workflow):
    from app.main import app
    from app.users.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: workflow["user"]
    try:
        client = TestClient(app)
        response = client.post("/leads", json={"title": "Первичный контакт"})
        assert response.status_code == 201
        assert response.json()["ownerId"] == workflow["user"].id
        bad = client.patch(f"/leads/{response.json()['_id']}", json={"stageId": stage_id(workflow, "converted")})
        assert bad.status_code == 422
        assert "convert" in bad.json()["detail"]
        invalid = client.post("/leads", json={"title": "Лид", "companyId": "not-an-id"})
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_lead_read_rechecks_ownership_after_reassignment(workflow, monkeypatch):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(title="Первый контакт"), workflow["user"])
        aggregate = workflow["leads"].aggregate
        async def reassign_before_fetch(pipeline):
            workflow["leads"].records[ObjectId(lead["_id"])]["ownerId"] = ObjectId()
            workflow["leads"].records[ObjectId(lead["_id"])]["notes"] = "Данные нового менеджера"
            return await aggregate(pipeline)
        monkeypatch.setattr(workflow["leads"], "aggregate", reassign_before_fetch)
        from app.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            await LeadsService.get_by_id(lead["_id"], workflow["user"])
    asyncio.run(scenario())


def test_failed_calculation_does_not_lock_lead(workflow, monkeypatch):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Лид", companyId=str(workflow["company"]["_id"]),
            materialIds=[str(workflow["material"]["_id"])], stageId=stage_id(workflow, "qualified"), quantity=0,
        ), workflow["user"])
        data = SDealsInput(serviceId=str(workflow["service"]["_id"]), stageId=str(workflow["deal_stage"]["_id"]))
        snapshots = AsyncMock(side_effect=ValidationError("Ошибка формулы"))
        monkeypatch.setattr(DealsService, "_compute_snapshots", snapshots)
        with pytest.raises(ValidationError):
            await LeadsService.convert(lead["_id"], data, workflow["user"])
        stored = workflow["leads"].records[ObjectId(lead["_id"])]
        assert stored.get("conversionDealId") is None
        await LeadsService.update(lead["_id"], SLeadUpdate(quantity=10), workflow["user"])
        snapshots.side_effect = None
        snapshots.return_value = ({}, str(ObjectId()), 1)
        result = await LeadsService.convert(lead["_id"], data, workflow["user"])
        assert result["deal"]["quantity"] == 10
    asyncio.run(scenario())


def test_task_list_resolves_deal_ids_after_repository_serialization(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Потребность", companyId=str(workflow["company"]["_id"]),
            materialIds=[str(workflow["material"]["_id"])], stageId=stage_id(workflow, "qualified"),
        ), workflow["user"])
        converted = await LeadsService.convert(lead["_id"], SDealsInput(
            serviceId=str(workflow["service"]["_id"]), stageId=str(workflow["deal_stage"]["_id"]),
        ), workflow["user"])
        task = await TasksService.create(STasksCreate(
            title="Проверить оплату", dueAt=utc_now(), dealId=converted["lead"]["dealId"],
        ), workflow["user"])
        result = await TasksService.list_tasks(STasksFilters(), STasksPagination(), workflow["user"])
        assert result.total == 1
        assert result.items[0]["_id"] == task["_id"]
        assert result.items[0]["dealId"] == converted["lead"]["dealId"]
    asyncio.run(scenario())


def test_deleted_lead_keeps_historical_tasks_readable_and_removable(workflow):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Первичный звонок", nextContactAt=datetime(2027, 3, 15, 9, tzinfo=timezone.utc),
        ), workflow["user"])
        task_id = lead["followUpTaskId"]
        await LeadsService.delete(lead["_id"], workflow["user"])
        task = await TasksService.get_by_id(task_id, workflow["user"])
        assert task["status"] == "cancelled"
        listed = await TasksService.list_tasks(STasksFilters(leadId=lead["_id"]), STasksPagination(), workflow["user"])
        assert listed.total == 1
        assert listed.items[0]["_id"] == task_id
        deleted = await TasksService.soft_delete(task_id, workflow["user"])
        assert deleted["deletedAt"] is not None
    asyncio.run(scenario())


def test_followup_creation_losing_race_with_conversion_is_cancelled(workflow, monkeypatch):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Потребность", companyId=str(workflow["company"]["_id"]),
            materialIds=[str(workflow["material"]["_id"])], stageId=stage_id(workflow, "qualified"),
        ), workflow["user"])
        started, resume = asyncio.Event(), asyncio.Event()
        create = workflow["tasks"].create
        async def slow_create(document):
            started.set()
            await resume.wait()
            return await create(document)
        monkeypatch.setattr(workflow["tasks"], "create", slow_create)
        update = asyncio.create_task(LeadsService.update(lead["_id"], SLeadUpdate(
            nextContactAt=datetime(2027, 3, 15, 9, tzinfo=timezone.utc),
        ), workflow["user"]))
        await started.wait()
        try:
            await LeadsService.convert(lead["_id"], SDealsInput(
                serviceId=str(workflow["service"]["_id"]), stageId=str(workflow["deal_stage"]["_id"]),
            ), workflow["user"])
        finally:
            resume.set()
        await update
        current = workflow["leads"].records[ObjectId(lead["_id"])]
        assert current["dealId"]
        assert current["nextContactAt"] is None
        assert current["followUpTaskId"] is None
        assert all(task["status"] == "cancelled" for task in workflow["tasks"].records.values())
    asyncio.run(scenario())


def test_older_followup_reschedule_does_not_cancel_newer_reschedule(workflow, monkeypatch):
    async def scenario():
        lead = await LeadsService.create(SLeadCreate(
            title="Звонок", nextContactAt=datetime(2027, 3, 1, 9, tzinfo=timezone.utc),
        ), workflow["user"])
        first_date = datetime(2027, 3, 2, 9, tzinfo=timezone.utc)
        second_date = datetime(2027, 3, 3, 9, tzinfo=timezone.utc)
        started, resume = asyncio.Event(), asyncio.Event()
        attach = workflow["leads"].attach_followup
        async def slow_attach(document, task_id):
            if document["nextContactAt"] == first_date:
                started.set()
                await resume.wait()
            return await attach(document, task_id)
        monkeypatch.setattr(workflow["leads"], "attach_followup", slow_attach)
        first = asyncio.create_task(LeadsService.update(lead["_id"], SLeadUpdate(nextContactAt=first_date), workflow["user"]))
        await started.wait()
        try:
            await LeadsService.update(lead["_id"], SLeadUpdate(nextContactAt=second_date), workflow["user"])
        finally:
            resume.set()
        await first
        task = workflow["tasks"].records[ObjectId(lead["followUpTaskId"])]
        assert task["status"] == "open"
        assert task["dueAt"] == second_date
        assert workflow["leads"].records[ObjectId(lead["_id"])]["nextContactAt"] == second_date
    asyncio.run(scenario())


def test_excel_import_skips_archived_company_and_continues_with_valid_rows(workflow, monkeypatch):
    from app.companies.excel_import import ParsedCompanyRow
    from app.companies.service import CompaniesService
    async def scenario():
        archived = {"_id": ObjectId(), "name": "Архив", "inn": "7700000001", "deletedAt": utc_now()}
        active = {"_id": ObjectId(), "name": "Новая", "inn": "7700000002", "deletedAt": None}
        rows = [
            ParsedCompanyRow(2, {"name": archived["name"], "inn": archived["inn"]}),
            ParsedCompanyRow(3, {"name": active["name"], "inn": active["inn"]}),
        ]
        monkeypatch.setattr("app.companies.service.parse_companies_excel", lambda *args, **kw: (rows, []))
        monkeypatch.setattr(CompaniesService, "find_by_inn", AsyncMock(side_effect=[archived, None]))
        monkeypatch.setattr(CompaniesService, "create", AsyncMock(return_value=active))
        monkeypatch.setattr(CompaniesService, "update", AsyncMock())
        create_lead = AsyncMock(return_value=True)
        monkeypatch.setattr(LeadsService, "create_for_import", create_lead)
        report = await CompaniesService.import_excel(b"test", create_leads=True, user=workflow["user"])
        assert report["created"] == 1
        assert report["leadsCreated"] == 1
        assert report["errors"][0]["row"] == 2
        create_lead.assert_awaited_once_with(active, workflow["user"])
        CompaniesService.update.assert_not_awaited()
    asyncio.run(scenario())
