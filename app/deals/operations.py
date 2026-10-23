"""Embedded operational ledger; arithmetic in minor units, not binary floats."""
import hashlib
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from bson import BSON, ObjectId

from app.core.crm import serialize_crm, utc_now
from app.exceptions import ConflictError, ValidationError

GUARDED_FIELDS = ("updatedAt", "userId", "stageId", "quantity", "unitMeasurement", "materialId", "customerId", "providerId",
                  "shippingAddressId", "deliveryAddressId", "amountSalesUnit", "amountPurchaseUnit", "amountDelivery",
                  "paymentMethod", "addExpenses", "deliveredQuantity", "calculationRuleId", "ndsPercent")
UNITS = {"т": {"т", "тонна", "тонн", "тонны"}, "м³": {"м³", "м3", "куб.м", "куб. м"}, "шт": {"шт", "шт.", "штука", "штук"}}


def normalize_unit(value) -> str:
    raw = str(value or "").strip().lower()
    return next((key for key, values in UNITS.items() if raw in values), raw)


def scaled(value, scale=100):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            return None
        return int((result * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (ValueError, TypeError, InvalidOperation):
        return None


def revision(deal: dict) -> str:
    fields = {key: deal.get(key) for key in GUARDED_FIELDS}
    # Detail/list pipelines serialize BSON differently; their revision must match the raw document.
    for key, value in fields.items():
        if isinstance(value, ObjectId):
            fields[key] = str(value)
    updated = fields.get("updatedAt")
    if isinstance(updated, str):
        try:
            updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except ValueError:
            pass
    if isinstance(updated, datetime):
        updated = updated.replace(tzinfo=timezone.utc) if updated.tzinfo is None else updated.astimezone(timezone.utc)
        fields["updatedAt"] = updated.isoformat(timespec="milliseconds")
    if not fields.get("unitMeasurement"):
        fields["unitMeasurement"] = None
    fields["version"] = (deal.get("_operations") or {}).get("version", 0)
    return hashlib.sha256(BSON.encode(fields)).hexdigest()


def ledger_for(deal: dict) -> dict:
    if deal.get("_operations") is not None:
        return deepcopy(deal["_operations"])
    shipments = []
    for index, item in enumerate(deal.get("deliveredQuantity") or []):
        count = scaled(item.get("quantity"), 1000)
        raw_date = str(item.get("date") or "").split(" ")[0]
        try:
            actual_date = date.fromisoformat(raw_date).isoformat()
        except ValueError:
            actual_date = None
        shipments.append({"_id": f"legacy-{index}", "status": "delivered", "quantityMilli": count or 0,
                          "unit": normalize_unit(item.get("unit")), "actualDate": actual_date, "plannedDate": None,
                          "amountPurchaseMinor": scaled(item.get("amountPurchase")), "deliveryCostMinor": None,
                          "comment": "", "providerId": deal.get("providerId"), "shippingAddressId": deal.get("shippingAddressId"),
                          "deliveryAddressId": deal.get("deliveryAddressId"), "legacySource": deepcopy(item),
                          "invalid": count is None or count <= 0 or actual_date is None or not normalize_unit(item.get("unit"))})
    return {"version": 0, "payments": [], "shipments": shipments, "history": []}


def delivered_rows(ledger: dict) -> list[dict]:
    rows = []
    for item in ledger["shipments"]:
        if item["status"] != "delivered":
            continue
        if "legacySource" in item:
            rows.append(deepcopy(item["legacySource"]))
            continue
        row = {"quantity": item["quantityMilli"] / 1000, "unit": item["unit"], "date": f"{item['actualDate']} 00:00"}
        if item.get("amountPurchaseMinor") is not None:
            row["amountPurchase"] = item["amountPurchaseMinor"] / 100
        rows.append(row)
    return rows


def public_entry(item: dict) -> dict:
    hidden = {"legacySource", "fingerprint", "amountMinor", "quantityMilli", "amountPurchaseMinor", "deliveryCostMinor"}
    result = {key: value for key, value in item.items() if key not in hidden}
    for source, target, scale in [("amountMinor", "amount", 100), ("quantityMilli", "quantity", 1000),
                                   ("amountPurchaseMinor", "amountPurchase", 100), ("deliveryCostMinor", "deliveryCost", 100)]:
        if source in item:
            result[target] = item[source] / scale if item[source] is not None else None
    return serialize_crm(result)


def summary(ledger: dict, deal: dict) -> dict:
    active = [row for row in ledger["shipments"] if row["status"] != "cancelled"]
    unit = normalize_unit(deal.get("unitMeasurement"))
    ordered = scaled(deal.get("quantity"), 1000)
    comparable = bool(unit) and ordered is not None and ordered >= 0 and all(not row.get("invalid") and row["unit"] == unit for row in active)
    delivered = sum(row["quantityMilli"] for row in active if row["status"] == "delivered") if comparable else None
    planned = sum(row["quantityMilli"] for row in active if row["status"] == "planned") if comparable else None
    paid = {key: sum(row["amountMinor"] for row in ledger["payments"] if row["status"] == "paid" and row["kind"] == key)
            for key in ("customer", "provider", "delivery", "other")}
    amount = scaled(deal.get("totalAmount"))
    purchase = scaled(deal.get("amountPurchaseTotal"))
    today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    payment_status = "unknown" if amount is None else "not_required" if amount <= 0 and not paid["customer"] else "paid" if paid["customer"] >= amount else "partial" if paid["customer"] > 0 else "unpaid"
    execution = "unknown" if not comparable else "completed" if ordered > 0 and delivered >= ordered else "partial" if delivered > 0 else "planned" if planned > 0 else "unplanned"
    return {"currency": "RUB", "paymentStatus": payment_status, "executionStatus": execution,
            "customerAmount": amount / 100 if amount is not None else None, "customerPaid": paid["customer"] / 100,
            "customerDebt": max(0, amount - paid["customer"]) / 100 if amount is not None else None,
            "customerOverpayment": max(0, paid["customer"] - amount) / 100 if amount is not None else None,
            "providerAmount": purchase / 100 if purchase is not None else None, "providerPaid": paid["provider"] / 100,
            "providerDebt": max(0, purchase - paid["provider"]) / 100 if purchase is not None else None,
            "providerOverpayment": max(0, paid["provider"] - purchase) / 100 if purchase is not None else None,
            "deliveryPaid": paid["delivery"] / 100, "otherPaid": paid["other"] / 100,
            "cashBalance": (paid["customer"] - paid["provider"] - paid["delivery"] - paid["other"]) / 100,
            "orderedQuantity": ordered / 1000 if ordered is not None else None, "unit": unit,
            "deliveredQuantity": delivered / 1000 if delivered is not None else None,
            "plannedQuantity": planned / 1000 if planned is not None else None,
            "remainingQuantity": max(0, ordered - delivered) / 1000 if comparable else None,
            "unplannedQuantity": max(0, ordered - delivered - planned) / 1000 if comparable else None,
            "overDeliveredQuantity": max(0, delivered - ordered) / 1000 if comparable else None,
            "progress": min(100, round(delivered * 100 / ordered, 1)) if comparable and ordered > 0 else None,
            "overduePayments": sum(1 for row in ledger["payments"] if row["status"] == "planned" and row.get("dueDate", "9999") < today),
            "overdueShipments": sum(1 for row in active if row["status"] == "planned" and row.get("plannedDate", "9999") < today),
            "warning": None if comparable else "Проверьте объёмы и единицы существующих поставок"}


def validate_shipments(ledger: dict, deal: dict) -> None:
    active = [row for row in ledger["shipments"] if row["status"] != "cancelled"]
    if not active:
        return
    unit = normalize_unit(deal.get("unitMeasurement"))
    amount = scaled(deal.get("quantity"), 1000)
    if not unit or amount is None or amount <= 0:
        raise ValidationError("В сделке должен быть положительный объём и единица измерения")
    if any(row.get("invalid") or row["unit"] != unit for row in active):
        raise ValidationError("Единицы поставок должны совпадать с единицей сделки. Исправьте существующие поставки")
    if sum(row["quantityMilli"] for row in active) > amount:
        raise ValidationError("Сумма запланированных и подтверждённых поставок превышает объём сделки")


def append_history(ledger: dict, user, kind: str, entry_id: str, action: str, before, after, reason=""):
    ledger["history"].append({"_id": str(ObjectId()), "at": utc_now(), "actorId": user.id,
                              "actorName": user.name or user.email or "Сотрудник", "kind": kind, "entryId": entry_id,
                              "action": action, "before": public_entry(before) if before else None,
                              "after": public_entry(after) if after else None, "reason": reason})
    ledger["version"] += 1
    if len(ledger["payments"]) + len(ledger["shipments"]) > 1000 or len(ledger["history"]) > 5000 or len(BSON.encode(ledger)) > 12_000_000:
        raise ValidationError("Достигнут лимит операций сделки. Обратитесь к администратору")


def guard_deal_edit(existing: dict, payload: dict, user) -> dict:
    ledger = ledger_for(existing)
    active = [row for row in ledger["shipments"] if row["status"] != "cancelled"]
    if existing.get("_operations") is not None and "deliveredQuantity" in payload:
        raise ConflictError("Изменяйте поставки на вкладке «Поставки»")
    for field, payment_kind in [("customerId", "customer"), ("providerId", "provider")]:
        if field in payload and str(payload[field]) != str(existing.get(field)) and any(row["kind"] == payment_kind and row["status"] != "cancelled" for row in ledger["payments"]):
            raise ValidationError("Нельзя изменить контрагента с действующими платежами")
    if active:
        for key in ("materialId", "providerId"):
            if key in payload and str(payload[key]) != str(existing.get(key)):
                raise ValidationError("Сначала отмените или исправьте связанные поставки")
        if "unitMeasurement" in payload and normalize_unit(payload["unitMeasurement"]) != normalize_unit(existing.get("unitMeasurement")):
            raise ValidationError("Нельзя изменить единицу сделки с действующими поставками")
        if "quantity" in payload and payload["quantity"] != existing.get("quantity"):
            validate_shipments(ledger, {**existing, **payload})
    if existing.get("_operations") is not None:
        changes = {key: value for key, value in payload.items() if value != existing.get(key)}
        if changes:
            append_history(ledger, user, "deal", str(existing["_id"]), "updated", {key: existing.get(key) for key in changes}, changes)
            payload["_operations"] = ledger
    return payload
