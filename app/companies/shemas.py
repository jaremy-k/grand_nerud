from datetime import datetime
from typing import List, Literal

from bson import ObjectId
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import SettingsConfigDict

CompanyRole = Literal["provider", "customer"]


class SCompanies(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    abbreviatedName: str | None = None
    inn: str | int | None = None
    kpp: str | int | None = None
    contacts: List[dict] | None = None
    comment: str | None = None
    roles: list[CompanyRole] | None = None
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
    kpp: int | str | None = None
    contacts: List[dict] | None = None
    comment: str | None = None
    roles: list[CompanyRole] | None = None
    type: str | None = None

    model_config = SettingsConfigDict(
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True
    )
