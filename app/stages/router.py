from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.logger import logger
from app.stages.service import StagesService
from app.stages.shemas import SStages, SStagesAdd
from app.users.dependencies import get_current_user

router = APIRouter(
    prefix="/stages",
    tags=["Этапы сделки"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/{id}", response_model=SStages, summary="Получить этап по ID")
async def get_stage(id: str) -> SStages:
    return await StagesService.get_by_id(id)


@router.get("", response_model=list[SStages], summary="Получить список этапов")
async def get_stages(
        data: SStages = Depends(),
        includeDeleted: bool = Query(False),
) -> list[SStages]:
    return await StagesService.list_entities(data, include_deleted=includeDeleted)


@router.post("", response_model=SStages, summary="Добавить этап", status_code=status.HTTP_201_CREATED)
async def add_stage(data: SStagesAdd):
    return await StagesService.create(data)


@router.patch("/{id}", response_model=SStages, summary="Обновить этап")
async def update_stage(id: str, data: SStagesAdd, background_tasks: BackgroundTasks):
    result = await StagesService.update(id, data)
    background_tasks.add_task(logger.info, "Stage updated: id=%s", id)
    return result


@router.delete("/{id}", response_model=Optional[SStages], summary="Мягкое удаление этапа")
async def delete_stage(id: str, check_dependencies: bool = True):
    return await StagesService.soft_delete(
        id,
        check_dependencies=check_dependencies,
        dependency_checker=StagesService.has_dependencies,
    )
