from dataclasses import dataclass


@dataclass(frozen=True)
class CalculatorConfig:
    nds_percent: float = 0.22
    default_manager_share: float = 0.05
    cash_payment_method: str = "наличный расчет"
    non_cash_payment_method: str = "безналичный расчет"

    @classmethod
    def from_document(cls, doc: dict | None) -> "CalculatorConfig":
        if not doc:
            return cls()
        return cls(
            nds_percent=float(doc.get("ndsPercent", 0.22)),
            default_manager_share=float(doc.get("defaultManagerShare", 0.05)),
            cash_payment_method=str(doc.get("cashPaymentMethod", "наличный расчет")),
            non_cash_payment_method=str(doc.get("nonCashPaymentMethod", "безналичный расчет")),
        )
