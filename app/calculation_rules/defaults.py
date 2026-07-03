DEFAULT_CALCULATION_FIELDS = [
    {
        "name": "ndsPercent",
        "label": "Ставка НДС",
        "description": "Сохраняется в сделке; для старых сделок используется записанное значение",
        "expression": (
            "storedNdsPercent if storedNdsPercent is not None "
            "else (ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0)"
        ),
        "store": True,
    },
    {
        "name": "amountSalesTotal",
        "label": "Сумма от клиента",
        "expression": "amountSalesUnit * quantity",
        "store": True,
    },
    {
        "name": "amountPurchaseTotal",
        "label": "Сумма закупки",
        "expression": "amountPurchaseUnit * quantity",
        "store": True,
    },
    {
        "name": "ndsAmount",
        "label": "Сумма НДС",
        "expression": "(amountSalesTotal / (1 + ndsPercent)) * ndsPercent if ndsPercent else 0",
        "store": True,
    },
    {
        "name": "companyProfit",
        "label": "Маржа",
        "expression": "amountSalesTotal - amountPurchaseTotal - amountDelivery - sumExpenses(addExpenses)",
        "store": True,
    },
    {
        "name": "managerProfit",
        "label": "Доход менеджера",
        "expression": "companyProfit * managerShare",
        "store": True,
    },
    {
        "name": "totalAmount",
        "label": "Итоговая сумма",
        "expression": "amountSalesTotal",
        "store": True,
    },
    {
        "name": "totalDeliveredQuantity",
        "label": "Доставлено (объём)",
        "expression": "sumDeliveredQuantity(deliveredQuantity)",
        "store": False,
    },
    {
        "name": "actualAmountSalesTotal",
        "label": "Факт. сумма от клиента",
        "expression": "amountSalesUnit * totalDeliveredQuantity if totalDeliveredQuantity > 0 else 0",
        "store": False,
    },
    {
        "name": "actualAmountPurchaseTotal",
        "label": "Факт. сумма закупки",
        "expression": "sumDeliveredPurchase(deliveredQuantity, amountPurchaseUnit)",
        "store": False,
    },
    {
        "name": "actualCompanyProfit",
        "label": "Фактическая прибыль",
        "expression": (
            "actualAmountSalesTotal - actualAmountPurchaseTotal "
            "- amountDelivery * deliveryShare(totalDeliveredQuantity, quantity) "
            "- sumExpenses(addExpenses) * deliveryShare(totalDeliveredQuantity, quantity) "
            "if totalDeliveredQuantity > 0 and quantity > 0 else 0"
        ),
        "store": False,
    },
]

DEFAULT_RULE_NAME = "Стандартный расчёт сделки"
