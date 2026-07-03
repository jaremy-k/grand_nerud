import pytest

from app.calculation_rules.defaults import DEFAULT_CALCULATION_FIELDS
from app.calculator_config.models import CalculatorConfig
from app.exceptions import ValidationError
from app.formula_engine.context import sample_context
from app.formula_engine.engine import FormulaEngine
from app.formula_engine.evaluator import evaluate_expression

CONFIG = CalculatorConfig()


def test_evaluate_simple_expression():
    ctx = sample_context(CONFIG)
    assert evaluate_expression("amountSalesUnit * quantity", ctx) == 2000


def test_evaluate_conditional_nds():
    ctx = sample_context(CONFIG)
    ctx["storedNdsPercent"] = 0.18
    result = evaluate_expression(
        "storedNdsPercent if storedNdsPercent is not None else ndsPercentConfig",
        ctx,
    )
    assert result == 0.18


def test_default_rules_validate():
    errors = FormulaEngine.validate_fields(DEFAULT_CALCULATION_FIELDS, CONFIG)
    assert errors == []


def test_default_rules_compute_company_profit():
    results = FormulaEngine.evaluate_fields(
        fields=DEFAULT_CALCULATION_FIELDS,
        deal_data={
            "quantity": 10,
            "amountPurchaseUnit": 100,
            "amountSalesUnit": 200,
            "amountDelivery": 500,
            "paymentMethod": CONFIG.non_cash_payment_method,
            "addExpenses": [{"name": "fee", "amount": 200}],
            "deliveredQuantity": [],
        },
        config=CONFIG,
        user_profit={"nonCash": {"alone": 0.1}},
        stored_nds_percent=None,
    )
    assert results["amountSalesTotal"] == 2000
    assert results["companyProfit"] == 300
    assert results["managerProfit"] == pytest.approx(30)
    assert results["ndsPercent"] == 0.22


def test_historical_nds_in_rules():
    results = FormulaEngine.evaluate_fields(
        fields=DEFAULT_CALCULATION_FIELDS,
        deal_data={
            "quantity": 1,
            "amountPurchaseUnit": 0,
            "amountSalesUnit": 1180,
            "amountDelivery": 0,
            "paymentMethod": CONFIG.non_cash_payment_method,
            "addExpenses": [],
            "deliveredQuantity": [],
        },
        config=CONFIG,
        user_profit=None,
        stored_nds_percent=0.18,
    )
    assert results["ndsPercent"] == 0.18


def test_unknown_variable_rejected():
    with pytest.raises(ValidationError):
        evaluate_expression("unknownVar + 1", {})
