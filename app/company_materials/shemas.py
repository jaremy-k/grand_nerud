from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.base_schemas import PyObjectId


class SCompanyMaterialInput(BaseModel):
    companyId: PyObjectId | None = None
    materialId: PyObjectId | None = None
    price: float | None = Field(None, ge=0)
    unit: str | None = Field(None, min_length=1, max_length=50)
    comment: str | None = None

    model_config = ConfigDict(
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True,
    )


class SCompanyMaterial(BaseModel):
    id: str | None = Field(None, alias="_id")
    companyId: str | None = None
    materialId: str | None = None
    price: float | None = None
    unit: str | None = None
    comment: str | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    deletedAt: datetime | None = None

    @field_validator("id", "companyId", "materialId", mode="before")
    @classmethod
    def convert_objectid_to_str(cls, value):
        if isinstance(value, ObjectId):
            return str(value)
        return value

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )


class SCompanyMaterialWithRelations(SCompanyMaterial):
    company: dict | None = None
    material: dict | None = None
