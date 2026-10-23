from datetime import datetime
from typing import List, Literal

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_settings import SettingsConfigDict

from app.adresses.shemas import MoscowAdministrativeDistrict

CompanyRole = Literal["provider", "customer"]


class SCompanyContactPerson(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    inn: str | int | None = None
    position: str | None = Field(None, max_length=150)
    phone: str | None = Field(None, max_length=50)
    email: EmailStr | None = None
    phones: list[str] | None = None
    emails: list[EmailStr] | None = None
    isPrimary: bool = False
    comment: str | None = Field(None, max_length=500)


class SCompanies(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    abbreviatedName: str | None = None
    inn: str | int | None = None
    kpp: str | int | None = None
    contacts: List[dict] | None = None
    contactPersons: list[SCompanyContactPerson] | None = None
    phones: list[str] | None = None
    emails: list[EmailStr] | None = None
    websites: list[str] | None = None
    source: str | None = None
    segments: list[str] | None = None
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


class SCompaniesWithDetails(SCompanies):
    addresses: list[dict] | None = None
    materialsWithPrices: list[dict] | None = None
    purchases: list[dict] | None = None


class SCompaniesAdd(BaseModel):
    name: str | None = None
    abbreviatedName: str | None = None
    inn: int | str | None = None
    kpp: int | str | None = None
    contacts: List[dict] | None = None
    contactPersons: list[SCompanyContactPerson] | None = None
    phones: list[str] | None = None
    emails: list[EmailStr] | None = None
    websites: list[str] | None = None
    source: str | None = None
    segments: list[str] | None = None
    comment: str | None = None
    roles: list[CompanyRole] | None = None
    type: str | None = None

    model_config = SettingsConfigDict(
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True
    )


class SCompanyPageQuery(BaseModel):
    page: int = Field(1, ge=1)
    pageSize: int = Field(15, ge=1, le=100)
    search: str | None = Field(None, max_length=200)
    role: CompanyRole | None = None
    includeDetails: bool = False
    city: str | None = Field(None, max_length=150)
    administrativeDistrict: MoscowAdministrativeDistrict | None = None
    district: str | None = Field(None, max_length=150)
    materialId: str | None = None
    priceUnit: str | None = Field(None, max_length=30)
    maxPrice: float | None = Field(None, ge=0, allow_inf_nan=False)
    priceSort: Literal["default", "asc", "desc"] = "default"
    sortBy: Literal["recent", "name"] = "recent"


class SCompanyImportError(BaseModel):
    row: int
    detail: str


class SCompanyImportResult(BaseModel):
    totalRows: int
    created: int
    updated: int
    skipped: int
    leadsCreated: int = 0
    leadsSkipped: int = 0
    errors: list[SCompanyImportError]
