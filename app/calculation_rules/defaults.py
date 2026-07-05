DEFAULT_RULE_NAME = "Стандартный расчёт сделки"

DEFAULT_RULE_INPUTS = {
    "deal": [
        "quantity",
        "amountPurchaseUnit",
        "amountSalesUnit",
        "amountDelivery",
        "paymentMethod",
        "addExpenses",
        "deliveredQuantity",
    ],
    "config": [
        "ndsPercentConfig",
        "defaultManagerShare",
        "cashPaymentMethod",
        "nonCashPaymentMethod",
    ],
    "user": ["managerShare"],
}

DEFAULT_RULE_SCHEMA = {
    "inputs": DEFAULT_RULE_INPUTS,
    "formulas": {
        "ndsPercent": {
            "expr": "ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0",
            "snapshot": True,
        },
        "amountSalesTotal": {
            "expr": "amountSalesUnit * quantity",
        },
        "amountPurchaseTotal": {
            "expr": "amountPurchaseUnit * quantity",
        },
        "ndsAmount": {
            "expr": "(amountSalesTotal / (1 + ndsPercent)) * ndsPercent if ndsPercent else 0",
        },
        "companyProfit": {
            "expr": "amountSalesTotal - amountPurchaseTotal - amountDelivery - sumExpenses(addExpenses)",
        },
        "managerProfit": {
            "expr": "companyProfit * managerShare",
        },
        "totalAmount": {
            "expr": "amountSalesTotal",
        },
        "totalDeliveredQuantity": {
            "expr": "sumDeliveredQuantity(deliveredQuantity)",
        },
        "actualAmountSalesTotal": {
            "expr": "amountSalesUnit * totalDeliveredQuantity if totalDeliveredQuantity > 0 else 0",
        },
        "actualAmountPurchaseTotal": {
            "expr": "sumDeliveredPurchase(deliveredQuantity, amountPurchaseUnit)",
        },
        "actualCompanyProfit": {
            "expr": (
                "actualAmountSalesTotal - actualAmountPurchaseTotal "
                "- amountDelivery * deliveryShare(totalDeliveredQuantity, quantity) "
                "- sumExpenses(addExpenses) * deliveryShare(totalDeliveredQuantity, quantity) "
                "if totalDeliveredQuantity > 0 and quantity > 0 else 0"
            ),
        },
    },
    "metadata": {
        "ndsPercent": {
            "label": "Ставка НДС",
            "description": "Сохраняется в сделке; для старых сделок используется записанное значение",
        },
        "amountSalesTotal": {"label": "Сумма от клиента"},
        "amountPurchaseTotal": {"label": "Сумма закупки"},
        "ndsAmount": {"label": "Сумма НДС"},
        "companyProfit": {"label": "Маржа"},
        "managerProfit": {"label": "Доход менеджера"},
        "totalAmount": {"label": "Итоговая сумма"},
        "totalDeliveredQuantity": {"label": "Доставлено (объём)"},
        "actualAmountSalesTotal": {"label": "Факт. сумма от клиента"},
        "actualAmountPurchaseTotal": {"label": "Факт. сумма закупки"},
        "actualCompanyProfit": {"label": "Фактическая прибыль"},
    },
}
