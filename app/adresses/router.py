from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.adresses.service import AdressesService
from app.adresses.shemas import SAdresses, SAdressesAdd
from app.logger import logger
from app.users.dependencies import get_current_privileged_user, get_current_user

router = APIRouter(
    prefix="/adresses",
    tags=["Адреса"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{id}", response_model=SAdresses, summary="Получить адрес по ID")
async def get_adress(id: str) -> SAdresses:
    return await AdressesService.get_by_id(id)


@router.get("", response_model=list[SAdresses], summary="Получить список адресов")
async def get_adresses(
        data: SAdresses = Depends(),
        includeDeleted: bool = Query(False),
) -> list[SAdresses]:
    return await AdressesService.list_entities(data, include_deleted=includeDeleted)


@router.post(
    "",
    response_model=SAdresses,
    summary="Добавить адрес",
    status_code=status.HTTP_201_CREATED,
)
async def add_adress(data: SAdressesAdd):
    return await AdressesService.create(data)


@router.patch(
    "/{id}",
    response_model=SAdresses,
    summary="Обновить адрес",
)
async def update_adress(id: str, data: SAdressesAdd, background_tasks: BackgroundTasks):
    result = await AdressesService.update(id, data)
    background_tasks.add_task(logger.info, "Address updated: id=%s", id)
    return result


@router.delete(
    "/{id}",
    response_model=Optional[SAdresses],
    summary="Мягкое удаление адреса",
    dependencies=[Depends(get_current_privileged_user)],
)
async def delete_adress(id: str, check_dependencies: bool = True):
    return await AdressesService.soft_delete(
        id,
        check_dependencies=check_dependencies,
        dependency_checker=AdressesService.has_dependencies,
    )
