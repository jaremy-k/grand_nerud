from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.logger import logger
from app.materials.service import MaterialsService
from app.materials.shemas import SMaterials, SMaterialsAdd
from app.users.dependencies import get_current_user

router = APIRouter(
    prefix="/materials",
    tags=["Нерудные материалы"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{id}", response_model=SMaterials, summary="Получить материал по ID")
async def get_material(id: str) -> SMaterials:
    return await MaterialsService.get_by_id(id)


@router.get("", response_model=list[SMaterials], summary="Получить список материалов")
async def get_materials(
        data: SMaterials = Depends(),
        includeDeleted: bool = Query(False),
) -> list[SMaterials]:
    return await MaterialsService.list_materials(data, include_deleted=includeDeleted)


@router.post(
    "",
    response_model=SMaterials,
    summary="Добавить материал",
    status_code=status.HTTP_201_CREATED,
)
async def add_material(data: SMaterialsAdd):
    return await MaterialsService.create(data)


@router.patch("/{id}", response_model=SMaterials, summary="Обновить материал по ID")
async def update_material(id: str, data: SMaterialsAdd, background_tasks: BackgroundTasks):
    result = await MaterialsService.update(id, data)
    background_tasks.add_task(
        logger.info, "Material updated: id=%s", id,
        extra={"material_id": id, "action": "material_update"},
    )
    return result


@router.delete("/{id}", response_model=Optional[SMaterials], summary="Мягкое удаление материала")
async def safe_delete_material(
        id: str,
        background_tasks: BackgroundTasks,
        check_dependencies: bool = True,
):
    result = await MaterialsService.soft_delete(
        id,
        check_dependencies=check_dependencies,
        dependency_checker=MaterialsService.has_dependencies,
    )
    background_tasks.add_task(
        logger.info, "Material safely deleted: id=%s", id,
        extra={"material_id": id, "action": "safe_delete"},
    )
    return result
