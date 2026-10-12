from fastapi import APIRouter, Depends, Query, status

from app.core.crm import serialize_crm
from app.core.pagination import PaginatedResponse
from app.lead_stages.shemas import LeadStageKind
from app.leads.activities import LeadActivitiesService
from app.leads.service import LeadsService
from app.leads.shemas import (
    LeadPriority, SLead, SLeadActivity, SLeadActivityCreate, SLeadConversionResult,
    SLeadConvert, SLeadCreate, SLeadUpdate,
)
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(prefix="/leads", tags=["Лиды"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=PaginatedResponse)
async def list_leads(
        page: int = Query(1, ge=1), pageSize: int = Query(100, ge=1, le=200),
        ownerId: str | None = None, companyId: str | None = None, stageId: str | None = None,
        priority: LeadPriority | None = None, status: LeadStageKind | None = None,
        search: str | None = Query(None, max_length=200), user: SUsersGet = Depends(get_current_user),
):
    return await LeadsService.list_leads(user, page, pageSize, ownerId, companyId, stageId, priority, status, search)


@router.post("", response_model=SLead, status_code=status.HTTP_201_CREATED)
async def create_lead(data: SLeadCreate, user: SUsersGet = Depends(get_current_user)):
    return await LeadsService.create(data, user)


@router.get("/{id}", response_model=SLead)
async def get_lead(id: str, user: SUsersGet = Depends(get_current_user)):
    return await LeadsService.get_by_id(id, user)


@router.patch("/{id}", response_model=SLead)
async def update_lead(id: str, data: SLeadUpdate, user: SUsersGet = Depends(get_current_user)):
    return await LeadsService.update(id, data, user)


@router.delete("/{id}", response_model=SLead)
async def delete_lead(id: str, user: SUsersGet = Depends(get_current_user)):
    return await LeadsService.delete(id, user)


@router.get("/{id}/activities", response_model=PaginatedResponse)
async def list_lead_activities(
        id: str, page: int = Query(1, ge=1), pageSize: int = Query(100, ge=1, le=200),
        user: SUsersGet = Depends(get_current_user),
):
    lead = await LeadsService.get_raw(id, user)
    response = await LeadActivitiesService.repository.find_paginated(
        leadId=lead["_id"], skip=(page - 1) * pageSize, limit=pageSize, sort=[("createdAt", -1)],
    )
    response.items = serialize_crm(response.items)
    await LeadsService.get_raw(id, user)
    return response


@router.post("/{id}/activities", response_model=SLeadActivity, status_code=status.HTTP_201_CREATED)
async def add_lead_activity(id: str, data: SLeadActivityCreate, user: SUsersGet = Depends(get_current_user)):
    await LeadsService.get_raw(id, user)
    return await LeadActivitiesService.record(id, user, data.type, data.comment)


@router.post("/{id}/convert", response_model=SLeadConversionResult)
async def convert_lead(id: str, data: SLeadConvert, user: SUsersGet = Depends(get_current_user)):
    return await LeadsService.convert(id, data, user)
