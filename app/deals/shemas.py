from datetime import datetime
from typing import Any, List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

from app.base_schemas import BaseMongoModel, PyObjectId


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

    @field_validator(
        "userId", "serviceId", "customerId", "providerId", "stageId", "materialId",
        "shippingAddressId", "deliveryAddressId",
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


class SDealsAdd(BaseModel):
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

    @field_validator(
        "serviceId", "customerId", "providerId", "stageId", "materialId", "userId",
        "shippingAddressId", "deliveryAddressId",
    )
    @classmethod
    def convert_str_to_objectid(cls, v: Optional[str]) -> Optional[ObjectId]:
        if not v:
            return None
        try:
            return ObjectId(v)
        except Exception:
            raise ValueError(f"Invalid ObjectId format: {v}")

    model_config = ConfigDict(
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
