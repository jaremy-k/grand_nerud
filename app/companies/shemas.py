from datetime import datetime
from typing import List

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import SettingsConfigDict


class SCompanies(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    abbreviatedName: str | None = None
    inn: str | int | None = None
    contacts: List[dict] | None = None
    type: str | None = None
    deletedAt: datetime | None = None

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    model_config = SettingsConfigDict(
        json_encoders={ObjectId: str}
    )


class SCompaniesAdd(BaseModel):
    name: str | None = None
    abbreviatedName: str | None = None
    inn: int | str | None = None
    contacts: List[dict] | None = None
    type: str | None = None

    model_config = SettingsConfigDict(
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True
    )
