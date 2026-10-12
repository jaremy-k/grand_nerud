from datetime import date

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime

from app.core.object_id import parse_object_id
from app.core.pagination import PaginatedResponse
from app.tasks.service import TasksService
from app.tasks.shemas import (
    STasks,
    STasksCreate,
    STasksFilters,
    STasksPagination,
    STasksUpdate,
    TaskBucket,
    TaskStatus,
    TaskType,
)
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(prefix="/tasks", tags=["Tasks"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=PaginatedResponse)
async def get_tasks(
        page: int = Query(1, ge=1, le=1_000_000),
        pageSize: int = Query(100, ge=1, le=100),
        ownerId: str | None = Query(None),
        companyId: str | None = Query(None),
        leadId: str | None = Query(None),
        dealId: str | None = Query(None),
        status: TaskStatus | None = Query(None),
        type: TaskType | None = Query(None),
        dateFrom: date | AwareDatetime | None = Query(None),
        dateTo: date | AwareDatetime | None = Query(None),
        bucket: TaskBucket | None = Query(None),
        timezone: str = Query("Europe/Moscow"),
        user: SUsersGet = Depends(get_current_user),
) -> PaginatedResponse:
    filters = STasksFilters(
        ownerId=parse_object_id(ownerId, "ownerId") if ownerId is not None else None,
        companyId=parse_object_id(companyId, "companyId") if companyId is not None else None,
        leadId=parse_object_id(leadId, "leadId") if leadId is not None else None,
        dealId=parse_object_id(dealId, "dealId") if dealId is not None else None,
        status=status, type=type, dateFrom=dateFrom, dateTo=dateTo,
        bucket=bucket, timezone=timezone,
    )
    return await TasksService.list_tasks(filters, STasksPagination(page=page, pageSize=pageSize), user)


@router.get("/{id}", response_model=STasks)
async def get_task(id: str, user: SUsersGet = Depends(get_current_user)):
    return await TasksService.get_by_id(id, user)


@router.post("", response_model=STasks, status_code=status.HTTP_201_CREATED)
async def add_task(data: STasksCreate, user: SUsersGet = Depends(get_current_user)):
    return await TasksService.create(data, user)


@router.patch("/{id}", response_model=STasks)
async def update_task(id: str, data: STasksUpdate, user: SUsersGet = Depends(get_current_user)):
    return await TasksService.update(id, data, user)


@router.delete("/{id}", response_model=STasks)
async def delete_task(id: str, user: SUsersGet = Depends(get_current_user)):
    return await TasksService.soft_delete(id, user)
