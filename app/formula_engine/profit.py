from app.calculator_config.models import CalculatorConfig

DEFAULT_CONFIG = CalculatorConfig()


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
