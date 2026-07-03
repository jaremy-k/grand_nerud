from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, field_validator, Field


class SVehicles(BaseModel):
    id: str | None = Field(None, alias="_id")
    companyId: str | None = None
    number: str | None = None
    region: int | None = None
    mark: str | None = None
    model: str | None = None
    year: int | None = None
    color: str | None = None
    deletedAt: datetime | None = None

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        json_encoders = {ObjectId: str}


class SVehiclesAdd(BaseModel):
    companyId: str | None = None
    number: str | None = None
    region: int | None = None
    mark: str | None = None
    model: str | None = None
    year: int | None = None
    color: str | None = None

    class Config:
        json_encoders = {ObjectId: str}
        from_attributes = True
        populate_by_name = True
