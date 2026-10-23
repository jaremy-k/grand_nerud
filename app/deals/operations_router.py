from fastapi import APIRouter, Depends, Query, Response

from app.deals.operation_schemas import CancelOperation, PaymentWrite, ShipmentWrite
from app.deals.operations_service import DealOperationsService
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(prefix="/{deal_id}", tags=["Оплаты и поставки"], dependencies=[Depends(get_current_user)])


@router.get("/operations")
async def operations(deal_id: str, response: Response, historyPage: int = Query(1, ge=1), historyPageSize: int = Query(25, ge=1, le=100), user: SUsersGet = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return await DealOperationsService.read(deal_id, user, historyPage, historyPageSize)


@router.post("/payments", status_code=201)
async def add_payment(deal_id: str, data: PaymentWrite, user: SUsersGet = Depends(get_current_user)):
    return await DealOperationsService.write(deal_id, "payments", data, user)


@router.patch("/payments/{entry_id}")
async def edit_payment(deal_id: str, entry_id: str, data: PaymentWrite, user: SUsersGet = Depends(get_current_user)):
    return await DealOperationsService.write(deal_id, "payments", data, user, entry_id)


@router.post("/payments/{entry_id}/cancel")
async def cancel_payment(deal_id: str, entry_id: str, data: CancelOperation, user: SUsersGet = Depends(get_current_user)):
    return await DealOperationsService.write(deal_id, "payments", data, user, entry_id, cancel=True)


@router.post("/shipments", status_code=201)
async def add_shipment(deal_id: str, data: ShipmentWrite, user: SUsersGet = Depends(get_current_user)):
    return await DealOperationsService.write(deal_id, "shipments", data, user)


@router.patch("/shipments/{entry_id}")
async def edit_shipment(deal_id: str, entry_id: str, data: ShipmentWrite, user: SUsersGet = Depends(get_current_user)):
    return await DealOperationsService.write(deal_id, "shipments", data, user, entry_id)


@router.post("/shipments/{entry_id}/cancel")
async def cancel_shipment(deal_id: str, entry_id: str, data: CancelOperation, user: SUsersGet = Depends(get_current_user)):
    return await DealOperationsService.write(deal_id, "shipments", data, user, entry_id, cancel=True)
