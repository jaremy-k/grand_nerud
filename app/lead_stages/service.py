from app.core.base_entity_service import BaseEntityService
from app.core.crm import require_active
from app.core.mongo_utils import convert_objectids_to_str
from app.core.object_id import parse_object_id
from app.exceptions import ConflictError, InternalError, ValidationError
from app.lead_stages.repository import lead_stages_repository
from app.lead_stages.shemas import SLeadStageCreate, SLeadStageUpdate
from app.leads.repository import leads_repository


class LeadStagesService(BaseEntityService):
    repository = lead_stages_repository
    not_found_detail = "Этап лида не найден"

    @classmethod
    async def list_stages(cls) -> list[dict]:
        return convert_objectids_to_str(await cls.repository.find_many(
            deletedAt=None, sort=[("order", 1)], limit=0,
        ))

    @classmethod
    async def get_by_kind(cls, kind: str) -> dict:
        stages = await cls.repository.find_many(kind=kind, deletedAt=None, sort=[("order", 1)], limit=1)
        if not stages:
            raise ValidationError(f"Не настроен этап лида: {kind}")
        return stages[0]

    @classmethod
    async def create(cls, data: SLeadStageCreate) -> dict:
        if not await cls.repository.is_unique("name", data.name):
            raise ConflictError("Этап лида с таким названием уже существует")
        result = await cls.repository.create(data.model_dump())
        if not result:
            raise InternalError("Не удалось создать этап лида")
        return convert_objectids_to_str(result)

    @classmethod
    async def update(cls, stage_id: str, data: SLeadStageUpdate) -> dict:
        existing = await require_active(cls.repository, stage_id, "Этап лида")
        payload = data.model_dump(exclude_unset=True)
        if any(value is None for value in payload.values()):
            raise ValidationError("Поля этапа не могут быть null")
        if "name" in payload and not await cls.repository.is_unique("name", data.name, exclude_id=stage_id):
            raise ConflictError("Этап лида с таким названием уже существует")
        if payload.get("kind", existing["kind"]) != existing["kind"]:
            if existing["kind"] in {"new", "converted"} or await cls.has_dependencies(stage_id):
                raise ConflictError("Нельзя менять тип системного или используемого этапа")
        result = await cls.repository.update_by_id(stage_id, payload)
        if not result:
            raise InternalError("Не удалось обновить этап лида")
        return convert_objectids_to_str(result)

    @classmethod
    async def has_dependencies(cls, stage_id: str) -> bool:
        return await leads_repository.count({"stageId": parse_object_id(stage_id), "deletedAt": None}) > 0

    @classmethod
    async def delete(cls, stage_id: str) -> dict:
        stage = await require_active(cls.repository, stage_id, "Этап лида")
        if await cls.has_dependencies(stage_id):
            raise ConflictError("Этап используется в лидах")
        if stage["kind"] in {"new", "converted"}:
            if await cls.repository.count({"kind": stage["kind"], "deletedAt": None}) <= 1:
                raise ConflictError("Нельзя удалить последний системный этап")
        return convert_objectids_to_str(await cls.soft_delete(stage_id))
