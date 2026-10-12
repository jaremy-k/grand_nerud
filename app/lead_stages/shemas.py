from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LeadStageKind = Literal["new", "in_progress", "qualified", "deferred", "unqualified", "converted"]


class SLeadStageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    order: int = Field(0, ge=0)
    kind: LeadStageKind = "in_progress"

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SLeadStageUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    order: int | None = Field(None, ge=0)
    kind: LeadStageKind | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SLeadStage(SLeadStageCreate):
    id: str = Field(alias="_id")
    deletedAt: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)
