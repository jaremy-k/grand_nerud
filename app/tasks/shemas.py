from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.base_schemas import PyObjectId
from app.core.mongo_utils import convert_objectids_to_str

TaskType = Literal["call", "meeting", "email", "other"]
TaskStatus = Literal["open", "completed", "cancelled"]
TaskBucket = Literal["today", "overdue", "upcoming"]


class _TaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("title", check_fields=False)
    @classmethod
    def validate_title(cls, value):
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("title must not be blank")
        return value


class STasksCreate(_TaskInput):
    title: str = Field(min_length=1)
    type: TaskType = "call"
    dueAt: AwareDatetime
    ownerId: PyObjectId | None = None
    companyId: PyObjectId | None = None
    leadId: PyObjectId | None = None
    dealId: PyObjectId | None = None
    comment: str | None = None
    status: TaskStatus = "open"
    result: str | None = None


class STasksUpdate(_TaskInput):
    title: str | None = Field(None, min_length=1)
    type: TaskType | None = None
    dueAt: AwareDatetime | None = None
    ownerId: PyObjectId | None = None
    companyId: PyObjectId | None = None
    leadId: PyObjectId | None = None
    dealId: PyObjectId | None = None
    comment: str | None = None
    status: TaskStatus | None = None
    result: str | None = None

    @field_validator("title", "type", "dueAt", "ownerId", "status", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class STasksFilters(BaseModel):
    ownerId: PyObjectId | None = None
    companyId: PyObjectId | None = None
    leadId: PyObjectId | None = None
    dealId: PyObjectId | None = None
    status: TaskStatus | None = None
    type: TaskType | None = None
    dateFrom: date | AwareDatetime | None = None
    dateTo: date | AwareDatetime | None = None
    bucket: TaskBucket | None = None
    timezone: str = "Europe/Moscow"


class STasksPagination(BaseModel):
    page: int = Field(1, ge=1, le=1_000_000)
    pageSize: int = Field(100, ge=1, le=100)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.pageSize

    @property
    def limit(self) -> int:
        return self.pageSize


class STasks(BaseModel):
    id: str = Field(alias="_id")
    title: str
    type: TaskType = "call"
    dueAt: datetime
    ownerId: str
    createdById: str | None = None
    companyId: str | None = None
    leadId: str | None = None
    dealId: str | None = None
    comment: str | None = None
    status: TaskStatus = "open"
    result: str | None = None
    followUp: bool = False
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    deletedAt: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id", "ownerId", "createdById", "companyId", "leadId", "dealId", mode="before")
    @classmethod
    def serialize_ids(cls, value):
        return convert_objectids_to_str(value)
