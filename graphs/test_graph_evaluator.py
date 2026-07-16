from evaluator import evaluate_graph_expression


expressions = [
    ("x^2", 3),
    ("sin(x)", 0),
    ("x^3 - 2*x + 1", 2),
    ("sqrt(abs(x))", -9),
    ("pi * x", 2),
]

for expression, x_value in expressions:
    result = evaluate_graph_expression(expression, x_value)

    print(
        f"{expression}, x={x_value} -> {result}"
    )