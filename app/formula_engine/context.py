from typing import Any

from app.calculator_config.models import CalculatorConfig
from app.formula_engine.profit import get_manager_share


def build_evaluation_context(
        deal_data: dict,
        config: CalculatorConfig,
        user_profit: dict | None = None,
        extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payment_method = deal_data.get("paymentMethod")
    manager_share = get_manager_share(user_profit, payment_method, config)

    ctx: dict[str, Any] = {
        "quantity": float(deal_data.get("quantity") or 0),
        "amountPurchaseUnit": float(deal_data.get("amountPurchaseUnit") or 0),
        "amountSalesUnit": float(deal_data.get("amountSalesUnit") or 0),
        "amountDelivery": float(deal_data.get("amountDelivery") or 0),
        "paymentMethod": payment_method or "",
        "managerShare": manager_share,
        "ndsPercentConfig": config.nds_percent,
        "defaultManagerShare": config.default_manager_share,
        "cashPaymentMethod": config.cash_payment_method,
        "nonCashPaymentMethod": config.non_cash_payment_method,
        "addExpenses": deal_data.get("addExpenses") or [],
        "deliveredQuantity": deal_data.get("deliveredQuantity") or [],
    }
    if extra:
        ctx.update(extra)
    return ctx


def sample_context(config: CalculatorConfig | None = None) -> dict[str, Any]:
    cfg = config or CalculatorConfig()
    return build_evaluation_context(
        deal_data={
            "quantity": 10,
            "amountPurchaseUnit": 100,
            "amountSalesUnit": 200,
            "amountDelivery": 500,
            "paymentMethod": cfg.non_cash_payment_method,
            "addExpenses": [{"name": "fee", "amount": 200}],
            "deliveredQuantity": [
                {"quantity": 5, "amountPurchase": 400},
                {"quantity": 3},
            ],
        },
        config=cfg,
        user_profit={"nonCash": {"alone": 0.1}},
    )
