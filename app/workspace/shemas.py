from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.leads.shemas import SLead
from app.tasks.shemas import STasks

WorkspaceScope = Literal["mine", "team"]
T = TypeVar("T")


class SWorkspaceCompany(BaseModel):
    id: str = Field(alias="_id")
    name: str

    model_config = ConfigDict(populate_by_name=True)


class SWorkspaceLeadReference(BaseModel):
    id: str = Field(alias="_id")
    title: str

    model_config = ConfigDict(populate_by_name=True)


class SWorkspaceTask(STasks):
    company: SWorkspaceCompany | None = None
    lead: SWorkspaceLeadReference | None = None


class SWorkspacePreview(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    hasMore: bool


class SWorkspaceMeta(BaseModel):
    generatedAt: datetime
    timezone: str
    localDate: date
    scope: Literal["mine", "team", "owner"]
    ownerId: str | None
    limit: int


class SWorkspaceTasks(SWorkspaceMeta):
    overdue: SWorkspacePreview[SWorkspaceTask]
    today: SWorkspacePreview[SWorkspaceTask]
    upcoming: SWorkspacePreview[SWorkspaceTask]


class SWorkspaceLeads(SWorkspaceMeta):
    newLeads: SWorkspacePreview[SLead]
