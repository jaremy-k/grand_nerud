from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.logger import logger
from app.services.service import ServicesService
from app.services.shemas import SServices, SServicesAdd
from app.users.dependencies import get_current_user

router = APIRouter(
    prefix="/services",
    tags=["Оказываемые услуги"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{id}", response_model=SServices, summary="Получить услугу по ID")
async def get_service(id: str) -> SServices:
    return await ServicesService.get_by_id(id)


@router.get("", response_model=list[SServices], summary="Получить список услуг")
async def get_services(
        data: SServices = Depends(),
        includeDeleted: bool = Query(False),
) -> list[SServices]:
    return await ServicesService.list_entities(data, include_deleted=includeDeleted)


@router.post("", response_model=SServices, summary="Добавить услугу", status_code=status.HTTP_201_CREATED)
async def add_service(data: SServicesAdd):
    return await ServicesService.create(data)


@router.patch("/{id}", response_model=SServices, summary="Обновить услугу")
async def update_service(id: str, data: SServicesAdd, background_tasks: BackgroundTasks):
    result = await ServicesService.update(id, data)
    background_tasks.add_task(logger.info, "Service updated: id=%s", id)
    return result


@router.delete("/{id}", response_model=Optional[SServices], summary="Мягкое удаление услуги")
async def delete_service(id: str, check_dependencies: bool = True):
    return await ServicesService.soft_delete(
        id,
        check_dependencies=check_dependencies,
        dependency_checker=ServicesService.has_dependencies,
    )
