from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
Cost = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3, allow_inf_nan=False)]


class OperationWrite(BaseModel):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    requestId: UUID
    comment: str = Field("", max_length=1000)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PaymentWrite(OperationWrite):
    kind: Literal["customer", "provider", "delivery", "other"] = "customer"
    status: Literal["planned", "paid"] = "planned"
    amount: Money
    dueDate: date | None = None
    actualDate: date | None = None
    reference: str = Field("", max_length=100)

    @model_validator(mode="after")
    def dates(self):
        if self.status == "planned" and self.dueDate is None:
            raise ValueError("Укажите плановую дату оплаты")
        if self.status == "paid" and self.actualDate is None:
            raise ValueError("Укажите дату платежа")
        if self.actualDate and self.actualDate > datetime.now(ZoneInfo("Europe/Moscow")).date():
            raise ValueError("Фактическая дата не может быть в будущем")
        if self.status == "planned" and self.actualDate is not None:
            raise ValueError("Плановый платёж не содержит фактическую дату")
        return self


class ShipmentWrite(OperationWrite):
    status: Literal["planned", "delivered"] = "planned"
    quantity: Quantity
    unit: str = Field(min_length=1, max_length=30)
    plannedDate: date | None = None
    actualDate: date | None = None
    amountPurchase: Cost | None = None
    deliveryCost: Cost | None = None
    shippingAddressId: str | None = None
    deliveryAddressId: str | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.status == "planned" and self.plannedDate is None:
            raise ValueError("Укажите плановую дату поставки")
        if self.status == "delivered" and self.actualDate is None:
            raise ValueError("Укажите фактическую дату поставки")
        if self.actualDate and self.actualDate > datetime.now(ZoneInfo("Europe/Moscow")).date():
            raise ValueError("Фактическая дата не может быть в будущем")
        if self.status == "planned" and self.actualDate is not None:
            raise ValueError("Плановая поставка не содержит фактическую дату")
        return self


class CancelOperation(BaseModel):
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=3, max_length=1000)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
