from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from starlette import status

from app.core.pagination import PaginatedResponse, PaginationParams
from app.deals.service import DealsService
from app.deals.shemas import (
    SDeals,
    SDealsInput,
    SDealsPreviewInput,
    SDealsPreviewResult,
    SDealsStageUpdate,
    SDealsWithRelations,
)
from app.logger import logger
from app.users.dependencies import get_current_privileged_user, get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(
    prefix="/deals",
    tags=["Сделки"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=PaginatedResponse, summary="Получить список сделок")
async def get_deals(
        pagination: PaginationParams = Depends(),
        sortBy: Optional[str] = Query(None, description="Поле для сортировки"),
        sortOrder: Optional[str] = Query("asc", pattern="^(asc|desc)$"),
        includeRelations: bool = Query(False),
        includeDeleted: bool = Query(False),
        data: SDeals = Depends(),
        user: SUsersGet = Depends(get_current_user),
) -> PaginatedResponse:
    return await DealsService.list_deals(
        filters=data,
        pagination=pagination,
        user=user,
        sort_by=sortBy,
        sort_order=sortOrder,
        include_relations=includeRelations,
        include_deleted=includeDeleted,
    )


@router.get("/admin/all", response_model=list[SDealsWithRelations], summary="Сделки со связями (админ/руководитель)")
async def get_deals_for_admins(
        data: SDeals = Depends(),
        user: SUsersGet = Depends(get_current_privileged_user),
):
    return await DealsService.list_with_relations(data, user)


@router.post("/preview", response_model=SDealsPreviewResult, summary="Предпросмотр расчётов по сделке")
async def preview_deal(
        data: SDealsPreviewInput,
        user: SUsersGet = Depends(get_current_user),
) -> SDealsPreviewResult:
    return await DealsService.preview(data, user)


@router.get("/{id}", response_model=SDealsWithRelations, summary="Получить сделку со связями")
async def get_deal_with_relations(id: str, user: SUsersGet = Depends(get_current_user)):
    return await DealsService.get_with_relations(id, user)


@router.post("", response_model=SDeals, summary="Добавить сделку", status_code=status.HTTP_201_CREATED)
async def add_deal(data: SDealsInput, user: SUsersGet = Depends(get_current_user)):
    return await DealsService.create(data, user)


@router.patch("/{id}", response_model=SDeals, summary="Обновить сделку")
async def update_deal(
        id: str,
        data: SDealsInput,
        background_tasks: BackgroundTasks,
        user: SUsersGet = Depends(get_current_user),
):
    result = await DealsService.update(id, data, user)
    background_tasks.add_task(logger.info, "Deal updated: id=%s", id)
    return result


@router.patch("/{id}/stage", response_model=SDeals, summary="Обновить этап сделки")
async def update_deal_stage(
        id: str,
        data: SDealsStageUpdate,
        user: SUsersGet = Depends(get_current_user),
):
    return await DealsService.update_stage(id, str(data.stageId), user)


@router.delete("/{id}", response_model=Optional[SDeals], summary="Мягкое удаление сделки")
async def safe_delete_deal(id: str, user: SUsersGet = Depends(get_current_user)):
    return await DealsService.soft_delete(id, user)
