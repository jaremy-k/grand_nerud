from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from starlette import status

from app.deals.service import DealsService
from app.deals.shemas import PaginatedResponse, PaginationParams, SDeals, SDealsAdd, SDealsWithRelations
from app.logger import logger
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(
    prefix="/deals",
    tags=["Сделки"],
)


@router.get("", response_model=PaginatedResponse, summary="Получить список сделок")
async def get_deals(
        pagination: PaginationParams = Depends(),
        sortBy: Optional[str] = Query(None, description="Поле для сортировки"),
        sortOrder: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Порядок сортировки"),
        includeRelations: bool = Query(False, description="Включать связанные объекты"),
        includeDeleted: bool = Query(False, description="Включать удалённые"),
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


@router.get("/admin/get", summary="Получить список сделок со связанными объектами")
async def get_deals_for_admins(data: SDeals = Depends()):
    return JSONResponse(content=await DealsService.list_with_relations(data))


@router.get(
    "/{id}",
    response_model=SDealsWithRelations,
    summary="Получить сделку с связанными объектами",
)
async def get_deal_with_relations(id: str):
    return JSONResponse(content=await DealsService.get_with_relations(id))


@router.post("", response_model=SDeals, summary="Добавить сделку", status_code=status.HTTP_201_CREATED)
async def add_deal(data: SDealsAdd, user: SUsersGet = Depends(get_current_user)):
    return await DealsService.create(data, user)


@router.patch("/{id}", response_model=SDeals, summary="Обновить сделку по ID")
async def update_deal(
        id: str,
        data: SDealsAdd,
        background_tasks: BackgroundTasks,
        user: SUsersGet = Depends(get_current_user),
):
    result = await DealsService.update(id, data)
    background_tasks.add_task(
        logger.info, "Deal updated: id=%s", id,
        extra={"deal_id": id, "action": "deal_update"},
    )
    return result


@router.delete("/{id}", response_model=Optional[SDeals], summary="Мягкое удаление сделки")
async def safe_delete_deal(
        id: str,
        background_tasks: BackgroundTasks,
        user: SUsersGet = Depends(get_current_user),
):
    result = await DealsService.soft_delete(id)
    background_tasks.add_task(
        logger.info, "Deal safely deleted: id=%s", id,
        extra={"deal_id": id, "action": "safe_delete"},
    )
    return result
