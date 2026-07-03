from typing import Literal

from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator


ServiceKind = Literal["sales", "sales_with_delivery", "utilization", "transport"]


class SServices(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    kind: ServiceKind | None = None
    deletedAt: datetime | None = None

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        json_encoders = {ObjectId: str}


class SServicesAdd(BaseModel):
    name: str | None = None
    kind: ServiceKind | None = None

    class Config:
        json_encoders = {ObjectId: str}
        from_attributes = True
        populate_by_name = True
