import asyncio
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.deals.operation_schemas import PaymentWrite, ShipmentWrite
from app.deals.operations import delivered_rows, guard_deal_edit, ledger_for, revision, summary
from app.deals.repository import DealsRepository
from app.deals.router import router
from app.deals.service import DealsService
from app.exceptions import AppError, InternalError, ValidationError
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet
from app.core.mongo_utils import serialize_mongo_doc, convert_objectids_to_str
from datetime import datetime, timezone


@pytest.fixture
def api(monkeypatch):
    user = SUsersGet(_id=ObjectId(), name="Manager")
    deal = {"_id": ObjectId(), "userId": ObjectId(user.id), "quantity": 100, "unitMeasurement": "тонна",
            "amountSalesUnit": 10, "amountPurchaseUnit": 5, "deliveredQuantity": []}
    state = {"deal": deal}

    async def read(identifier):
        return deepcopy(state["deal"]) if identifier == deal["_id"] else None

    async def save(existing, changes):
        if revision(existing) != revision(state["deal"]):
            return None
        state["deal"] = {**state["deal"], **deepcopy(changes)}
        return deepcopy(state["deal"])

    async def enrich(document, _user):
        return {**document, "totalAmount": document["quantity"] * document["amountSalesUnit"], "amountPurchaseTotal": document["quantity"] * document["amountPurchaseUnit"]}

    repository = SimpleNamespace(read_for_operations=AsyncMock(side_effect=read), update_checked=AsyncMock(side_effect=save),
                                 read_operation_address=AsyncMock(return_value=None), find_one=AsyncMock(side_effect=lambda **_: deepcopy(state["deal"])))
    monkeypatch.setattr(DealsService, "repository", repository)
    monkeypatch.setattr(DealsService, "_enrich_response", enrich)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user

    @app.exception_handler(AppError)
    async def errors(_request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    with TestClient(app) as client:
        root = f"/deals/{deal['_id']}"
        yield SimpleNamespace(client=client, root=root, state=state, user=user, repository=repository, app=app,
                              read=lambda: client.get(f"{root}/operations").json())


def payment(api, **changes):
    return {"revision": api.read()["revision"], "requestId": str(uuid4()), "kind": "customer", "status": "paid", "amount": "10.25", "actualDate": date.today().isoformat(), **changes}


def shipment(api, **changes):
    return {"revision": api.read()["revision"], "requestId": str(uuid4()), "status": "planned", "quantity": "60", "unit": "т", "plannedDate": date.today().isoformat(), **changes}


def test_get_preserves_legacy_and_does_not_write(api):
    api.state["deal"]["deliveredQuantity"] = [{"quantity": 20, "unit": "тонна", "date": "2026-10-01 00:00", "amountPurchase": 50}]
    body = api.read()
    assert body["summary"]["remainingQuantity"] == 80
    assert body["shipments"][0]["quantity"] == 20
    assert body["summary"]["executionStatus"] == "partial"
    assert "legacySource" not in body["shipments"][0]
    api.repository.update_checked.assert_not_awaited()


def test_routes_require_auth_and_deal_ownership(api):
    api.user.id = str(ObjectId())
    assert api.client.get(f"{api.root}/operations").status_code == 403
    api.user.manager = True
    assert api.client.get(f"{api.root}/operations").status_code == 200
    api.app.dependency_overrides.clear()
    assert api.client.get(f"{api.root}/operations").status_code == 401


def test_money_is_counted_exactly_and_kept_separate_from_payment_plans(api):
    for value in ["0.10", "0.20"]:
        assert api.client.post(f"{api.root}/payments", json=payment(api, amount=value)).status_code == 201
    body = api.read()
    assert body["summary"]["customerPaid"] == 0.3
    assert body["summary"]["customerDebt"] == 999.7
    assert body["summary"]["paymentStatus"] == "partial"
    planned = payment(api, amount="999.70", status="planned", actualDate=None, dueDate="2026-01-01")
    body = api.client.post(f"{api.root}/payments", json=planned).json()
    assert body["summary"]["customerPaid"] == 0.3 and body["summary"]["overduePayments"] == 1
    entry = body["payments"][-1]
    paid = payment(api, amount="999.70", requestId=entry["requestId"])
    body = api.client.patch(f"{api.root}/payments/{entry['_id']}", json=paid).json()
    assert body["summary"]["paymentStatus"] == "paid" and body["summary"]["customerDebt"] == 0


def test_post_retry_is_idempotent_but_changed_reused_request_is_conflict(api):
    request = payment(api)
    first = api.client.post(f"{api.root}/payments", json=request)
    retry = api.client.post(f"{api.root}/payments", json=request)
    assert first.status_code == retry.status_code == 201
    assert len(retry.json()["payments"]) == len(retry.json()["history"]["items"]) == 1
    assert api.client.post(f"{api.root}/payments", json={**request, "amount": "20"}).status_code == 409


def test_stale_revisions_never_overwrite_and_can_be_reloaded(api):
    stale = payment(api)
    api.client.post(f"{api.root}/payments", json=payment(api))
    assert api.client.post(f"{api.root}/payments", json=stale).status_code == 409
    assert len(api.read()["payments"]) == 1
    assert api.client.post(f"{api.root}/payments", json={**stale, "revision": api.read()["revision"]}).status_code == 201


def test_outgoing_payments_do_not_pay_customer_debt_and_overpayment_is_visible(api):
    api.client.post(f"{api.root}/payments", json=payment(api, kind="provider", amount="150"))
    body = api.read()
    assert body["summary"]["customerDebt"] == 1000 and body["summary"]["providerDebt"] == 350
    assert body["summary"]["cashBalance"] == -150
    api.client.post(f"{api.root}/payments", json=payment(api, amount="1200"))
    assert api.read()["summary"]["customerOverpayment"] == 200


def test_plan_confirmation_partial_delivery_and_remainder(api):
    response = api.client.post(f"{api.root}/shipments", json=shipment(api))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["summary"]["plannedQuantity"] == 60 and body["summary"]["deliveredQuantity"] == 0
    assert api.state["deal"]["deliveredQuantity"] == []
    entry = body["shipments"][0]
    request = shipment(api, status="delivered", actualDate=date.today().isoformat(), quantity="40", amountPurchase="150", requestId=entry["requestId"])
    body = api.client.patch(f"{api.root}/shipments/{entry['_id']}", json=request).json()
    assert body["summary"]["deliveredQuantity"] == 40 and body["summary"]["remainingQuantity"] == 60
    assert body["summary"]["progress"] == 40 and body["summary"]["executionStatus"] == "partial"
    assert api.state["deal"]["deliveredQuantity"][0]["amountPurchase"] == 150


@pytest.mark.parametrize("changes", [{"quantity": "101"}, {"unit": "м³"}])
def test_overbooking_and_mixed_units_are_rejected(api, changes):
    response = api.client.post(f"{api.root}/shipments", json=shipment(api, **changes))
    assert response.status_code == 422
    api.repository.update_checked.assert_not_awaited()


def test_cancel_keeps_reason_before_after_and_actor_and_restores_totals(api):
    first = api.client.post(f"{api.root}/payments", json=payment(api)).json()
    entry = first["payments"][0]
    response = api.client.post(f"{api.root}/payments/{entry['_id']}/cancel", json={"revision": first["revision"], "reason": "Ошибочная запись"})
    body = response.json()
    assert response.status_code == 200
    assert body["summary"]["customerPaid"] == 0 and body["payments"][0]["status"] == "cancelled"
    history = body["history"]["items"][0]
    assert history["before"]["amount"] == 10.25 and history["after"]["status"] == "cancelled"
    assert history["actorName"] == "Manager" and history["reason"] == "Ошибочная запись"
    assert api.client.patch(f"{api.root}/payments/{entry['_id']}", json=payment(api)).status_code == 409


def test_cancel_delivery_restores_available_volume_without_deleting_history(api):
    first = api.client.post(f"{api.root}/shipments", json=shipment(api, status="delivered", actualDate=date.today().isoformat())).json()
    entry = first["shipments"][0]
    response = api.client.post(f"{api.root}/shipments/{entry['_id']}/cancel", json={"revision": first["revision"], "reason": "Корректировка"})
    assert response.json()["summary"]["remainingQuantity"] == 100
    assert api.state["deal"]["deliveredQuantity"] == []
    assert len(api.read()["history"]["items"]) == 2


def test_shipment_address_must_belong_to_correct_company(api):
    response = api.client.post(f"{api.root}/shipments", json=shipment(api, shippingAddressId=str(ObjectId())))
    assert response.status_code == 422
    api.repository.update_checked.assert_not_awaited()


def test_edit_protects_operations_from_legacy_form_and_lower_order_volume(api):
    api.client.post(f"{api.root}/shipments", json=shipment(api))
    existing = api.state["deal"]
    with pytest.raises(ValidationError):
        guard_deal_edit(existing, {"quantity": 50}, api.user)
    with pytest.raises(AppError):
        guard_deal_edit(existing, {"deliveredQuantity": []}, api.user)
    with pytest.raises(ValidationError):
        guard_deal_edit(existing, {"unitMeasurement": "куб.м"}, api.user)
    assert api.client.patch(api.root, json={"notes": "Old form"}).status_code == 409


def test_history_is_paginated_and_cancel_requires_reason(api):
    for _ in range(3):
        api.client.post(f"{api.root}/payments", json=payment(api))
    result = api.client.get(f"{api.root}/operations?historyPage=2&historyPageSize=2").json()
    assert result["history"]["total"] == 3 and len(result["history"]["items"]) == 1
    assert api.client.post(f"{api.root}/payments/{result['payments'][0]['_id']}/cancel", json={"revision": result["revision"], "reason": " "}).status_code == 422


@pytest.mark.parametrize("changes", [{"amount": "0"}, {"amount": "-1"}, {"amount": "nan"}, {"amount": "1.234"}, {"actualDate": None}, {"actualDate": (date.today() + timedelta(days=2)).isoformat()}])
def test_payment_invalid_input_does_not_write(api, changes):
    assert api.client.post(f"{api.root}/payments", json=payment(api, **changes)).status_code == 422
    api.repository.update_checked.assert_not_awaited()


@pytest.mark.parametrize("changes", [{"quantity": "0"}, {"quantity": "1.0001"}, {"deliveryCost": "-1"}, {"plannedDate": None}])
def test_shipment_invalid_input_does_not_write(api, changes):
    assert api.client.post(f"{api.root}/shipments", json=shipment(api, **changes)).status_code == 422
    api.repository.update_checked.assert_not_awaited()


def test_mixed_legacy_units_are_reported_not_summed_or_destroyed():
    deal = {"quantity": 100, "unitMeasurement": "т", "deliveredQuantity": [{"quantity": 20, "unit": "т", "date": "2026-01-01"}, {"quantity": 5, "unit": "м³", "date": "2026-01-01"}]}
    ledger = ledger_for(deal)
    assert summary(ledger, deal)["remainingQuantity"] is None
    assert summary(ledger, deal)["warning"]
    assert delivered_rows(ledger) == deal["deliveredQuantity"]


def test_database_failure_does_not_look_like_missing_record_or_zero_total():
    repository = DealsRepository(SimpleNamespace(find_one=AsyncMock(side_effect=ServerSelectionTimeoutError("private"))))
    with pytest.raises(InternalError):
        asyncio.run(repository.read_for_operations(ObjectId()))


def test_revision_matches_raw_bson_serialized_detail_and_list():
    raw = {"userId": ObjectId(), "customerId": ObjectId(), "stageId": ObjectId(), "calculationRuleId": ObjectId(),
           "quantity": 100, "updatedAt": datetime(2026, 10, 23, 10, 0, 0, 123000, tzinfo=timezone.utc), "unitMeasurement": ""}
    assert revision(raw) == revision(serialize_mongo_doc(raw)) == revision(convert_objectids_to_str(raw))


def test_deal_price_edit_retains_before_and_after_in_operation_history(api):
    api.client.post(f"{api.root}/payments", json=payment(api))
    changes = guard_deal_edit(api.state["deal"], {"amountSalesUnit": 12}, api.user)
    event = changes["_operations"]["history"][-1]
    assert event["before"]["amountSalesUnit"] == 10
    assert event["after"]["amountSalesUnit"] == 12
