from app.core.named_entity_service import NamedEntityService
from app.stages.repository import stages_repository


class StagesService(NamedEntityService):
    repository = stages_repository
    not_found_detail = "Этап не найден"
    conflict_detail = "Невозможно удалить этап — имеются связанные сделки"
    entity_label = "Этап"
    default_sort = [("order", 1)]

    @classmethod
    async def has_dependencies(cls, entity_id: str) -> bool:
        return await cls.count_deal_dependencies("stageId", entity_id)
