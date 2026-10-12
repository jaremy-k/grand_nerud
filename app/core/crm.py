from datetime import datetime, timezone

from bson import ObjectId

from app.core.object_id import parse_object_id
from app.exceptions import ForbiddenError, NotFoundError
from app.users.repository import users_repository
from app.users.shemas import SUsersGet


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_crm(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        # BSON datetimes are UTC even when decoded without tzinfo.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, dict):
        return {key: serialize_crm(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_crm(item) for item in value]
    return value


def ensure_owner_access(record: dict, user: SUsersGet) -> None:
    if not user.is_privileged and str(record.get("ownerId")) != str(user.id):
        raise ForbiddenError()


def owner_filter(user: SUsersGet, owner_id: str | None = None) -> dict:
    if not user.is_privileged:
        if owner_id is not None and owner_id != str(user.id):
            raise ForbiddenError()
        return {"ownerId": parse_object_id(user.id, "user_id")}
    return {"ownerId": parse_object_id(owner_id, "ownerId")} if owner_id else {}


async def resolve_owner(owner_id: str | ObjectId | None, user: SUsersGet) -> ObjectId:
    oid = parse_object_id(str(owner_id or user.id), "ownerId")
    if not user.is_privileged and str(oid) != str(user.id):
        raise ForbiddenError("Назначать другого ответственного может только руководитель")
    if str(oid) != str(user.id):
        owner = await users_repository.find_one(_id=oid, deletedAt=None)
        if not owner:
            raise NotFoundError("Ответственный не найден")
    return oid


async def require_active(repository, entity_id: str | ObjectId, label: str) -> dict:
    oid = parse_object_id(str(entity_id))
    record = await repository.find_one(_id=oid, deletedAt=None)
    if not record:
        raise NotFoundError(f"{label} не найден")
    return record
