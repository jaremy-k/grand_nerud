from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator


class SStages(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    order: int | None = None
    deletedAt: datetime | None = None

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        json_encoders = {ObjectId: str}


class SStagesAdd(BaseModel):
    name: str | None = None
    order: int | None = None

    class Config:
        json_encoders = {ObjectId: str}
        from_attributes = True
        populate_by_name = True
