from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator


class SAdresses(BaseModel):
    id: str | None = Field(None, alias="_id")
    companyId: str | None = None
    coordinates: list | None = None
    cityId: str | None = None
    adressDetail: dict | None = None
    typeAdress: str | None = None
    deletedAt: datetime | None = None

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        json_encoders = {ObjectId: str}


class SAdressesAdd(BaseModel):
    companyId: str | None = None
    coordinates: list | None = None
    cityId: str | None = None
    adressDetail: dict | None = None
    typeAdress: str | None = None

    class Config:
        json_encoders = {ObjectId: str}
        from_attributes = True
        populate_by_name = True
