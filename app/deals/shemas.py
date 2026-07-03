from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, field_validator

from app.base_schemas import BaseMongoModel, PyObjectId


class SDealExpense(BaseModel):
    name: str
    amount: float


class SDealDeliveredQuantity(BaseModel):
    quantity: float
    unit: str
    date: str
    amountPurchase: float | None = None


class _ObjectIdConverterMixin:
    @field_validator(
        "serviceId", "customerId", "providerId", "stageId", "materialId",
        "shippingAddressId", "deliveryAddressId",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def convert_str_to_objectid(cls, v: Optional[str]) -> Optional[ObjectId]:
        if not v:
            return None
        try:
            return ObjectId(v)
        except Exception:
            raise ValueError(f"Invalid ObjectId format: {v}")


class SDealsInput(_ObjectIdConverterMixin, BaseModel):
    serviceId: Optional[PyObjectId] = None
    customerId: Optional[PyObjectId] = None
    providerId: Optional[PyObjectId] = None
    stageId: Optional[PyObjectId] = None
    materialId: Optional[PyObjectId] = None
    unitMeasurement: str | None = None

    quantity: float | None = None
    amountPurchaseUnit: float | None = None
    amountSalesUnit: float | None = None
    amountDelivery: float | None = None
    paymentMethod: str | None = None

    shippingAddress: str | None = None
    shippingAddressId: Optional[PyObjectId] = None
    methodReceiving: str | None = None
    deliveryAddress: str | None = None
    deliveryAddressId: Optional[PyObjectId] = None

    addExpenses: List[SDealExpense] | None = None
    deliveredQuantity: List[SDealDeliveredQuantity] | None = None
    notes: str | None = None
    OSSIG: bool | None = None

    model_config = ConfigDict(
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True,
    )


class SDealsPreviewInput(BaseModel):
    quantity: float = 0
    amountPurchaseUnit: float = 0
    amountSalesUnit: float = 0
    amountDelivery: float = 0
    paymentMethod: str | None = None
    addExpenses: List[SDealExpense] | None = None
    deliveredQuantity: List[SDealDeliveredQuantity] | None = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class SDealsPreviewResult(BaseModel):
    taxAmount: float
    companyProfit: float
    managerProfit: float
    amountPurchaseTotal: float
    amountSalesTotal: float
    actualCompanyProfit: float
    actualAmountSalesTotal: float
    actualAmountPurchaseTotal: float
    totalDeliveredQuantity: float
    ndsPercent: float
    managerShare: float
    totalAmount: float

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class SDealsStageUpdate(_ObjectIdConverterMixin, BaseModel):
    stageId: PyObjectId

    model_config = ConfigDict(
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True,
    )


class SDeals(BaseModel):
    createdAt: datetime | None = None
    userId: Optional[PyObjectId] | None = None
    serviceId: Optional[PyObjectId] | None = None
    customerId: Optional[PyObjectId] | None = None
    providerId: Optional[PyObjectId] | None = None
    stageId: Optional[PyObjectId] | None = None
    materialId: Optional[PyObjectId] | None = None
    unitMeasurement: str | None = None

    quantity: float | None = None
    amountPurchaseUnit: float | None = None
    amountPurchaseTotal: float | None = None
    amountSalesUnit: float | None = None
    amountSalesTotal: float | None = None
    amountDelivery: float | None = None
    companyProfit: float | None = None
    managerProfit: float | None = None
    paymentMethod: str | None = None
    ndsPercent: float | None = None
    ndsAmount: float | None = None
    totalAmount: float | None = None
    addExpenses: List[dict] | None = None

    shippingAddress: str | None = None
    shippingAddressId: Optional[PyObjectId] | None = None
    methodReceiving: str | None = None
    deliveryAddress: str | None = None
    deliveryAddressId: Optional[PyObjectId] | None = None

    deliveredQuantity: List[dict] | None = None
    notes: str | None = None
    OSSIG: bool | None = None
    updatedAt: datetime | None = None
    deletedAt: datetime | None = None

    calculationRuleId: Optional[PyObjectId] | None = None
    calculationRuleVersion: int | None = None

    actualCompanyProfit: float | None = None
    actualAmountSalesTotal: float | None = None
    actualAmountPurchaseTotal: float | None = None
    totalDeliveredQuantity: float | None = None
    managerShare: float | None = None

    @field_validator(
        "userId", "serviceId", "customerId", "providerId", "stageId", "materialId",
        "shippingAddressId", "deliveryAddressId", "calculationRuleId",
        mode="before",
    )
    @classmethod
    def convert_objectid_to_str(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        from_attributes=True,
        populate_by_name=True,
    )


class SDealsWithRelations(SDeals):
    service: Optional[dict] = None
    customer: Optional[dict] = None
    stage: Optional[dict] = None
    material: Optional[dict] = None
    shipping_address: Optional[dict] = None
    delivery_address: Optional[dict] = None
    user: Optional[dict] = None


# Обратная совместимость для импортов
SDealsAdd = SDealsInput
