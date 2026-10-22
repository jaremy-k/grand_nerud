from fastapi import APIRouter, Depends, Query, Response

from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet
from app.workspace.service import WorkspaceService
from app.workspace.shemas import SWorkspaceLeads, SWorkspaceTasks, WorkspaceScope

router = APIRouter(prefix="/workspace", tags=["Рабочий стол"], dependencies=[Depends(get_current_user)])


@router.get("/tasks", response_model=SWorkspaceTasks)
async def workspace_tasks(
        response: Response,
        scope: WorkspaceScope = Query("mine"),
        ownerId: str | None = Query(None, min_length=1),
        timezone: str = Query("Europe/Moscow", min_length=1, max_length=100),
        limit: int = Query(6, ge=1, le=20),
        user: SUsersGet = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    return await WorkspaceService.tasks(user, scope, ownerId, timezone, limit)


@router.get("/leads", response_model=SWorkspaceLeads)
async def workspace_leads(
        response: Response,
        scope: WorkspaceScope = Query("mine"),
        ownerId: str | None = Query(None, min_length=1),
        timezone: str = Query("Europe/Moscow", min_length=1, max_length=100),
        limit: int = Query(6, ge=1, le=20),
        user: SUsersGet = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"
    return await WorkspaceService.leads(user, scope, ownerId, timezone, limit)
