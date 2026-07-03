from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.logger import logger
from app.users.dependencies import get_current_user
from app.vehicles.service import VehiclesService
from app.vehicles.shemas import SVehicles, SVehiclesAdd

router = APIRouter(
    prefix="/vehicles",
    tags=["Транспорт"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{id}", response_model=SVehicles, summary="Получить транспорт по ID")
async def get_vehicle(id: str) -> SVehicles:
    return await VehiclesService.get_by_id(id)


@router.get("", response_model=list[SVehicles], summary="Получить список транспорта")
async def get_vehicles(
        data: SVehicles = Depends(),
        includeDeleted: bool = Query(False),
) -> list[SVehicles]:
    return await VehiclesService.list_entities(data, include_deleted=includeDeleted)


@router.post("", response_model=SVehicles, summary="Добавить транспорт", status_code=status.HTTP_201_CREATED)
async def add_vehicle(data: SVehiclesAdd):
    return await VehiclesService.create(data)


@router.patch("/{id}", response_model=SVehicles, summary="Обновить транспорт")
async def update_vehicle(id: str, data: SVehiclesAdd, background_tasks: BackgroundTasks):
    result = await VehiclesService.update(id, data)
    background_tasks.add_task(logger.info, "Vehicle updated: id=%s", id)
    return result


@router.delete("/{id}", response_model=Optional[SVehicles], summary="Мягкое удаление транспорта")
async def delete_vehicle(id: str, check_dependencies: bool = True):
    return await VehiclesService.soft_delete(
        id,
        check_dependencies=check_dependencies,
        dependency_checker=VehiclesService.has_dependencies,
    )
