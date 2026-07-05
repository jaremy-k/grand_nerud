from app.calculator_config.models import CalculatorConfig
from app.formula_engine.profit import get_manager_share

CONFIG = CalculatorConfig()


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
