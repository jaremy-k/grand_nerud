import pytest

from app.calculation_rules.defaults import DEFAULT_RULE_SCHEMA
from app.calculator_config.models import CalculatorConfig
from app.exceptions import ValidationError
from app.formula_engine.compiler import compile_schema, extract_dependencies
from app.formula_engine.context import sample_context
from app.formula_engine.engine import FormulaEngine
from app.formula_engine.evaluator import evaluate_expression

CONFIG = CalculatorConfig()


def test_evaluate_simple_expression():
    ctx = sample_context(CONFIG)
    assert evaluate_expression("amountSalesUnit * quantity", ctx) == 2000


def test_evaluate_conditional_nds():
    ctx = sample_context(CONFIG)
    result = evaluate_expression(
        "ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0",
        ctx,
    )
    assert result == 0.22


def test_default_rules_validate():
    errors = FormulaEngine.validate_schema(DEFAULT_RULE_SCHEMA, CONFIG)
    assert errors == []


def test_default_rules_compute_company_profit():
    compiled = compile_schema(DEFAULT_RULE_SCHEMA)
    results = FormulaEngine.evaluate_rule(
        compiled=compiled,
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
    )
    assert results["amountSalesTotal"] == 2000
    assert results["companyProfit"] == 300
    assert results["managerProfit"] == pytest.approx(30)
    assert results["ndsPercent"] == 0.22


def test_snapshot_nds_preserved_from_deal():
    compiled = compile_schema(DEFAULT_RULE_SCHEMA)
    results = FormulaEngine.evaluate_rule(
        compiled=compiled,
        deal_data={
            "quantity": 1,
            "amountPurchaseUnit": 0,
            "amountSalesUnit": 1180,
            "amountDelivery": 0,
            "paymentMethod": CONFIG.non_cash_payment_method,
            "addExpenses": [],
            "deliveredQuantity": [],
            "ndsPercent": 0.18,
        },
        config=CONFIG,
        user_profit=None,
    )
    assert results["ndsPercent"] == 0.18


def test_topological_sort_allows_any_formula_order():
    reordered = {
        **DEFAULT_RULE_SCHEMA,
        "formulas": dict(reversed(list(DEFAULT_RULE_SCHEMA["formulas"].items()))),
    }
    errors = FormulaEngine.validate_schema(reordered, CONFIG)
    assert errors == []


def test_cyclic_dependency_rejected():
    schema = {
        "inputs": DEFAULT_RULE_SCHEMA["inputs"],
        "formulas": {
            "a": {"expr": "b + 1"},
            "b": {"expr": "a + 1"},
        },
        "metadata": {},
    }
    with pytest.raises(ValidationError):
        compile_schema(schema)


def test_unknown_variable_rejected():
    with pytest.raises(ValidationError):
        evaluate_expression("unknownVar + 1", {})


def test_extract_dependencies():
    deps = extract_dependencies("amountSalesTotal - amountPurchaseTotal")
    assert deps == {"amountSalesTotal", "amountPurchaseTotal"}
