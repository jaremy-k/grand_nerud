import ast
import operator
from typing import Any

from app.exceptions import ValidationError
from app.formula_engine.functions import DSL_FUNCTIONS

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

_BOOL_OPS = {
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
}


class FormulaEvaluationError(ValidationError):
    default_detail = "Ошибка вычисления формулы"


def evaluate_expression(expression: str, namespace: dict[str, Any]) -> Any:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValidationError(f"Синтаксическая ошибка: {exc.msg}") from exc
    return _eval_node(tree.body, namespace)


def _eval_node(node: ast.AST, namespace: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in namespace:
            return namespace[node.id]
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        raise ValidationError(f"Неизвестная переменная: {node.id}")

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, namespace)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand
        raise ValidationError("Недопустимый унарный оператор")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise ValidationError("Недопустимый бинарный оператор")
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.right, namespace)
        try:
            return _BIN_OPS[op_type](left, right)
        except ZeroDivisionError as exc:
            raise ValidationError("Деление на ноль") from exc

    if isinstance(node, ast.BoolOp):
        op_type = type(node.op)
        if op_type not in _BOOL_OPS:
            raise ValidationError("Недопустимый логический оператор")
        result = _eval_node(node.values[0], namespace)
        for value in node.values[1:]:
            result = _BOOL_OPS[op_type](result, _eval_node(value, namespace))
        return result

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, namespace)
        for op, comparator in zip(node.ops, node.comparators):
            op_type = type(op)
            if op_type not in _CMP_OPS:
                raise ValidationError("Недопустимое сравнение")
            right = _eval_node(comparator, namespace)
            if not _CMP_OPS[op_type](left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.IfExp):
        test = _eval_node(node.test, namespace)
        return _eval_node(node.body if test else node.orelse, namespace)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValidationError("Разрешены только простые вызовы функций")
        func_name = node.func.id
        if func_name not in DSL_FUNCTIONS:
            raise ValidationError(f"Неизвестная функция: {func_name}")
        args = [_eval_node(arg, namespace) for arg in node.args]
        if node.keywords:
            raise ValidationError("Именованные аргументы не поддерживаются")
        try:
            return DSL_FUNCTIONS[func_name](*args)
        except TypeError as exc:
            raise ValidationError(f"Ошибка вызова {func_name}: {exc}") from exc

    if isinstance(node, ast.List):
        return [_eval_node(elt, namespace) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, namespace) for elt in node.elts)

    raise ValidationError(f"Недопустимый элемент выражения: {type(node).__name__}")
