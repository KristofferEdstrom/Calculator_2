# engine.py
# -----------------------------
# Safe scientific calculator engine
# This replaces eval() completely
# -----------------------------

import ast
import operator
import math
import re


# -----------------------------
# Allowed math operators
# -----------------------------
operators = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


# -----------------------------
# Allowed math functions
# -----------------------------
functions = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "ln": math.log,
    "log10": math.log10,
    "abs": abs,
    "factorial": math.factorial    
}


# -----------------------------
# Constants (pi, e, etc.)
# -----------------------------
constants = {
    "pi": math.pi,
    "e": math.e,
}


# -----------------------------
# Main evaluation function
# -----------------------------
def format_result(value):
    """
    Formats output:
    - converts 3.0 → 3
    - keeps decimals when needed
    """

    if isinstance(value, float):
        if value.is_integer():
            return int(value)

    return value

def preprocess_expression(expr):
    """
    Converts user-friendly syntax into Python syntax.
    """

    # Replace ^ with **
    expr = expr.replace("^", "**")

    # Replace factorials: 5! -> factorial(5)
    expr = re.sub(r'(\d+)!', r'factorial(\1)', expr)

    return expr

def evaluate_expression(expr: str):
    """
    Safely evaluates a math expression using AST.
    No eval() used — fully controlled.
    """

    expr = preprocess_expression(expr)

    # Replace constants like pi, e
    for name, value in constants.items():
        expr = expr.replace(name, str(value))
    
    # Parse expression into AST
    node = ast.parse(expr, mode="eval")

    def eval_node(n):

        # Numbers (e.g. 5, 2.3)
        if isinstance(n, ast.Constant):
            return n.value

        # Binary operations (2 + 3, 4 * 5, etc.)
        elif isinstance(n, ast.BinOp):
            left = eval_node(n.left)
            right = eval_node(n.right)

            op_type = type(n.op)

            if op_type not in operators:
                raise ValueError("Unsupported operator")

            return operators[op_type](left, right)

        # Unary operations (-5)
        elif isinstance(n, ast.UnaryOp):
            return operators[type(n.op)](eval_node(n.operand))

        # Function calls (sqrt(9), sin(1))
        elif isinstance(n, ast.Call):

            func_name = n.func.id

            if func_name not in functions:
                raise ValueError(f"Function '{func_name}' not allowed")

            args = [eval_node(arg) for arg in n.args]

            return functions[func_name](*args)

        else:
            raise ValueError("Invalid expression")

    return eval_node(node.body)