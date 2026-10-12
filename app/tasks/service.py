from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.companies.repository import companies_repository
from app.core.crm import ensure_owner_access, owner_filter, require_active, resolve_owner, serialize_crm, utc_now
from app.core.mongo_utils import convert_objectids_to_str
from app.core.object_id import parse_object_id
from app.core.pagination import PaginatedResponse
from app.deals.service import DealsService
from app.exceptions import InternalError, NotFoundError, ValidationError
from app.repositories.protocols import EntityRepositoryProtocol
from app.tasks.repository import tasks_repository
from app.tasks.shemas import STasksCreate, STasksFilters, STasksPagination, STasksUpdate
from app.users.repository import users_repository
from app.users.shemas import SUsersGet


class TasksService:
    repository: EntityRepositoryProtocol = tasks_repository

    @staticmethod
    async def _linked_records(document: dict, user: SUsersGet, allow_deleted: bool = False) -> tuple[dict | None, dict | None]:
        lead = deal = None
        if document.get("leadId") is not None:
            from app.leads.service import LeadsService

            # Converted leads remain readable through the lead service.
            reader = LeadsService.get_for_task if allow_deleted else LeadsService.get_by_id
            lead = await reader(str(document["leadId"]), user)
            if not lead:
                raise NotFoundError("Lead not found")
        if document.get("dealId") is not None:
            if allow_deleted:
                deal = await DealsService.repository.find_one(_id=parse_object_id(str(document["dealId"]), "dealId"))
                if not deal:
                    raise NotFoundError("Сделка не найдена")
            else:
                deal = await require_active(DealsService.repository, document["dealId"], "Deal")
            DealsService._ensure_access(deal, user)
        return lead, deal

    @classmethod
    async def _active_task(cls, task_id: str, user: SUsersGet) -> dict:
        task = await require_active(cls.repository, task_id, "Task")
        ensure_owner_access(task, user)
        await cls._linked_records(task, user, allow_deleted=True)
        return task

    @classmethod
    async def _validate_links(cls, document: dict, user: SUsersGet) -> None:
        lead, deal = await cls._linked_records(document, user)
        company_id = document.get("companyId")
        if company_id is not None:
            await require_active(companies_repository, company_id, "Company")
            for record, field in ((lead, "companyId"), (deal, "customerId")):
                if record is not None and str(record.get(field)) != str(company_id):
                    raise ValidationError("companyId must match the linked lead and deal")
        if lead is not None and deal is not None:
            if str(deal.get("sourceLeadId")) != str(lead["_id"]):
                raise ValidationError("The deal must originate from the linked lead")
            if str(lead.get("companyId")) != str(deal.get("customerId")):
                raise ValidationError("The linked lead and deal must have the same company")

        if lead is None and deal is None:
            return
        owner = user
        if str(document["ownerId"]) != str(user.id):
            owner_record = await require_active(users_repository, document["ownerId"], "Assignee")
            owner = SUsersGet.model_validate(owner_record)
        if lead is not None:
            ensure_owner_access(lead, owner)
        if deal is not None:
            DealsService._ensure_access(deal, owner)

    @staticmethod
    def _date_bound(value: date | datetime, zone: ZoneInfo, end: bool = False) -> datetime:
        if isinstance(value, datetime):
            if value.utcoffset() is None:
                raise ValidationError("Date filters must include a timezone")
            return value.astimezone(timezone.utc)
        if end:
            value += timedelta(days=1)
        return datetime.combine(value, time.min, tzinfo=zone).astimezone(timezone.utc)

    @classmethod
    def _list_query(cls, filters: STasksFilters, user: SUsersGet) -> dict:
        query = {"deletedAt": None, **owner_filter(
            user, str(filters.ownerId) if filters.ownerId is not None else None,
        )}
        try:
            zone = ZoneInfo(filters.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError("Unknown timezone") from exc
        for field in ("companyId", "leadId", "dealId", "status", "type"):
            value = getattr(filters, field)
            if value is not None:
                query[field] = value

        date_bounds = {}
        if filters.dateFrom is not None:
            date_bounds["$gte"] = cls._date_bound(filters.dateFrom, zone)
        if filters.dateTo is not None:
            upper_operator = "$lte" if isinstance(filters.dateTo, datetime) else "$lt"
            date_bounds[upper_operator] = cls._date_bound(filters.dateTo, zone, end=True)
            lower = date_bounds.get("$gte")
            upper = date_bounds[upper_operator]
            if lower is not None and (lower > upper or (lower == upper and upper_operator == "$lt")):
                raise ValidationError("dateFrom must not be after dateTo")

        bucket_bounds = {}
        if filters.bucket is not None:
            if filters.status not in (None, "open"):
                raise ValidationError("Buckets only contain open tasks")
            query["status"] = "open"
            now = utc_now()
            today = now.astimezone(zone).date()
            start = cls._date_bound(today, zone)
            end = cls._date_bound(today, zone, end=True)
            bucket_bounds = {
                "today": {"$gte": start, "$lt": end},
                "overdue": {"$lt": now},
                "upcoming": {"$gte": end},
            }[filters.bucket]
        if date_bounds and bucket_bounds:
            query["$and"] = [{"dueAt": date_bounds}, {"dueAt": bucket_bounds}]
        elif date_bounds or bucket_bounds:
            query["dueAt"] = date_bounds or bucket_bounds
        return query

    @classmethod
    async def list_tasks(
            cls, filters: STasksFilters, pagination: STasksPagination, user: SUsersGet,
    ) -> PaginatedResponse:
        query = cls._list_query(filters, user)
        await cls._linked_records(filters.model_dump(), user, allow_deleted=True)
        if filters.companyId is not None:
            await require_active(companies_repository, filters.companyId, "Company")
        result = await cls.repository.find_paginated(
            filter_by=query, skip=pagination.skip, limit=pagination.limit,
            sort=[("dueAt", 1), ("_id", 1)],
        )
        for task in result.items:
            ensure_owner_access(task, user)
            await cls._linked_records(task, user, allow_deleted=True)
        return result.model_copy(update={"items": serialize_crm(result.items)})

    @classmethod
    async def get_by_id(cls, task_id: str, user: SUsersGet) -> dict:
        return serialize_crm(await cls._active_task(task_id, user))

    @staticmethod
    async def _record_activity(lead_id, user: SUsersGet, kind: str, task: dict, changes=None) -> None:
        if lead_id is None:
            return
        from app.leads.activities import LeadActivitiesService

        comment = task.get("result") if kind == "task_completed" else task.get("comment")
        if not comment or not comment.strip():
            label = {
                "task_created": "Создана задача",
                "task_updated": "Задача обновлена",
                "task_completed": "Задача выполнена",
                "task_cancelled": "Задача отменена",
                "task_deleted": "Задача удалена",
            }[kind]
            comment = f"{label}: {task['title']}"
        await LeadActivitiesService.record(
            str(lead_id), user, kind, comment,
            details=convert_objectids_to_str({
                "taskId": task["_id"], "title": task["title"],
                "status": task["status"], "result": task.get("result"),
                "changes": changes or {},
            }),
        )

    @staticmethod
    async def _sync_follow_up(task: dict, previous: dict) -> None:
        if not task.get("followUp") or task.get("leadId") is None:
            return
        from app.leads.service import LeadsService

        task_id = parse_object_id(str(task["_id"]))
        query = {
            "_id": parse_object_id(str(task["leadId"])),
            "deletedAt": None, "followUpTaskId": task_id,
        }
        if task.get("deletedAt") is not None or task["status"] in ("completed", "cancelled"):
            update = {"nextContactAt": None, "followUpTaskId": None}
        elif task["dueAt"] != previous["dueAt"] or task["status"] != previous["status"]:
            update = {"nextContactAt": task["dueAt"], "followUpTaskId": task_id}
            query.update(dealId=None, conversionDealId=None)
            if previous["status"] != "open":
                query["followUpTaskId"] = None
        else:
            return
        update["updatedAt"] = utc_now()
        # Match the pointer atomically so a newer follow-up is never overwritten.
        await LeadsService.repository.update_many(filter_by=query, update_data=update)

    @classmethod
    async def create(cls, data: STasksCreate, user: SUsersGet) -> dict:
        document = data.model_dump()
        document["ownerId"] = await resolve_owner(document["ownerId"], user)
        document["dueAt"] = document["dueAt"].astimezone(timezone.utc)
        await cls._validate_links(document, user)
        now = utc_now()
        document.update(
            createdById=parse_object_id(user.id), createdAt=now, updatedAt=now, deletedAt=None,
        )
        task = await cls.repository.create(document)
        if not task:
            raise InternalError("Could not create task")
        await cls._record_activity(task.get("leadId"), user, "task_created", task)
        return serialize_crm(task)

    @classmethod
    async def update(cls, task_id: str, data: STasksUpdate, user: SUsersGet) -> dict:
        existing = await cls._active_task(task_id, user)
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            return serialize_crm(existing)
        if existing.get("followUp"):
            for field in ("leadId", "companyId"):
                if field in changes and str(changes[field]) != str(existing.get(field)):
                    raise ValidationError("Follow-up leadId and companyId cannot be changed")
        if "ownerId" in changes:
            changes["ownerId"] = await resolve_owner(changes["ownerId"], user)
        if "dueAt" in changes:
            changes["dueAt"] = changes["dueAt"].astimezone(timezone.utc)
        await cls._validate_links({**existing, **changes}, user)
        task = await cls.repository.update_by_id(
            object_id=task_id, update_data={**changes, "updatedAt": utc_now()},
        )
        if not task:
            raise InternalError("Could not update task")
        await cls._sync_follow_up(task, existing)
        kind = "task_updated"
        if task["status"] != existing["status"]:
            kind = {"completed": "task_completed", "cancelled": "task_cancelled"}.get(task["status"], kind)
        lead_ids = {str(value) for value in (existing.get("leadId"), task.get("leadId")) if value is not None}
        for lead_id in sorted(lead_ids):
            await cls._record_activity(lead_id, user, kind, task, changes)
        return serialize_crm(task)

    @classmethod
    async def soft_delete(cls, task_id: str, user: SUsersGet) -> dict:
        existing = await cls._active_task(task_id, user)
        now = utc_now()
        task = await cls.repository.update_by_id(
            object_id=task_id, update_data={"deletedAt": now, "updatedAt": now},
        )
        if not task:
            raise InternalError("Could not delete task")
        await cls._sync_follow_up(task, existing)
        await cls._record_activity(existing.get("leadId"), user, "task_deleted", task)
        return serialize_crm(task)
