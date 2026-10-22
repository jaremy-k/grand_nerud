from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.crm import ensure_owner_access, owner_filter, serialize_crm, utc_now
from app.core.object_id import parse_object_id
from app.exceptions import ForbiddenError, InternalError, ValidationError
from app.leads.service import LeadsService
from app.tasks.service import TasksService
from app.users.shemas import SUsersGet
from app.workspace.repository import workspace_repository
from app.workspace.shemas import WorkspaceScope


class WorkspaceService:
    repository = workspace_repository

    @staticmethod
    def _context(user: SUsersGet, scope: WorkspaceScope, owner_id: str | None,
                 zone_name: str, limit: int) -> tuple[dict, dict, ZoneInfo, datetime]:
        if not user.id:
            raise ForbiddenError()
        if not 1 <= limit <= 20:
            raise ValidationError("limit must be between 1 and 20")
        if scope not in ("mine", "team"):
            raise ValidationError("Unknown workspace scope")
        if scope == "team":
            if not user.is_privileged:
                raise ForbiddenError()
            if owner_id is not None:
                raise ValidationError("scope=team cannot be combined with ownerId")
            query, resolved_scope, selected_owner = {}, "team", None
        else:
            selected_owner = str(parse_object_id(owner_id if owner_id is not None else user.id, "ownerId"))
            query = owner_filter(user, selected_owner)
            resolved_scope = "mine" if selected_owner == str(user.id) else "owner"
        try:
            zone = ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError("Unknown timezone") from exc
        now = utc_now()
        meta = {
            "generatedAt": now, "timezone": zone_name, "localDate": now.astimezone(zone).date(),
            "scope": resolved_scope, "ownerId": selected_owner, "limit": limit,
        }
        return query, meta, zone, now

    @staticmethod
    def _preview(document: dict, items_key: str, total_key: str, serializer) -> dict:
        if items_key not in document or total_key not in document:
            raise InternalError("Неполный ответ рабочего стола")
        items = [serializer(item) for item in document[items_key]]
        count = document[total_key]
        total = count[0]["value"] if count else 0
        if not isinstance(total, int) or total < len(items):
            raise InternalError("Некорректный счётчик рабочего стола")
        return {"items": items, "total": total, "hasMore": total > len(items)}

    @classmethod
    async def tasks(cls, user: SUsersGet, scope: WorkspaceScope = "mine",
                    owner_id: str | None = None, timezone: str = "Europe/Moscow", limit: int = 6) -> dict:
        owner_query, meta, zone, now = cls._context(user, scope, owner_id, timezone, limit)
        today = now.astimezone(zone).date()
        start = TasksService._date_bound(today, zone)
        end = TasksService._date_bound(today, zone, end=True)
        document = await cls.repository.task_buckets(
            {"deletedAt": None, "status": "open", **owner_query},
            {"overdue": {"$lt": now}, "today": {"$gte": start, "$lt": end},
             "upcoming": {"$gte": end}}, limit,
        )
        previews = {
            bucket: cls._preview(document, f"{bucket}Items", f"{bucket}Total", serialize_crm)
            for bucket in ("overdue", "today", "upcoming")
        }
        checked = set()
        for preview in previews.values():
            for task in preview["items"]:
                if task["_id"] in checked:
                    continue
                ensure_owner_access(task, user)
                # Keep the existing historical-task permissions after linked records change.
                await TasksService._linked_records(task, user, allow_deleted=True)
                checked.add(task["_id"])
        return {**meta, **previews}

    @classmethod
    async def leads(cls, user: SUsersGet, scope: WorkspaceScope = "mine",
                    owner_id: str | None = None, timezone: str = "Europe/Moscow", limit: int = 6) -> dict:
        owner_query, meta, _zone, _now = cls._context(user, scope, owner_id, timezone, limit)
        document = await cls.repository.new_leads({"deletedAt": None, **owner_query}, limit)
        preview = cls._preview(document, "items", "total", LeadsService.serialize)
        for lead in preview["items"]:
            ensure_owner_access(lead, user)
        return {**meta, "newLeads": preview}
