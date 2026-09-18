from datetime import datetime
from typing import List, Literal

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_settings import SettingsConfigDict

CompanyRole = Literal["provider", "customer"]


class SCompanyContactPerson(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    position: str | None = Field(None, max_length=150)
    phone: str | None = Field(None, max_length=50)
    email: EmailStr | None = None
    comment: str | None = Field(None, max_length=500)


class SCompanies(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    abbreviatedName: str | None = None
    inn: str | int | None = None
    kpp: str | int | None = None
    contacts: List[dict] | None = None
    contactPersons: list[SCompanyContactPerson] | None = None
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
    contactPersons: list[SCompanyContactPerson] | None = None
    comment: str | None = None
    roles: list[CompanyRole] | None = None
    type: str | None = None

    model_config = SettingsConfigDict(
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True
    )
