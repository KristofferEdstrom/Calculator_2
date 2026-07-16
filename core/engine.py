"""
engine.py

Safely parses and evaluates mathematical expressions.
"""

import ast
import math
import operator
import re
from collections.abc import Callable
from typing import TypeAlias


Number: TypeAlias = int | float
MathFunction: TypeAlias = Callable[..., Number]


# --------------------------------------------------
# ALLOWED OPERATORS
# --------------------------------------------------

operators: dict[type[ast.operator] | type[ast.unaryop], Callable] = {
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

functions: dict[str, MathFunction] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "sqrt": math.sqrt,
    "ln": math.log,
    "log": math.log10,
    "log10": math.log10,
    "abs": abs,
    "factorial": math.factorial,
    "floor": math.floor,
    "ceil": math.ceil,
    "exp": math.exp,
}


# --------------------------------------------------
# ALLOWED CONSTANTS
# --------------------------------------------------

constants: dict[str, Number] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}


# --------------------------------------------------
# EXPRESSION PREPROCESSING
# --------------------------------------------------

def preprocess_expression(expression: str) -> str:
    """
    Convert calculator-style syntax into syntax understood by the AST parser.

    Examples:
        2^3   -> 2**3
        5!    -> factorial(5)
        pi    -> resolved later as a named constant
    """
    expression = expression.strip()

    # Allow calculator-style powers.
    expression = expression.replace("^", "**")

    # Convert simple numeric factorials:
    # 5! -> factorial(5)
    expression = re.sub(
        r"(?<![\w)])(\d+(?:\.\d+)?)!",
        r"factorial(\1)",
        expression,
    )

    # Convert factorials applied to names or closing parentheses:
    # factorial(5)! -> factorial(factorial(5))
    # This loop handles nested occurrences conservatively.
    factorial_pattern = re.compile(
        r"(\([^()]+\)|[A-Za-z_]\w*|\d+(?:\.\d+)?)!"
    )

    while factorial_pattern.search(expression):
        expression = factorial_pattern.sub(
            r"factorial(\1)",
            expression,
        )

    return expression


# --------------------------------------------------
# AST EVALUATOR
# --------------------------------------------------

def evaluate_expression(expression: str) -> Number:
    """
    Safely evaluate a mathematical expression.

    Only explicitly allowed numbers, operators, functions, and constants
    can be evaluated.
    """
    if not isinstance(expression, str):
        raise TypeError("Expression must be a string.")

    processed_expression = preprocess_expression(expression)

    if not processed_expression:
        raise ValueError("Expression cannot be empty.")

    parsed = ast.parse(processed_expression, mode="eval")

    result = _evaluate_node(parsed.body)

    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise TypeError("Expression did not produce a numeric result.")

    return result


def _evaluate_node(node: ast.AST) -> Number:
    """Recursively evaluate one permitted AST node."""

    # Numeric literal, such as 5 or 3.14.
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise TypeError("Boolean values are not supported.")

        if isinstance(node.value, (int, float)):
            return node.value

        raise TypeError("Only numeric constants are supported.")

    # Named constants, such as pi or e.
    if isinstance(node, ast.Name):
        if node.id in constants:
            return constants[node.id]

        raise ValueError(f"Unknown constant: {node.id}")

    # Binary expressions, such as 2 + 3 or 4 ** 2.
    if isinstance(node, ast.BinOp):
        operation = operators.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported binary operator.")

        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)

        return operation(left, right)

    # Unary expressions, such as -5 or +3.
    if isinstance(node, ast.UnaryOp):
        operation = operators.get(type(node.op))

        if operation is None:
            raise ValueError("Unsupported unary operator.")

        operand = _evaluate_node(node.operand)

        return operation(operand)

    # Approved function calls, such as sqrt(25).
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct function calls are supported.")

        function_name = node.func.id

        if function_name not in functions:
            raise ValueError(f"Unsupported function: {function_name}")

        if node.keywords:
            raise ValueError("Keyword arguments are not supported.")

        arguments = [_evaluate_node(argument) for argument in node.args]

        return functions[function_name](*arguments)

    raise ValueError(
        f"Unsupported expression element: {type(node).__name__}"
    )


# --------------------------------------------------
# RESULT FORMATTING
# --------------------------------------------------

def format_result(value: Number) -> Number:
    """
    Format a numeric result for display.

    Examples:
        3.0 -> 3
        3.5 -> 3.5
        1.2246467991473532e-16 -> 0
    """
    if isinstance(value, bool):
        return int(value)

    if not isinstance(value, (int, float)):
        raise TypeError("Result must be numeric.")

    if isinstance(value, float):
        # Remove tiny floating-point artifacts, such as sin(pi).
        if math.isclose(value, 0.0, abs_tol=1e-12):
            return 0

        # Display whole-valued floats as integers.
        if value.is_integer():
            return int(value)

        # Avoid excessively long floating-point output.
        return float(f"{value:.12g}")

    return value