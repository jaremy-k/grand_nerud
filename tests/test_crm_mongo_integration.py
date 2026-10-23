"""Opt-in checks against disposable loopback MongoDB; never use application DB settings."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient

from app.calculation_rules import repository as rules_repo
from app.calculation_rules.service import CalculationRulesService
from app.calculator_config import repository as config_repo
from app.calculator_config.service import CalculatorConfigService
from app.companies.router import router as companies_router
from app.companies.service import CompaniesService
from app.deals.numbering import initialize_deal_numbers
from app.deals.repository import DealsRepository
from app.deals.router import router as deals_router
from app.deals.service import DealsService
from app.exceptions import AppError
from app.repositories.mongo import MongoRepository
from app.users import dependencies
from app.users.auth import create_access_token
from app.workspace.repository import WorkspaceRepository
from app.workspace.router import router as workspace_router
from app.workspace.service import WorkspaceService


@pytest.mark.skipif(not os.getenv("CRM_TEST_MONGO_URI"), reason="Requires disposable loopback MongoDB")
def test_crm_routes_on_real_mongodb(monkeypatch):
    uri = os.environ["CRM_TEST_MONGO_URI"]
    assert urlparse(uri).hostname in {"127.0.0.1", "localhost", "::1"}, "Only disposable local MongoDB is allowed"

    async def scenario():
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        database_name = f"crm_test_{uuid4().hex}"
        db = client[database_name]
        try:
            await client.admin.command("ping")
            companies_repo = type(CompaniesService.repository)(db.companies)
            deals_repo = DealsRepository(db.deals, db.counters)
            monkeypatch.setattr(CompaniesService, "repository", companies_repo)
            monkeypatch.setattr(DealsService, "repository", deals_repo)
            monkeypatch.setattr(dependencies, "users_repository", MongoRepository(db.users))
            monkeypatch.setattr(config_repo, "_collection", db.calculator_config)
            monkeypatch.setattr(rules_repo, "_collection", db.calculation_rules)
            monkeypatch.setattr(CalculatorConfigService, "_cache", None)
            monkeypatch.setattr(CalculationRulesService, "_active_cache", None)
            monkeypatch.setattr(CalculationRulesService, "_active_cache_id", None)
            workspace_repo = WorkspaceRepository()
            workspace_repo.tasks_collection, workspace_repo.leads_collection = db.tasks, db.leads
            monkeypatch.setattr(WorkspaceService, "repository", workspace_repo)
            await CalculationRulesService.seed_default_rule_if_empty()

            manager, employee, other = ObjectId(), ObjectId(), ObjectId()
            await db.users.insert_many([{"_id": identifier, "name": name, "manager": identifier == manager}
                                        for identifier, name in [(manager, "Manager"), (employee, "Employee"), (other, "Other")]])
            headers = lambda identifier: {"Authorization": f"Bearer {create_access_token({'sub': str(identifier)})}"}
            items = [{"_id": ObjectId(), "name": f"Company {index:02d}", "inn": 7700000000 + index,
                      "roles": ["provider", "customer"], "phones": ["111", "222"], "contacts": [{"Director": "FNS"}]}
                     for index in range(37)]
            await db.companies.insert_many(items)
            material, service, stage = ObjectId(), ObjectId(), ObjectId()
            await db.materials.insert_one({"_id": material, "name": "Sand"})
            await db.services.insert_one({"_id": service, "name": "Sales", "kind": "sales"})
            await db.stages.insert_one({"_id": stage, "name": "New"})
            await db.adresses.insert_many([
                {"companyId": items[index]["_id"], "city": "Москва", "district": "Раменки", "administrativeDistrict": "ЗАО"}
                for index in range(20)])
            await db.company_materials.insert_many([
                {"companyId": items[index]["_id"], "materialId": material, "price": 1000 + index,
                 "unit": "тонна" if index % 2 else "т"} for index in range(20)
            ] + [{"companyId": items[25]["_id"], "materialId": material, "price": 1, "unit": "м³"}])

            # Backfill includes archived records and stays idempotent before concurrent writes.
            legacy = [ObjectId(), ObjectId()]
            await db.deals.insert_many([{"_id": identifier, "createdAt": datetime.now(timezone.utc),
                                        "deletedAt": datetime.now(timezone.utc)} for identifier in legacy])
            await initialize_deal_numbers(db.deals, db.counters)
            old_numbers = [doc["number"] async for doc in db.deals.find()]
            await initialize_deal_numbers(db.deals, db.counters)
            assert [doc["number"] async for doc in db.deals.find()] == old_numbers

            app = FastAPI()
            for router in (companies_router, deals_router, workspace_router):
                app.include_router(router)

            @app.exception_handler(AppError)
            async def error_handler(_request, exc):
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
                assert (await http.get("/companies/page")).status_code == 401
                first = await http.get("/companies/page", params={"role": "provider", "pageSize": 15}, headers=headers(employee))
                assert first.status_code == 200, first.text
                first = first.json()
                second = (await http.get("/companies/page", params={"page": 2, "pageSize": 15}, headers=headers(employee))).json()
                assert first["total"] == second["total"] == 37
                assert not {row["_id"] for row in first["items"]} & {row["_id"] for row in second["items"]}
                search = (await http.get("/companies/page", params={"search": "7700000000"}, headers=headers(employee))).json()
                assert search["total"] == 1 and search["items"][0]["name"] == "Company 00"
                query = {"materialId": str(material), "priceUnit": "т", "priceSort": "asc", "city": "Москва",
                         "district": "Раменки", "maxPrice": 1018, "includeDetails": "true", "pageSize": 3, "page": 2}
                filtered = await http.get("/companies/page", params=query, headers=headers(employee))
                assert filtered.status_code == 200, filtered.text
                filtered = filtered.json()
                assert filtered["total"] == 19
                assert [row["materialsWithPrices"][0]["price"] for row in filtered["items"]] == [1003, 1004, 1005]
                assert all(row["addresses"] and "purchases" not in row for row in filtered["items"])
                contact_payload = {"phones": ["111", "222", "333"], "emails": ["one@example.com", "two@example.com"],
                                   "contactPersons": [{"name": "Person", "phones": ["444", "555"], "emails": ["a@example.com", "b@example.com"]}]}
                updated = await http.patch(f"/companies/{items[0]['_id']}", json=contact_payload, headers=headers(employee))
                assert updated.status_code == 200, updated.text
                assert updated.json()["contactPersons"][0]["phones"] == ["444", "555"]
                assert updated.json()["contacts"] == [{"Director": "FNS"}]

                payload = {"serviceId": str(service), "customerId": str(items[0]["_id"]), "providerId": str(items[1]["_id"]),
                           "stageId": str(stage), "materialId": str(material), "quantity": 10, "unitMeasurement": "тонна",
                           "amountPurchaseUnit": 1000, "amountSalesUnit": 1500, "paymentMethod": "наличный расчет"}
                responses = await asyncio.gather(*(http.post("/deals", json=payload, headers=headers(employee if index % 2 else other)) for index in range(20)))
                assert all(response.status_code == 201 for response in responses), [response.text for response in responses if response.status_code != 201]
                numbers = [response.json()["number"] for response in responses]
                assert len(set(numbers + old_numbers)) == 22
                one = responses[1].json()
                revised = await http.patch(f"/deals/{one['_id']}", json={"number": "HACK", "numberSequence": 1, "notes": "Updated"}, headers=headers(employee))
                assert revised.status_code == 200 and revised.json()["number"] == one["number"]
                own = await http.get("/deals", params={"search": "Sand", "userId": str(other), "includeRelations": "true", "sortBy": "numberSequence", "sortOrder": "asc"}, headers=headers(employee))
                assert own.status_code == 200, own.text
                own = own.json()
                assert own["total"] == 10 and all(row["userId"] == str(employee) for row in own["items"])
                assert [row["numberSequence"] for row in own["items"]] == sorted(row["numberSequence"] for row in own["items"])
                exact = (await http.get("/deals", params={"search": one["number"]}, headers=headers(manager))).json()
                assert exact["total"] == 1 and exact["items"][0]["_id"] == one["_id"]

                root = f"/deals/{one['_id']}"
                assert (await http.get(f"{root}/operations", headers=headers(other))).status_code == 403
                current = (await http.get(f"{root}/operations", headers=headers(employee))).json()
                original_revision = current["revision"]
                planned = {"revision": original_revision, "requestId": str(uuid4()), "status": "planned", "quantity": "6", "unit": "т", "plannedDate": "2026-10-01"}
                scheduled = await http.post(f"{root}/shipments", json=planned, headers=headers(employee))
                assert scheduled.status_code == 201, scheduled.text
                current = scheduled.json()
                assert current["summary"]["plannedQuantity"] == 6 and current["summary"]["deliveredQuantity"] == 0
                competitors = [{**planned, "revision": current["revision"], "requestId": str(uuid4()), "quantity": "3"} for _ in range(2)]
                raced = await asyncio.gather(*(http.post(f"{root}/shipments", json=row, headers=headers(employee)) for row in competitors))
                assert sorted(response.status_code for response in raced) == [201, 409]
                current = (await http.get(f"{root}/operations", headers=headers(employee))).json()
                too_much = await http.post(f"{root}/shipments", json={**planned, "revision": current["revision"], "requestId": str(uuid4()), "quantity": "2"}, headers=headers(employee))
                assert too_much.status_code == 422
                first_shipment = current["shipments"][0]
                delivered = await http.patch(f"{root}/shipments/{first_shipment['_id']}", json={**planned, "revision": current["revision"], "status": "delivered", "quantity": "4", "actualDate": "2026-10-01", "amountPurchase": "3900"}, headers=headers(employee))
                assert delivered.status_code == 200, delivered.text
                current = delivered.json()
                assert current["summary"]["remainingQuantity"] == 6 and current["summary"]["unplannedQuantity"] == 3
                refreshed = (await http.get(root, headers=headers(employee))).json()
                assert refreshed["totalDeliveredQuantity"] == 4 and refreshed["actualAmountPurchaseTotal"] == 3900
                assert "_operations" not in refreshed
                assert refreshed["operationsSummary"]["executionStatus"] == "partial"
                assert refreshed["operationsRevision"] == current["revision"]
                edit_from_detail = await http.patch(root, json={"notes": "Changed after shipment", "operationsRevision": refreshed["operationsRevision"]}, headers=headers(employee))
                assert edit_from_detail.status_code == 200, edit_from_detail.text
                current = (await http.get(f"{root}/operations", headers=headers(employee))).json()
                assert (await http.patch(root, json={"notes": "Outdated", "operationsRevision": original_revision}, headers=headers(employee))).status_code == 409
                assert (await http.patch(root, json={"quantity": 5, "operationsRevision": current["revision"]}, headers=headers(employee))).status_code == 422
                assert (await http.patch(root, json={"deliveredQuantity": [], "operationsRevision": current["revision"]}, headers=headers(employee))).status_code == 409
                posted = {"revision": current["revision"], "requestId": str(uuid4()), "status": "paid", "kind": "customer", "amount": "5000.10", "actualDate": "2026-10-01"}
                repeated = await asyncio.gather(*(http.post(f"{root}/payments", json=posted, headers=headers(employee)) for _ in range(3)))
                assert all(response.status_code == 201 for response in repeated), [response.text for response in repeated]
                current = (await http.get(f"{root}/operations", headers=headers(employee))).json()
                assert len(current["payments"]) == 1 and current["summary"]["customerPaid"] == 5000.1
                assert current["summary"]["customerDebt"] == 9999.9
                payment_id = current["payments"][0]["_id"]
                cancelled = await http.post(f"{root}/payments/{payment_id}/cancel", json={"revision": current["revision"], "reason": "Ошибочная запись"}, headers=headers(employee))
                assert cancelled.status_code == 200 and cancelled.json()["summary"]["customerPaid"] == 0
                assert cancelled.json()["history"]["items"][0]["before"]["amount"] == 5000.1
                assert (await http.delete(root, headers=headers(employee))).status_code == 409

                retry_id = ObjectId()
                retries = await asyncio.gather(*(deals_repo.create({"_id": retry_id, "userId": employee}) for _ in range(10)))
                assert len({row["number"] for row in retries}) == 1
                now = datetime.now(timezone.utc)
                await db.tasks.insert_many([{"ownerId": employee, "title": "Call", "type": "call", "status": "open", "dueAt": now - timedelta(days=1)} for _ in range(8)]
                                           + [{"ownerId": other, "title": "Other", "type": "call", "status": "open", "dueAt": now - timedelta(days=1)}])
                tasks = await http.get("/workspace/tasks", params={"limit": 3}, headers=headers(employee))
                assert tasks.status_code == 200, tasks.text
                assert tasks.json()["overdue"]["total"] == 8 and tasks.json()["overdue"]["hasMore"]
                assert len(tasks.json()["overdue"]["items"]) == 3
                assert (await http.get("/workspace/tasks", params={"scope": "team"}, headers=headers(employee))).status_code == 403
                assert (await http.get("/workspace/tasks", params={"scope": "team"}, headers=headers(manager))).json()["overdue"]["total"] == 9
        finally:
            await client.drop_database(database_name)
            client.close()

    asyncio.run(scenario())
