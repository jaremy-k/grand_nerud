from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CalculatorConfigDto(BaseModel):
    ndsPercent: float = Field(0.22, ge=0, le=1)
    defaultManagerShare: float = Field(0.05, ge=0, le=1)
    cashPaymentMethod: str = "наличный расчет"
    nonCashPaymentMethod: str = "безналичный расчет"
    updatedAt: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class CalculatorConfigUpdate(BaseModel):
    ndsPercent: float | None = Field(None, ge=0, le=1)
    defaultManagerShare: float | None = Field(None, ge=0, le=1)
    cashPaymentMethod: str | None = None
    nonCashPaymentMethod: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
