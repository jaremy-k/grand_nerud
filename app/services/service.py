from app.core.named_entity_service import NamedEntityService
from app.services.repository import services_repository


class ServicesService(NamedEntityService):
    repository = services_repository
    not_found_detail = "Услуга не найдена"
    conflict_detail = "Невозможно удалить услугу — имеются связанные сделки"
    entity_label = "Услуга"
    default_sort = [("name", 1)]

    @classmethod
    async def has_dependencies(cls, entity_id: str) -> bool:
        return await cls.count_deal_dependencies("serviceId", entity_id)
