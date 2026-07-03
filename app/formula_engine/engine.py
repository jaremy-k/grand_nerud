from typing import Any

from app.exceptions import ValidationError
from app.formula_engine.context import build_evaluation_context, sample_context
from app.formula_engine.evaluator import evaluate_expression
from app.formula_engine.functions import DSL_FUNCTION_DOCS, DSL_VARIABLE_DOCS


class FormulaEngine:
    @staticmethod
    def evaluate_fields(
            fields: list[dict],
            deal_data: dict,
            config,
            user_profit: dict | None = None,
            stored_nds_percent: float | None = None,
    ) -> dict[str, Any]:
        ctx = build_evaluation_context(
            deal_data=deal_data,
            config=config,
            user_profit=user_profit,
            stored_nds_percent=stored_nds_percent,
        )
        results: dict[str, Any] = {}
        for field in fields:
            name = field["name"]
            expression = field["expression"]
            value = evaluate_expression(expression, ctx)
            if isinstance(value, (int, float)):
                value = float(value)
            ctx[name] = value
            results[name] = value
        return results

    @staticmethod
    def stored_field_names(fields: list[dict]) -> set[str]:
        return {field["name"] for field in fields if field.get("store", True)}

    @staticmethod
    def preview_field_names(fields: list[dict]) -> set[str]:
        return {field["name"] for field in fields if not field.get("store", True)}

    @staticmethod
    def validate_fields(fields: list[dict], config) -> list[str]:
        errors: list[str] = []
        names: set[str] = set()
        ctx = sample_context(config)

        for index, field in enumerate(fields):
            name = field.get("name", "").strip()
            expression = field.get("expression", "").strip()
            prefix = f"Поле #{index + 1}"

            if not name:
                errors.append(f"{prefix}: не указано имя")
                continue
            if name in names:
                errors.append(f"{prefix} ({name}): дублирующееся имя")
            names.add(name)

            if not expression:
                errors.append(f"{prefix} ({name}): пустая формула")
                continue

            try:
                value = evaluate_expression(expression, dict(ctx))
                if isinstance(value, (int, float)):
                    value = float(value)
                ctx[name] = value
            except ValidationError as exc:
                errors.append(f"{prefix} ({name}): {exc.detail}")

        return errors

    @staticmethod
    def get_dsl_docs() -> dict:
        return {
            "variables": DSL_VARIABLE_DOCS,
            "functions": DSL_FUNCTION_DOCS,
            "syntax": [
                "Python-подобные выражения: +, -, *, /, **, сравнения, and/or/not",
                "Условие: value_if_true if condition else value_if_false",
                "Пример: amountSalesUnit * quantity",
                "Пример НДС: storedNdsPercent if storedNdsPercent is not None else (ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0)",
            ],
        }
