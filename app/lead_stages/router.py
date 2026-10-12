from fastapi import APIRouter, Depends, status

from app.lead_stages.service import LeadStagesService
from app.lead_stages.shemas import SLeadStage, SLeadStageCreate, SLeadStageUpdate
from app.users.dependencies import get_current_privileged_user, get_current_user

router = APIRouter(prefix="/lead-stages", tags=["Этапы лидов"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[SLeadStage])
async def list_lead_stages():
    return await LeadStagesService.list_stages()


@router.post("", response_model=SLeadStage, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(get_current_privileged_user)])
async def create_lead_stage(data: SLeadStageCreate):
    return await LeadStagesService.create(data)


@router.patch("/{id}", response_model=SLeadStage, dependencies=[Depends(get_current_privileged_user)])
async def update_lead_stage(id: str, data: SLeadStageUpdate):
    return await LeadStagesService.update(id, data)


@router.delete("/{id}", response_model=SLeadStage, dependencies=[Depends(get_current_privileged_user)])
async def delete_lead_stage(id: str):
    return await LeadStagesService.delete(id)
