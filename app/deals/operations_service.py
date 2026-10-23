import hashlib
import json
from copy import deepcopy

from bson import ObjectId

from app.core.crm import serialize_crm, utc_now
from app.core.object_id import parse_object_id
from app.deals.operation_schemas import CancelOperation, PaymentWrite, ShipmentWrite
from app.deals.operations import append_history, delivered_rows, ledger_for, normalize_unit, public_entry, revision, scaled, summary, validate_shipments
from app.deals.service import DealsService
from app.exceptions import ConflictError, NotFoundError, ValidationError


class DealOperationsService:
    @classmethod
    async def _deal(cls, identifier, user):
        deal = await DealsService.repository.read_for_operations(parse_object_id(identifier, "dealId"))
        if not deal:
            raise NotFoundError("Сделка не найдена")
        DealsService._ensure_access(deal, user)
        return deal

    @classmethod
    async def response(cls, deal, user, history_page=1, history_size=25):
        ledger = ledger_for(deal)
        enriched = await DealsService._enrich_response(deal, user)
        history = list(reversed(ledger["history"]))
        return {"dealId": str(deal["_id"]), "revision": revision(deal), "version": ledger["version"],
                "summary": summary(ledger, enriched), "payments": [public_entry(row) for row in ledger["payments"]],
                "shipments": [public_entry(row) for row in ledger["shipments"]],
                "history": {"items": serialize_crm(history[(history_page - 1) * history_size:history_page * history_size]),
                            "total": len(history), "page": history_page, "pageSize": history_size, "totalPages": (len(history) + history_size - 1) // history_size}}

    @classmethod
    async def read(cls, identifier, user, history_page=1, history_size=25):
        return await cls.response(await cls._deal(identifier, user), user, history_page, history_size)

    @classmethod
    async def write(cls, identifier, kind, data: PaymentWrite | ShipmentWrite | CancelOperation, user, entry_id=None, cancel=False):
        deal = await cls._deal(identifier, user)
        ledger = ledger_for(deal)
        rows = ledger[kind]
        before = next((row for row in rows if row["_id"] == entry_id), None) if entry_id else None
        if entry_id and not before:
            raise NotFoundError("Операция не найдена")
        fingerprint = None
        if not cancel:
            fingerprint = hashlib.sha256(json.dumps(data.model_dump(mode="json", exclude={"revision", "requestId"}), sort_keys=True).encode()).hexdigest()
            if not entry_id:
                prior = next((row for row in rows if row.get("requestId") == str(data.requestId)), None)
                if prior:
                    if prior.get("fingerprint") != fingerprint:
                        raise ConflictError("Этот запрос уже использован для другой операции")
                    return await cls.response(deal, user)
        if revision(deal) != data.revision:
            raise ConflictError("Данные сделки изменились. Обновите данные и проверьте остатки перед сохранением")
        if before and before["status"] == "cancelled":
            raise ConflictError("Отменённая операция доступна только для просмотра. Создайте новую")
        at = utc_now()
        if cancel:
            after = {**before, "status": "cancelled", "cancelReason": data.reason, "cancelledAt": at, "updatedAt": at}
        else:
            after = {"_id": entry_id or str(ObjectId()), "requestId": before.get("requestId") if before else str(data.requestId),
                     "fingerprint": before.get("fingerprint") if before else fingerprint, "status": data.status, "comment": data.comment,
                     "createdAt": before.get("createdAt") if before else at, "updatedAt": at}
            if kind == "payments":
                after.update(kind=data.kind, amountMinor=scaled(data.amount), dueDate=data.dueDate.isoformat() if data.dueDate else None,
                             actualDate=data.actualDate.isoformat() if data.actualDate else None, reference=data.reference)
            else:
                # A planned shipment may change its date/quantity, but keeps its original counterparties and addresses.
                after.update(quantityMilli=scaled(data.quantity, 1000), unit=normalize_unit(data.unit),
                             plannedDate=data.plannedDate.isoformat() if data.plannedDate else None,
                             actualDate=data.actualDate.isoformat() if data.actualDate else None,
                             amountPurchaseMinor=scaled(data.amountPurchase), deliveryCostMinor=scaled(data.deliveryCost))
                for field in ("providerId", "shippingAddressId", "deliveryAddressId", "materialId"):
                    after[field] = before.get(field) if before and field in before else deal.get(field)
                for field, company_field, text_field in [("shippingAddressId", "providerId", "shippingAddressText"), ("deliveryAddressId", "customerId", "deliveryAddressText")]:
                    identifier = getattr(data, field) or after.get(field)
                    # Unchanged historical addresses remain readable even if subsequently archived.
                    if before and str(identifier or "") == str(before.get(field) or ""):
                        after[field] = before.get(field)
                        after[text_field] = before.get(text_field, "")
                        continue
                    after[field] = parse_object_id(str(identifier), field) if identifier else None
                    if after[field]:
                        address = await DealsService.repository.read_operation_address(after[field], deal.get(company_field))
                        if not address:
                            raise ValidationError("Адрес не найден или не принадлежит компании сделки")
                        after[text_field] = (address.get("adressDetail") or {}).get("address", "")
        if before:
            rows[rows.index(before)] = after
        else:
            rows.append(after)
        if kind == "shipments" and not cancel:
            validate_shipments(ledger, deal)
        append_history(ledger, user, kind, after["_id"], "cancelled" if cancel else "updated" if before else "created", deepcopy(before), after, data.reason if cancel else "")
        changes = {"_operations": ledger, "updatedAt": at}
        if kind == "shipments":
            changes["deliveredQuantity"] = delivered_rows(ledger)
        # Compute before committing, so invalid calculator data cannot produce a half-successful write.
        await DealsService._enrich_response({**deal, **changes}, user)
        saved = await DealsService.repository.update_checked(deal, changes)
        if not saved:
            raise ConflictError("Данные сделки изменились. Обновите данные перед сохранением")
        return await cls.response(saved, user)
