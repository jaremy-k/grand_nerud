from typing import Any

from app.calculator_config.models import CalculatorConfig

DEFAULT_CONFIG = CalculatorConfig()


def resolve_nds_percent(
        payment_method: str | None,
        config: CalculatorConfig,
        stored_nds_percent: float | None = None,
) -> float:
    """Для существующих сделок сохраняет записанный НДС (историчность)."""
    if stored_nds_percent is not None:
        return float(stored_nds_percent)
    if payment_method == config.non_cash_payment_method:
        return config.nds_percent
    return 0.0


def get_nds_percent(
        payment_method: str | None,
        config: CalculatorConfig = DEFAULT_CONFIG,
) -> float:
    return resolve_nds_percent(payment_method, config)


def get_manager_share(
        user_profit: dict | None,
        payment_method: str | None,
        config: CalculatorConfig = DEFAULT_CONFIG,
) -> float:
    profit = user_profit or {}
    if payment_method == config.cash_payment_method:
        cash = profit.get("cash") or {}
        return float(cash.get("alone", config.default_manager_share))
    non_cash = profit.get("nonCash") or {}
    return float(non_cash.get("alone", config.default_manager_share))


def _extra_expenses_sum(extra_expenses: list[dict] | None) -> float:
    if not extra_expenses:
        return 0.0
    return sum(float(item.get("amount") or 0) for item in extra_expenses)


def calculate_deal_totals(
        quantity: float,
        amount_purchase_unit: float,
        amount_sales_unit: float,
        manager_share: float,
        tax_percent: float,
        delivery_price: float,
        extra_expenses: list[dict] | None,
) -> dict[str, float]:
    amount_sales_total = amount_sales_unit * quantity
    amount_purchase_total = amount_purchase_unit * quantity
    tax_amount = (amount_sales_total / (1 + tax_percent)) * tax_percent if tax_percent else 0.0
    extra_sum = _extra_expenses_sum(extra_expenses)
    company_profit = amount_sales_total - amount_purchase_total - delivery_price - extra_sum
    manager_profit = company_profit * manager_share

    return {
        "amountSalesTotal": amount_sales_total,
        "amountPurchaseTotal": amount_purchase_total,
        "ndsAmount": tax_amount,
        "companyProfit": company_profit,
        "managerProfit": manager_profit,
        "totalAmount": amount_sales_total,
    }


def calculate_actual_profit(
        delivered_items: list[dict],
        quantity: float,
        amount_purchase_unit: float,
        amount_sales_unit: float,
        delivery_price: float,
        extra_expenses: list[dict] | None,
) -> dict[str, float]:
    total_delivered_quantity = sum(float(item.get("quantity") or 0) for item in delivered_items)
    if total_delivered_quantity <= 0 or quantity <= 0:
        return {
            "actualAmountSalesTotal": 0.0,
            "actualAmountPurchaseTotal": 0.0,
            "actualCompanyProfit": 0.0,
            "totalDeliveredQuantity": 0.0,
        }

    share = total_delivered_quantity / quantity
    actual_amount_sales_total = amount_sales_unit * total_delivered_quantity
    actual_amount_purchase_total = 0.0
    for item in delivered_items:
        item_qty = float(item.get("quantity") or 0)
        amount_purchase = item.get("amountPurchase")
        if amount_purchase is not None:
            actual_amount_purchase_total += float(amount_purchase)
        else:
            actual_amount_purchase_total += amount_purchase_unit * item_qty

    extra_sum = _extra_expenses_sum(extra_expenses)
    actual_company_profit = (
            actual_amount_sales_total
            - actual_amount_purchase_total
            - delivery_price * share
            - extra_sum * share
    )

    return {
        "actualAmountSalesTotal": actual_amount_sales_total,
        "actualAmountPurchaseTotal": actual_amount_purchase_total,
        "actualCompanyProfit": actual_company_profit,
        "totalDeliveredQuantity": total_delivered_quantity,
    }


def compute_deal_fields(
        *,
        quantity: float,
        amount_purchase_unit: float,
        amount_sales_unit: float,
        amount_delivery: float,
        payment_method: str | None,
        add_expenses: list[dict] | None,
        delivered_quantity: list[dict] | None,
        manager_share: float,
        config: CalculatorConfig = DEFAULT_CONFIG,
        stored_nds_percent: float | None = None,
) -> dict[str, Any]:
    tax_percent = resolve_nds_percent(payment_method, config, stored_nds_percent)
    totals = calculate_deal_totals(
        quantity=quantity,
        amount_purchase_unit=amount_purchase_unit,
        amount_sales_unit=amount_sales_unit,
        manager_share=manager_share,
        tax_percent=tax_percent,
        delivery_price=amount_delivery,
        extra_expenses=add_expenses,
    )
    actual = calculate_actual_profit(
        delivered_items=delivered_quantity or [],
        quantity=quantity,
        amount_purchase_unit=amount_purchase_unit,
        amount_sales_unit=amount_sales_unit,
        delivery_price=amount_delivery,
        extra_expenses=add_expenses,
    )
    return {
        **totals,
        **actual,
        "ndsPercent": tax_percent,
        "managerShare": manager_share,
    }


def enrich_deal_document(
        deal: dict,
        user_profit: dict | None = None,
        config: CalculatorConfig = DEFAULT_CONFIG,
) -> dict:
    """Добавляет вычисляемые поля к документу сделки при чтении."""
    stored_nds = deal.get("ndsPercent")
    if stored_nds is not None:
        stored_nds = float(stored_nds)

    manager_share = get_manager_share(user_profit, deal.get("paymentMethod"), config)
    computed = compute_deal_fields(
        quantity=float(deal.get("quantity") or 0),
        amount_purchase_unit=float(deal.get("amountPurchaseUnit") or 0),
        amount_sales_unit=float(deal.get("amountSalesUnit") or 0),
        amount_delivery=float(deal.get("amountDelivery") or 0),
        payment_method=deal.get("paymentMethod"),
        add_expenses=deal.get("addExpenses"),
        delivered_quantity=deal.get("deliveredQuantity"),
        manager_share=manager_share,
        config=config,
        stored_nds_percent=stored_nds,
    )
    return {**deal, **computed}
