import re

from bson import ObjectId

from app.adresses.repository import adresses_repository
from app.companies.repository import companies_repository
from app.core.crm import ensure_owner_access, owner_filter, require_active, resolve_owner, serialize_crm, utc_now
from app.core.object_id import parse_object_id
from app.core.pagination import PaginatedResponse
from app.deals.service import DealsService
from app.deals.shemas import SDealsInput
from app.exceptions import ConflictError, InternalError, NotFoundError, ValidationError
from app.lead_stages.service import LeadStagesService
from app.leads.activities import LeadActivitiesService
from app.leads.repository import leads_repository
from app.leads.shemas import SLeadCreate, SLeadUpdate
from app.materials.repository import materials_repository
from app.services.repository import services_repository
from app.stages.repository import stages_repository
from app.tasks.repository import tasks_repository
from app.users.repository import users_repository
from app.users.shemas import SUsersGet


def lead_relation_lookups() -> list[dict]:
    return [
        {"$lookup": {"from": "companies", "localField": "companyId", "foreignField": "_id", "as": "company"}},
        {"$lookup": {"from": "lead_stages", "localField": "stageId", "foreignField": "_id", "as": "stage"}},
        {"$lookup": {"from": "materials", "localField": "materialIds", "foreignField": "_id", "as": "materials"}},
        {"$addFields": {
            "company": {"$arrayElemAt": ["$company", 0]},
            "stage": {"$arrayElemAt": ["$stage", 0]},
        }},
    ]


class LeadsService:
    repository = leads_repository

    @staticmethod
    def serialize(lead: dict) -> dict:
        public = {key: value for key, value in lead.items()
                  if key not in {"conversionDealId", "conversionInput", "conversionDocument", "importKey"}}
        public["conversionPending"] = bool(lead.get("conversionDealId") and not lead.get("dealId"))
        return serialize_crm(public)

    @classmethod
    async def get_raw(cls, lead_id: str, user: SUsersGet) -> dict:
        lead = await require_active(cls.repository, lead_id, "Лид")
        ensure_owner_access(lead, user)
        return lead

    @classmethod
    async def get_by_id(cls, lead_id: str, user: SUsersGet) -> dict:
        lead = await cls.get_raw(lead_id, user)
        rows = await cls.repository.aggregate([
            {"$match": {"_id": lead["_id"], "deletedAt": None, **owner_filter(user)}},
            *lead_relation_lookups(),
        ])
        if not rows:
            raise NotFoundError("Лид не найден или ответственный изменился")
        return cls.serialize(rows[0])

    @classmethod
    async def get_for_task(cls, lead_id: str, user: SUsersGet) -> dict:
        lead = await cls.repository.find_one(_id=parse_object_id(lead_id))
        if not lead:
            raise NotFoundError("Лид не найден")
        ensure_owner_access(lead, user)
        return cls.serialize(lead)

    @classmethod
    async def list_leads(cls, user: SUsersGet, page: int = 1, page_size: int = 100,
                         owner_id: str | None = None, company_id: str | None = None,
                         stage_id: str | None = None, priority: str | None = None,
                         status: str | None = None, search: str | None = None) -> PaginatedResponse:
        query = {"deletedAt": None, **owner_filter(user, owner_id)}
        if company_id:
            query["companyId"] = parse_object_id(company_id, "companyId")
        if stage_id:
            query["stageId"] = parse_object_id(stage_id, "stageId")
        if status:
            stages = await LeadStagesService.repository.find_many(kind=status, deletedAt=None, limit=0)
            ids = [stage["_id"] for stage in stages]
            if stage_id and query["stageId"] not in ids:
                ids = []
            query["stageId"] = {"$in": ids if not stage_id else [query["stageId"]] if ids else []}
        if priority:
            query["priority"] = priority
        if search:
            query["title"] = {"$regex": re.escape(search), "$options": "i"}
        total = await cls.repository.count(query)
        rows = await cls.repository.aggregate([
            {"$match": query}, {"$sort": {"createdAt": -1, "_id": -1}},
            {"$skip": (page - 1) * page_size}, {"$limit": page_size},
            *lead_relation_lookups(),
        ])
        return PaginatedResponse(
            items=[cls.serialize(row) for row in rows], total=total, page=page, page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
            has_next=page * page_size < total, has_prev=page > 1,
        )

    @classmethod
    async def _validate_links(cls, data: dict) -> None:
        if data.get("companyId"):
            await require_active(companies_repository, data["companyId"], "Компания")
        for material_id in data.get("materialIds") or []:
            await require_active(materials_repository, material_id, "Материал")
        if data.get("objectAddressId"):
            address = await require_active(adresses_repository, data["objectAddressId"], "Адрес")
            if data.get("companyId") and str(address.get("companyId")) != str(data["companyId"]):
                raise ValidationError("Объект должен принадлежать компании лида")

    @classmethod
    async def _validate_stage(cls, data: dict, require_followup: bool = True) -> dict:
        stage = await require_active(LeadStagesService.repository, data["stageId"], "Этап лида")
        if stage["kind"] == "converted":
            raise ValidationError("Перевод в сделку выполняется через /leads/{id}/convert")
        if stage["kind"] == "deferred" and require_followup and not data.get("nextContactAt"):
            raise ValidationError("Для отложенного лида укажите nextContactAt")
        if stage["kind"] == "unqualified" and not (data.get("lossReason") or "").strip():
            raise ValidationError("Для нецелевого лида укажите lossReason")
        return stage

    @classmethod
    async def _sync_followup(cls, lead: dict, user: SUsersGet, due_at) -> None:
        task_id = lead.get("followUpTaskId")
        task = await tasks_repository.find_one(_id=task_id, deletedAt=None) if task_id else None
        if due_at is None:
            cleared = await cls.repository.clear_followup(lead)
            if cleared is None:
                return
            if task and task.get("status") == "open":
                await tasks_repository.update_by_id(task_id, {"status": "cancelled", "updatedAt": utc_now()})
                await LeadActivitiesService.record(lead["_id"], user, "task_cancelled", "Отменён следующий звонок")
            lead["nextContactAt"] = None
            lead["followUpTaskId"] = None
            lead["updatedAt"] = cleared["updatedAt"]
            return
        payload = {
            "title": f"Перезвонить: {lead['title']}", "type": "call", "dueAt": due_at,
            "ownerId": lead["ownerId"], "companyId": lead.get("companyId"),
            "leadId": lead["_id"], "followUp": True, "updatedAt": utc_now(),
            "followUpLeadUpdatedAt": lead["updatedAt"],
        }
        if task and task.get("status") == "open":
            result = await tasks_repository.update_followup(task, payload)
        else:
            result = await tasks_repository.create({
                **payload, "createdById": parse_object_id(user.id),
                "createdAt": utc_now(), "status": "open", "deletedAt": None,
            })
        if not result:
            raise InternalError("Не удалось назначить следующий звонок")
        attached = await cls.repository.attach_followup(lead, result["_id"])
        if attached is None:
            await tasks_repository.update_many({
                "_id": result["_id"], "updatedAt": result["updatedAt"],
                "followUpLeadUpdatedAt": lead["updatedAt"], "status": "open",
            }, {"status": "cancelled", "updatedAt": utc_now()})
            return
        lead["followUpTaskId"] = result["_id"]
        if not task or task.get("status") != "open":
            await LeadActivitiesService.record(lead["_id"], user, "task_created", "Назначен следующий звонок",
                                               {"taskId": result["_id"], "dueAt": due_at})

    @classmethod
    async def create(cls, data: SLeadCreate, user: SUsersGet, *, import_key: str | None = None) -> dict:
        payload = data.model_dump(exclude_none=True)
        payload["ownerId"] = await resolve_owner(data.ownerId, user)
        if not payload.get("stageId"):
            payload["stageId"] = (await LeadStagesService.get_by_kind("new"))["_id"]
        await cls._validate_links(payload)
        stage = await cls._validate_stage(payload)
        if stage["kind"] == "unqualified":
            payload.pop("nextContactAt", None)
        payload.update(createdById=parse_object_id(user.id), createdAt=utc_now(), updatedAt=utc_now(), deletedAt=None)
        if import_key:
            payload["importKey"] = import_key
        lead = await cls.repository.create(payload)
        if not lead:
            raise InternalError("Не удалось создать лид")
        await LeadActivitiesService.record(lead["_id"], user, "created", "Лид создан")
        if lead.get("nextContactAt") and stage["kind"] != "unqualified":
            await cls._sync_followup(lead, user, lead["nextContactAt"])
        return cls.serialize(lead)

    @classmethod
    async def create_for_import(cls, company: dict, user: SUsersGet) -> bool:
        import_key = f"excel:{user.id}:{company['_id']}"
        if await cls.repository.find_one(importKey=import_key):
            return False
        contacts = company.get("contactPersons") or []
        data = SLeadCreate(
            title=f"Первичный контакт: {company.get('name') or company['_id']}"[:200],
            companyId=str(company["_id"]),
            contactPerson=contacts[0] if contacts else None,
            source=company.get("source") or "Excel",
        )
        try:
            await cls.create(data, user, import_key=import_key)
        except InternalError:
            if await cls.repository.find_one(importKey=import_key):
                return False
            raise
        return True

    @classmethod
    async def update(cls, lead_id: str, data: SLeadUpdate, user: SUsersGet) -> dict:
        lead = await cls.get_raw(lead_id, user)
        if lead.get("conversionDealId") or lead.get("dealId"):
            raise ConflictError("Лид уже переведён в сделку или перевод выполняется")
        payload = data.model_dump(exclude_unset=True)
        for field in ("title", "ownerId", "stageId", "priority", "materialIds"):
            if field in payload and payload[field] is None:
                raise ValidationError(f"{field} не может быть null")
        if "ownerId" in payload:
            payload["ownerId"] = await resolve_owner(payload["ownerId"], user)
        merged = {**lead, **payload}
        await cls._validate_links(merged)
        stage = await cls._validate_stage(merged, require_followup="stageId" in payload or "nextContactAt" in payload)
        payload["updatedAt"] = utc_now()
        result = await cls.repository.update_unconverted(lead, payload)
        if not result:
            raise ConflictError("Лид изменился, обновите его и повторите запрос")
        changes = {
            field: {"before": lead.get(field), "after": value}
            for field, value in payload.items()
            if field != "updatedAt" and lead.get(field) != value
        }
        if changes:
            kind = "stage_changed" if "stageId" in changes else "updated"
            await LeadActivitiesService.record(lead_id, user, kind, "Лид обновлён", changes)
        linked_task_update = {}
        if "ownerId" in changes:
            linked_task_update["ownerId"] = result["ownerId"]
        if "companyId" in changes:
            linked_task_update["companyId"] = result.get("companyId")
        if linked_task_update:
            await tasks_repository.update_many(
                {"leadId": lead["_id"], "deletedAt": None},
                {**linked_task_update, "updatedAt": utc_now()},
            )
        if stage["kind"] == "unqualified":
            await cls._sync_followup(result, user, None)
        elif any(field in payload for field in ("nextContactAt", "ownerId", "companyId", "title")):
            await cls._sync_followup(result, user, result.get("nextContactAt"))
        return cls.serialize(result)

    @classmethod
    async def delete(cls, lead_id: str, user: SUsersGet) -> dict:
        lead = await cls.get_raw(lead_id, user)
        if lead.get("conversionDealId") or lead.get("dealId"):
            raise ConflictError("Нельзя удалить лид со связанной сделкой")
        if await tasks_repository.count({
            "leadId": lead["_id"], "status": "open", "deletedAt": None,
            "_id": {"$ne": lead.get("followUpTaskId")},
        }):
            raise ConflictError("Сначала завершите или отмените открытые задачи лида")
        result = await cls.repository.update_unconverted(lead, {"deletedAt": utc_now(), "updatedAt": utc_now()})
        if not result:
            raise ConflictError("Лид изменился, повторите запрос")
        await cls._sync_followup(result, user, None)
        await LeadActivitiesService.record(lead_id, user, "deleted", "Лид удалён")
        return cls.serialize(result)

    @classmethod
    async def convert(cls, lead_id: str, data: SDealsInput, user: SUsersGet) -> dict:
        lead = await cls.get_raw(lead_id, user)
        if lead.get("dealId"):
            deal = await DealsService.repository.find_one(_id=lead["dealId"])
            if not deal:
                raise InternalError("Связанная сделка не найдена")
            await cls._mark_customer(deal["customerId"])
            await cls._sync_followup(lead, user, None)
            await LeadActivitiesService.record(
                lead_id, user, "converted", "Лид переведён в сделку", {"dealId": lead["dealId"]},
                event_key=f"converted:{lead_id}",
            )
            owner = await cls._conversion_owner(lead, user)
            return {"lead": cls.serialize(lead), "deal": await DealsService._enrich_response(deal, owner)}

        converted_stage = await LeadStagesService.get_by_kind("converted")
        if not lead.get("conversionDealId"):
            stage = await require_active(LeadStagesService.repository, lead["stageId"], "Этап лида")
            if stage["kind"] != "qualified":
                raise ConflictError("Перед созданием сделки квалифицируйте лид")
            payload = data.model_dump(exclude_none=True)
            if lead.get("companyId"):
                if payload.get("customerId") and payload["customerId"] != lead["companyId"]:
                    raise ValidationError("Заказчик сделки должен совпадать с компанией лида")
                payload["customerId"] = lead["companyId"]
            for field, value in {
                "quantity": lead.get("quantity"), "unitMeasurement": lead.get("unitMeasurement"),
                "deliveryAddressId": lead.get("objectAddressId"), "deliveryAddress": lead.get("objectAddress"),
                "notes": lead.get("notes"),
            }.items():
                if value is not None:
                    payload.setdefault(field, value)
            if len(lead.get("materialIds", [])) == 1:
                payload.setdefault("materialId", lead["materialIds"][0])
            deal_input = SDealsInput.model_validate(payload)
            DealsService._validate_create(deal_input)
            for repository, field, label in (
                (companies_repository, "customerId", "Компания"),
                (materials_repository, "materialId", "Материал"),
                (services_repository, "serviceId", "Услуга"),
                (stages_repository, "stageId", "Этап сделки"),
            ):
                await require_active(repository, payload[field], label)
            if payload.get("providerId"):
                await require_active(companies_repository, payload["providerId"], "Исполнитель")
            for field in ("shippingAddressId", "deliveryAddressId"):
                if payload.get(field):
                    await require_active(adresses_repository, payload[field], "Адрес")
            owner = await cls._conversion_owner(lead, user)
            document = await DealsService.prepare_creation(deal_input, owner)
            reserved = await cls.repository.reserve_conversion(lead, payload, ObjectId(), document)
            if reserved is None:
                lead = await cls.get_raw(lead_id, user)
                if not lead.get("conversionDealId"):
                    raise ConflictError("Лид изменился, повторите запрос")
            else:
                lead = reserved

        owner = await cls._conversion_owner(lead, user)
        deal = await DealsService.create_from_lead(
            SDealsInput.model_validate(lead["conversionInput"]), owner,
            lead["_id"], lead["conversionDealId"],
            prepared=lead.get("conversionDocument"),
        )
        result = await cls.repository.update_by_id(lead["_id"], {
            "companyId": lead["conversionInput"]["customerId"],
            "dealId": lead["conversionDealId"], "stageId": converted_stage["_id"],
            "convertedAt": utc_now(), "updatedAt": utc_now(),
        })
        if not result:
            raise InternalError("Сделка создана, повторите запрос для завершения перевода лида")
        await cls._mark_customer(result["companyId"])
        await cls._sync_followup(result, user, None)
        await LeadActivitiesService.record(
            lead_id, user, "converted", "Лид переведён в сделку", {"dealId": result["dealId"]},
            event_key=f"converted:{lead_id}",
        )
        return {"lead": cls.serialize(result), "deal": deal}

    @staticmethod
    async def _conversion_owner(lead: dict, user: SUsersGet) -> SUsersGet:
        if str(lead["ownerId"]) == str(user.id):
            return user
        return SUsersGet.model_validate(await require_active(users_repository, lead["ownerId"], "Ответственный"))

    @staticmethod
    async def _mark_customer(company_id) -> None:
        if not await companies_repository.add_role(company_id, "customer"):
            raise InternalError("Не удалось назначить компании роль заказчика")
