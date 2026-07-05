import ast
from dataclasses import dataclass, field
from typing import Any

from app.exceptions import ValidationError
from app.formula_engine.evaluator import evaluate_expression

_BUILTIN_NAMES = frozenset({"True", "False", "None"})


@dataclass(frozen=True)
class CompiledFormula:
    name: str
    expression: str
    snapshot: bool = False
    label: str | None = None
    description: str | None = None
    group: str | None = None


@dataclass
class CompiledRule:
    inputs: dict[str, list[str]]
    formulas: list[CompiledFormula] = field(default_factory=list)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def input_names(self) -> set[str]:
        names: set[str] = set()
        for values in self.inputs.values():
            names.update(values)
        return names

    @property
    def snapshot_names(self) -> set[str]:
        return {formula.name for formula in self.formulas if formula.snapshot}

    def formula_by_name(self) -> dict[str, CompiledFormula]:
        return {formula.name: formula for formula in self.formulas}


def extract_dependencies(expression: str) -> set[str]:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValidationError(f"Синтаксическая ошибка: {exc.msg}") from exc

    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _BUILTIN_NAMES:
            deps.add(node.id)
    return deps


def legacy_fields_to_schema(fields: list[dict]) -> dict[str, Any]:
    formulas: dict[str, dict[str, Any]] = {}
    metadata: dict[str, dict[str, Any]] = {}

    for item in fields:
        name = item["name"]
        expression = item["expression"]
        if "storedNdsPercent" in expression:
            expression = (
                "ndsPercentConfig if paymentMethod == nonCashPaymentMethod else 0"
            )
        formulas[name] = {
            "expr": expression,
            "snapshot": bool(item.get("store", True) and name == "ndsPercent"),
        }
        meta: dict[str, Any] = {}
        if item.get("label"):
            meta["label"] = item["label"]
        if item.get("description"):
            meta["description"] = item["description"]
        if meta:
            metadata[name] = meta

    from app.calculation_rules.defaults import DEFAULT_RULE_INPUTS

    return {
        "inputs": dict(DEFAULT_RULE_INPUTS),
        "formulas": formulas,
        "metadata": metadata,
    }


def compile_schema(schema: dict[str, Any]) -> CompiledRule:
    inputs = schema.get("inputs") or {}
    raw_formulas = schema.get("formulas") or {}
    metadata = schema.get("metadata") or {}

    if not raw_formulas:
        raise ValidationError("Не указаны формулы")

    formulas_map: dict[str, CompiledFormula] = {}
    for name, definition in raw_formulas.items():
        if isinstance(definition, str):
            expr = definition
            snapshot = False
        else:
            expr = definition.get("expr") or definition.get("expression", "")
            snapshot = bool(definition.get("snapshot", False))
        if not expr:
            raise ValidationError(f"Пустая формула: {name}")

        meta = metadata.get(name, {})
        formulas_map[name] = CompiledFormula(
            name=name,
            expression=expr,
            snapshot=snapshot,
            label=meta.get("label"),
            description=meta.get("description"),
            group=meta.get("group"),
        )

    sorted_formulas = _topological_sort(formulas_map)
    return CompiledRule(inputs=inputs, formulas=sorted_formulas, metadata=metadata)


def normalize_rule_document(doc: dict[str, Any]) -> CompiledRule:
    if doc.get("schema"):
        return compile_schema(doc["schema"])
    if doc.get("fields"):
        return compile_schema(legacy_fields_to_schema(doc["fields"]))
    raise ValidationError("Набор правил не содержит schema или fields")


def _topological_sort(formulas: dict[str, CompiledFormula]) -> list[CompiledFormula]:
    deps_map = {name: extract_dependencies(formula.expression) for name, formula in formulas.items()}
    in_degree = {name: 0 for name in formulas}
    dependents: dict[str, list[str]] = {name: [] for name in formulas}

    for name, deps in deps_map.items():
        for dep in deps:
            if dep in formulas:
                in_degree[name] += 1
                dependents[dep].append(name)

    queue = [name for name, degree in in_degree.items() if degree == 0]
    order: list[str] = []

    while queue:
        queue.sort()
        current = queue.pop(0)
        order.append(current)
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(formulas):
        raise ValidationError("Циклическая зависимость между формулами")

    return [formulas[name] for name in order]


def validate_rule(
        compiled: CompiledRule,
        config,
        sample_ctx: dict[str, Any] | None = None,
) -> list[str]:
    from app.formula_engine.context import sample_context
    from app.formula_engine.functions import DSL_FUNCTIONS

    errors: list[str] = []
    allowed_inputs = compiled.input_names
    allowed_functions = set(DSL_FUNCTIONS.keys())
    defined: set[str] = set()
    ctx = dict(sample_ctx or sample_context(config))

    for index, formula in enumerate(compiled.formulas, start=1):
        prefix = f"Формула #{index} ({formula.name})"
        deps = extract_dependencies(formula.expression)
        unknown = deps - allowed_inputs - defined - _BUILTIN_NAMES - allowed_functions
        if unknown:
            errors.append(f"{prefix}: неизвестные переменные: {', '.join(sorted(unknown))}")
            continue

        try:
            value = evaluate_expression(formula.expression, dict(ctx))
            if isinstance(value, (int, float)):
                value = float(value)
            ctx[formula.name] = value
            defined.add(formula.name)
        except ValidationError as exc:
            errors.append(f"{prefix}: {exc.detail}")

    return errors
