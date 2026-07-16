# calculator_v3.py

import ast
import operator
import json
from colorama import init, Fore

init(autoreset=True)

HISTORY_FILE = "history.json"

memory = 0


# =========================
# SAFE OPERATORS
# =========================

operators = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


# =========================
# SAFE EVALUATOR
# =========================

def evaluate_expression(expression):
    """
    Safely evaluate math expressions using AST.
    """

    def eval_node(node):

        if isinstance(node, ast.Constant):
            return node.value

        elif isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)

            op_type = type(node.op)

            if op_type not in operators:
                raise TypeError("Unsupported operator")

            return operators[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            operand = eval_node(node.operand)

            op_type = type(node.op)

            if op_type not in operators:
                raise TypeError("Unsupported unary operator")

            return operators[op_type](operand)

        else:
            raise TypeError("Unsupported expression")

    parsed = ast.parse(expression, mode='eval')

    return eval_node(parsed.body)


# =========================
# HISTORY SYSTEM
# =========================

def load_history():
    try:
        with open(HISTORY_FILE, "r") as file:
            return json.load(file)

    except FileNotFoundError:
        return []


def save_history(history):
    with open(HISTORY_FILE, "w") as file:
        json.dump(history, file, indent=4)


history = load_history()


# =========================
# UI
# =========================

def show_help():
    print(Fore.CYAN + """
=== COMMANDS ===

Type any math expression:
    2 + 2
    5 * 10
    2 ** 8

Commands:
    help        Show commands
    history     Show history
    memory      Show memory value
    mc          Clear memory
    exit        Quit calculator

Memory:
    m+ NUMBER   Add to memory
    m- NUMBER   Subtract from memory
""")


# =========================
# MAIN LOOP
# =========================

print(Fore.GREEN + "=== ADVANCED CLI CALCULATOR V3 ===")
print(Fore.YELLOW + "Type 'help' for commands.\n")


while True:

    user_input = input(Fore.WHITE + ">>> ").strip()

    if not user_input:
        continue

    # EXIT
    if user_input.lower() == "exit":
        print(Fore.GREEN + "Goodbye!")
        break

    # HELP
    elif user_input.lower() == "help":
        show_help()
        continue

    # HISTORY
    elif user_input.lower() == "history":

        print(Fore.MAGENTA + "\n=== HISTORY ===")

        if not history:
            print("No history found.")

        for item in history:
            print(item)

        continue

    # MEMORY VIEW
    elif user_input.lower() == "memory":
        print(Fore.CYAN + f"Memory = {memory}")
        continue

    # MEMORY CLEAR
    elif user_input.lower() == "mc":
        memory = 0
        print(Fore.CYAN + "Memory cleared.")
        continue

    # MEMORY ADD
    elif user_input.lower().startswith("m+"):
        try:
            value = float(user_input[2:].strip())
            memory += value

            print(Fore.CYAN + f"Memory = {memory}")

        except ValueError:
            print(Fore.RED + "Invalid memory value.")

        continue

    # MEMORY SUBTRACT
    elif user_input.lower().startswith("m-"):
        try:
            value = float(user_input[2:].strip())
            memory -= value

            print(Fore.CYAN + f"Memory = {memory}")

        except ValueError:
            print(Fore.RED + "Invalid memory value.")

        continue

    # EXPRESSION EVALUATION
    try:

        result = evaluate_expression(user_input)

        output = f"{user_input} = {result}"

        history.append(output)

        save_history(history)

        print(Fore.GREEN + output)

    except ZeroDivisionError:
        print(Fore.RED + "Error: Division by zero.")

    except Exception as e:
        print(Fore.RED + f"Error: {e}")