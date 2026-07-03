from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FormulaFieldSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    label: str | None = None
    description: str | None = None
    expression: str = Field(..., min_length=1, max_length=2000)
    store: bool = True


class CalculationRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    fields: List[FormulaFieldSchema] = Field(..., min_length=1)
    isActive: bool = False

    model_config = ConfigDict(populate_by_name=True)


class CalculationRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    fields: List[FormulaFieldSchema] | None = Field(None, min_length=1)
    isActive: bool | None = None

    model_config = ConfigDict(populate_by_name=True)


class CalculationRuleDto(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    version: int
    isActive: bool
    fields: List[FormulaFieldSchema]
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class CalculationRuleTestInput(BaseModel):
    fields: List[FormulaFieldSchema]
    context: dict | None = None


class CalculationRuleTestResult(BaseModel):
    results: dict
    errors: List[str] = []


class CalculationRuleValidateResult(BaseModel):
    valid: bool
    errors: List[str] = []


class CalculationRuleDslDocs(BaseModel):
    variables: list
    functions: list
    syntax: list
