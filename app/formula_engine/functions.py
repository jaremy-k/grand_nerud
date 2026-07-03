"""Вспомогательные функции, доступные в DSL формул."""

from typing import Any


def sum_expenses(items: list[dict] | None) -> float:
    if not items:
        return 0.0
    return sum(float(item.get("amount") or 0) for item in items)


def sum_delivered_quantity(items: list[dict] | None) -> float:
    if not items:
        return 0.0
    return sum(float(item.get("quantity") or 0) for item in items)


def sum_delivered_purchase(items: list[dict] | None, unit_price: float) -> float:
    if not items:
        return 0.0
    total = 0.0
    for item in items:
        qty = float(item.get("quantity") or 0)
        amount_purchase = item.get("amountPurchase")
        if amount_purchase is not None:
            total += float(amount_purchase)
        else:
            total += unit_price * qty
    return total


def delivery_share(total_delivered: float, quantity: float) -> float:
    if quantity <= 0:
        return 0.0
    return total_delivered / quantity


def coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


DSL_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sumExpenses": sum_expenses,
    "sumDeliveredQuantity": sum_delivered_quantity,
    "sumDeliveredPurchase": sum_delivered_purchase,
    "deliveryShare": delivery_share,
    "coalesce": coalesce,
}

DSL_FUNCTION_DOCS = [
    {"name": "sumExpenses(addExpenses)", "description": "Сумма доп. расходов"},
    {"name": "sumDeliveredQuantity(deliveredQuantity)", "description": "Сумма доставленных объёмов"},
    {
        "name": "sumDeliveredPurchase(deliveredQuantity, amountPurchaseUnit)",
        "description": "Сумма закупки по доставленным партиям",
    },
    {"name": "deliveryShare(totalDeliveredQuantity, quantity)", "description": "Доля доставленного объёма"},
    {"name": "coalesce(a, b, ...)", "description": "Первое не-None значение"},
    {"name": "abs(x), min(a,b), max(a,b), round(x)", "description": "Математические функции"},
]

DSL_VARIABLE_DOCS = [
    {"name": "quantity", "description": "Количество"},
    {"name": "amountPurchaseUnit", "description": "Цена закупки за единицу"},
    {"name": "amountSalesUnit", "description": "Цена клиента за единицу"},
    {"name": "amountDelivery", "description": "Стоимость доставки"},
    {"name": "paymentMethod", "description": "Способ оплаты"},
    {"name": "managerShare", "description": "Доля менеджера (из профиля)"},
    {"name": "ndsPercentConfig", "description": "Текущая ставка НДС из настроек"},
    {"name": "defaultManagerShare", "description": "Дефолтная доля менеджера"},
    {"name": "cashPaymentMethod", "description": "Строка «наличный расчёт»"},
    {"name": "nonCashPaymentMethod", "description": "Строка «безналичный расчёт»"},
    {"name": "storedNdsPercent", "description": "Записанный НДС сделки (историчность)"},
    {"name": "addExpenses", "description": "Список доп. расходов (через функции)"},
    {"name": "deliveredQuantity", "description": "Список доставок (через функции)"},
]
