from typing import Any

from app.formula_engine.compiler import CompiledRule, compile_schema, normalize_rule_document, validate_rule
from app.formula_engine.context import build_evaluation_context, sample_context
from app.formula_engine.evaluator import evaluate_expression
from app.formula_engine.functions import DSL_FUNCTION_DOCS, DSL_VARIABLE_DOCS


class FormulaEngine:
    @staticmethod
    def compile(rule_doc_or_schema: dict) -> CompiledRule:
        if rule_doc_or_schema.get("formulas") or rule_doc_or_schema.get("inputs"):
            return compile_schema(rule_doc_or_schema)
        return normalize_rule_document(rule_doc_or_schema)

    @staticmethod
    def evaluate_rule(
            compiled: CompiledRule,
            deal_data: dict,
            config,
            user_profit: dict | None = None,
    ) -> dict[str, Any]:
        ctx = build_evaluation_context(
            deal_data=deal_data,
            config=config,
            user_profit=user_profit,
        )
        results: dict[str, Any] = {}

        for formula in compiled.formulas:
            name = formula.name
            if formula.snapshot and deal_data.get(name) is not None:
                value = deal_data[name]
                if isinstance(value, (int, float)):
                    value = float(value)
                ctx[name] = value
                results[name] = value
                continue

            value = evaluate_expression(formula.expression, ctx)
            if isinstance(value, (int, float)):
                value = float(value)
            ctx[name] = value
            results[name] = value

        return results

    @staticmethod
    def snapshot_field_names(compiled: CompiledRule) -> set[str]:
        return compiled.snapshot_names

    @staticmethod
    def validate_schema(schema: dict, config) -> list[str]:
        compiled = compile_schema(schema)
        return validate_rule(compiled, config)

    @staticmethod
    def get_dsl_docs() -> dict:
        return {
            "variables": DSL_VARIABLE_DOCS,
            "functions": DSL_FUNCTION_DOCS,
            "syntax": [
                "Python-подобные выражения: +, -, *, /, **, сравнения, and/or/not",
                "Условие: value_if_true if condition else value_if_false",
                "Пример: amountSalesUnit * quantity",
                "Пример НДС: ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0",
                "Поля с snapshot: true сохраняются в сделке и не пересчитываются",
            ],
        }
