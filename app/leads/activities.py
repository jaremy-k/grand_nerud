from hashlib import sha256

from bson import ObjectId

from app.core.crm import serialize_crm, utc_now
from app.core.mongo_utils import convert_objectids_to_str
from app.core.object_id import parse_object_id
from app.exceptions import InternalError
from app.leads.repository import lead_activities_repository


class LeadActivitiesService:
    repository = lead_activities_repository

    @classmethod
    async def record(cls, lead_id, user, kind: str, comment: str, details: dict | None = None,
                     event_key: str | None = None) -> dict:
        document = {
            "leadId": parse_object_id(str(lead_id)),
            "userId": parse_object_id(user.id),
            "type": kind, "comment": comment,
            "details": convert_objectids_to_str(details or {}),
            "createdAt": utc_now(),
        }
        if event_key:
            document["_id"] = ObjectId(sha256(event_key.encode()).digest()[:12])
            existing = await cls.repository.find_one(_id=document["_id"])
            if existing:
                return serialize_crm(existing)
        result = await cls.repository.create(document)
        if not result and event_key:
            result = await cls.repository.find_one(_id=document["_id"])
        if not result:
            raise InternalError("Не удалось сохранить историю лида")
        return serialize_crm(result)
