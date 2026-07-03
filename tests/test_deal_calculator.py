import pytest

from app.calculator_config.models import CalculatorConfig
from app.deals.calculator import (
    calculate_actual_profit,
    calculate_deal_totals,
    compute_deal_fields,
    get_manager_share,
    get_nds_percent,
    resolve_nds_percent,
)

CONFIG = CalculatorConfig()


def test_get_nds_percent_cash():
    assert get_nds_percent("наличный расчет", CONFIG) == 0.0


def test_get_nds_percent_non_cash():
    assert get_nds_percent("безналичный расчет", CONFIG) == 0.22


def test_resolve_nds_percent_uses_stored_for_historical():
    assert resolve_nds_percent("безналичный расчет", CONFIG, stored_nds_percent=0.18) == 0.18


def test_resolve_nds_percent_uses_config_for_new_deals():
    assert resolve_nds_percent("безналичный расчет", CONFIG, stored_nds_percent=None) == 0.22


def test_get_manager_share_defaults():
    assert get_manager_share(None, "наличный расчет", CONFIG) == 0.05
    assert get_manager_share(None, "безналичный расчет", CONFIG) == 0.05


def test_get_manager_share_from_user():
    profit = {
        "cash": {"alone": 0.1, "withPartners": 0.05},
        "nonCash": {"alone": 0.15, "withPartners": 0.08},
    }
    assert get_manager_share(profit, "наличный расчет", CONFIG) == 0.1
    assert get_manager_share(profit, "безналичный расчет", CONFIG) == 0.15


def test_calculate_deal_totals_basic():
    result = calculate_deal_totals(
        quantity=10,
        amount_purchase_unit=100,
        amount_sales_unit=200,
        manager_share=0.1,
        tax_percent=0.22,
        delivery_price=500,
        extra_expenses=[{"name": "fee", "amount": 200}],
    )
    assert result["amountSalesTotal"] == 2000
    assert result["amountPurchaseTotal"] == 1000
    assert result["companyProfit"] == 300
    assert result["managerProfit"] == pytest.approx(30)
    assert result["ndsAmount"] == pytest.approx(2000 / 1.22 * 0.22)
    assert result["totalAmount"] == 2000


def test_calculate_actual_profit_with_custom_purchase():
    result = calculate_actual_profit(
        delivered_items=[
            {"quantity": 5, "amountPurchase": 400},
            {"quantity": 3},
        ],
        quantity=10,
        amount_purchase_unit=100,
        amount_sales_unit=200,
        delivery_price=500,
        extra_expenses=[{"name": "fee", "amount": 200}],
    )
    assert result["totalDeliveredQuantity"] == 8
    assert result["actualAmountSalesTotal"] == 1600
    assert result["actualAmountPurchaseTotal"] == 700
    assert result["actualCompanyProfit"] == pytest.approx(1600 - 700 - 500 * 0.8 - 200 * 0.8)


def test_calculate_actual_profit_empty_delivery():
    result = calculate_actual_profit([], 10, 100, 200, 500, [])
    assert result["actualCompanyProfit"] == 0
    assert result["totalDeliveredQuantity"] == 0


def test_compute_deal_fields_includes_nds_percent():
    result = compute_deal_fields(
        quantity=1,
        amount_purchase_unit=0,
        amount_sales_unit=1220,
        amount_delivery=0,
        payment_method="безналичный расчет",
        add_expenses=[],
        delivered_quantity=[],
        manager_share=0.05,
        config=CONFIG,
    )
    assert result["ndsPercent"] == 0.22
    assert result["managerShare"] == 0.05


def test_compute_deal_fields_preserves_historical_nds():
    result = compute_deal_fields(
        quantity=1,
        amount_purchase_unit=0,
        amount_sales_unit=1180,
        amount_delivery=0,
        payment_method="безналичный расчет",
        add_expenses=[],
        delivered_quantity=[],
        manager_share=0.05,
        config=CalculatorConfig(nds_percent=0.22),
        stored_nds_percent=0.18,
    )
    assert result["ndsPercent"] == 0.18
