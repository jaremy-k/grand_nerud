from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.base_schemas import PyObjectId
from app.companies.shemas import SCompanyContactPerson
from app.deals.shemas import SDeals, SDealsInput

LeadPriority = Literal["low", "normal", "high", "urgent"]


class SLeadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    companyId: PyObjectId | None = None
    contactPerson: SCompanyContactPerson | None = None
    ownerId: PyObjectId | None = None
    stageId: PyObjectId | None = None
    source: str | None = None
    priority: LeadPriority = "normal"
    materialIds: list[PyObjectId] = Field(default_factory=list)
    quantity: float | None = Field(None, ge=0)
    unitMeasurement: str | None = None
    objectAddressId: PyObjectId | None = None
    objectAddress: str | None = None
    budget: float | None = Field(None, ge=0)
    expectedPurchaseAt: AwareDatetime | None = None
    nextContactAt: AwareDatetime | None = None
    lossReason: str | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SLeadUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    companyId: PyObjectId | None = None
    contactPerson: SCompanyContactPerson | None = None
    ownerId: PyObjectId | None = None
    stageId: PyObjectId | None = None
    source: str | None = None
    priority: LeadPriority | None = None
    materialIds: list[PyObjectId] | None = None
    quantity: float | None = Field(None, ge=0)
    unitMeasurement: str | None = None
    objectAddressId: PyObjectId | None = None
    objectAddress: str | None = None
    budget: float | None = Field(None, ge=0)
    expectedPurchaseAt: AwareDatetime | None = None
    nextContactAt: AwareDatetime | None = None
    lossReason: str | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SLead(BaseModel):
    id: str = Field(alias="_id")
    title: str
    companyId: str | None = None
    contactPerson: SCompanyContactPerson | None = None
    ownerId: str
    createdById: str
    stageId: str
    source: str | None = None
    priority: LeadPriority = "normal"
    materialIds: list[str] = Field(default_factory=list)
    quantity: float | None = None
    unitMeasurement: str | None = None
    objectAddressId: str | None = None
    objectAddress: str | None = None
    budget: float | None = None
    expectedPurchaseAt: datetime | None = None
    nextContactAt: datetime | None = None
    followUpTaskId: str | None = None
    lossReason: str | None = None
    notes: str | None = None
    dealId: str | None = None
    convertedAt: datetime | None = None
    conversionPending: bool = False
    createdAt: datetime
    updatedAt: datetime
    deletedAt: datetime | None = None
    company: dict | None = None
    stage: dict | None = None
    materials: list[dict] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class SLeadActivityCreate(BaseModel):
    type: Literal["note", "call", "meeting", "email"] = "note"
    comment: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SLeadActivity(BaseModel):
    id: str = Field(alias="_id")
    leadId: str
    userId: str
    type: str
    comment: str
    details: dict | None = None
    createdAt: datetime


class SLeadConversionResult(BaseModel):
    lead: SLead
    deal: SDeals


SLeadConvert = SDealsInput
