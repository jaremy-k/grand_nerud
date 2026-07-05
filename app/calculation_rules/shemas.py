from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuleInputsSchema(BaseModel):
    deal: List[str] = Field(default_factory=list)
    config: List[str] = Field(default_factory=list)
    user: List[str] = Field(default_factory=list)


class FormulaDefinitionSchema(BaseModel):
    expr: str = Field(..., min_length=1, max_length=2000)
    snapshot: bool = False


class FormulaMetadataSchema(BaseModel):
    label: str | None = None
    description: str | None = None
    group: str | None = None


class CalculationRuleSchema(BaseModel):
    inputs: RuleInputsSchema
    formulas: Dict[str, FormulaDefinitionSchema] = Field(..., min_length=1)
    metadata: Dict[str, FormulaMetadataSchema] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class CalculationRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    schema: CalculationRuleSchema
    isActive: bool = False

    model_config = ConfigDict(populate_by_name=True)


class CalculationRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    schema: CalculationRuleSchema | None = None
    isActive: bool | None = None

    model_config = ConfigDict(populate_by_name=True)


class CalculationRuleDto(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    version: int
    isActive: bool
    schema: CalculationRuleSchema
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
    schema: CalculationRuleSchema
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
