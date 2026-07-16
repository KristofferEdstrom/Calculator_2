"""
graphs/evaluator.py

Safely evaluates mathematical expressions containing the variable x.

This module is used by the graphing system to calculate many y-values
for a sequence of x-values.

Examples:
    sin(x)
    x^2
    x^3 - 2*x + 1
    sqrt(abs(x))
"""

import ast
import math
import operator
from collections.abc import Callable
from typing import TypeAlias


# A graph calculation can return an integer or floating-point number.
Number: TypeAlias = int | float


# --------------------------------------------------
# ALLOWED OPERATORS
# --------------------------------------------------

# Only operators listed here can be used in graph expressions.
OPERATORS: dict[type[ast.operator] | type[ast.unaryop], Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


# --------------------------------------------------
# ALLOWED FUNCTIONS
# --------------------------------------------------

# Only these functions may be called from graph expressions.
FUNCTIONS: dict[str, Callable[..., Number]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "sqrt": math.sqrt,
    "abs": abs,
    "ln": math.log,
    "log": math.log10,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
}


# --------------------------------------------------
# ALLOWED CONSTANTS
# --------------------------------------------------

CONSTANTS: dict[str, Number] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}


# --------------------------------------------------
# EXPRESSION PREPARATION
# --------------------------------------------------

def preprocess_expression(expression: str) -> str:
    """
    Convert calculator-style syntax into Python-compatible syntax.

    Examples:
        x^2  -> x**2
        2π   is not supported yet; use 2*pi
    """
    return expression.strip().replace("^", "**")


# --------------------------------------------------
# PUBLIC EVALUATOR
# --------------------------------------------------

def evaluate_graph_expression(expression: str, x_value: Number) -> float:
    """
    Evaluate a mathematical expression for one value of x.

    Args:
        expression:
            Mathematical expression such as "sin(x)" or "x^2".

        x_value:
            Numeric value to substitute for x.

    Returns:
        The calculated result as a float.

    Raises:
        SyntaxError:
            If the expression has invalid syntax.

        ValueError:
            If the expression contains unsupported names or operations.

        ZeroDivisionError:
            If the expression divides by zero.

        TypeError:
            If an unsupported value type is encountered.
    """
    if not isinstance(expression, str):
        raise TypeError("Expression must be a string.")

    if isinstance(x_value, bool) or not isinstance(x_value, (int, float)):
        raise TypeError("x must be an integer or float.")

    processed_expression = preprocess_expression(expression)

    if not processed_expression:
        raise ValueError("Expression cannot be empty.")

    parsed_expression = ast.parse(processed_expression, mode="eval")

    result = _evaluate_node(parsed_expression.body, float(x_value))

    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise TypeError("Expression did not return a numeric value.")

    return float(result)


# --------------------------------------------------
# AST NODE EVALUATION
# --------------------------------------------------

def _evaluate_node(node: ast.AST, x_value: float) -> Number:
    """
    Recursively evaluate one approved AST node.
    """

    # Numeric literal, such as 5 or 3.14.
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise TypeError("Boolean values are not supported.")

        if isinstance(node.value, (int, float)):
            return node.value

        raise TypeError("Only numeric constants are supported.")

    # Variable or named mathematical constant.
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x_value

        if node.id in CONSTANTS:
            return CONSTANTS[node.id]

        raise ValueError(f"Unknown name: {node.id}")

    # Binary operation, such as x + 2 or x ** 2.
    if isinstance(node, ast.BinOp):
        operation = OPERATORS.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported binary operator.")

        left_value = _evaluate_node(node.left, x_value)
        right_value = _evaluate_node(node.right, x_value)

        return operation(left_value, right_value)

    # Unary operation, such as -x.
    if isinstance(node, ast.UnaryOp):
        operation = OPERATORS.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported unary operator.")

        operand = _evaluate_node(node.operand, x_value)

        return operation(operand)

    # Approved function call, such as sin(x).
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct function calls are supported.")

        function_name = node.func.id

        if function_name not in FUNCTIONS:
            raise ValueError(f"Unsupported function: {function_name}")

        if node.keywords:
            raise ValueError("Keyword arguments are not supported.")

        arguments = [
            _evaluate_node(argument, x_value)
            for argument in node.args
        ]

        return FUNCTIONS[function_name](*arguments)

    raise ValueError(
        f"Unsupported expression element: {type(node).__name__}"
    )