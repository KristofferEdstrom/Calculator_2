# gui.py
# -----------------------------
# Scientific Calculator GUI
# Uses engine.py (safe evaluator)
# -----------------------------

import tkinter as tk
from engine import evaluate_expression
import math


# -----------------------------
# WINDOW SETUP
# -----------------------------
root = tk.Tk()
root.title("Scientific Calculator")
root.geometry("420x600")


# -----------------------------
# DISPLAY
# -----------------------------
display = tk.Entry(root, font=("Arial", 22), borderwidth=5, relief="ridge")
display.pack(fill="both", padx=10, pady=10)


# -----------------------------
# INPUT FUNCTIONS
# -----------------------------
def press(value):
    """
    Inserts a button value into the display.
    """
    display.insert(tk.END, value)


def clear():
    """
    Clears the display.
    """
    display.delete(0, tk.END)


def calculate():
    """
    Sends expression to engine and shows result.
    """
    expr = display.get()

    try:
        result = evaluate_expression(expr)
    except Exception:
        result = "Error"

    display.delete(0, tk.END)
    display.insert(0, str(result))


# -----------------------------
# SCIENTIFIC FUNCTIONS
# -----------------------------
def insert_func(func_name):
    """
    Inserts function like sin(, cos(, sqrt(
    """
    display.insert(tk.END, func_name + "(")


def insert_constant(value):
    """
    Inserts constants like pi or e
    """
    display.insert(tk.END, str(value))


# -----------------------------
# BUTTON LAYOUT
# -----------------------------
buttons = [
    "7", "8", "9", "/", "sin",
    "4", "5", "6", "*", "cos",
    "1", "2", "3", "-", "tan",
    "0", ".", "(", ")", "sqrt",
]


frame = tk.Frame(root)
frame.pack()


# -----------------------------
# CREATE BUTTONS
# -----------------------------
row = 0
col = 0

for b in buttons:

    if b in ["sin", "cos", "tan", "sqrt"]:

        tk.Button(
            frame,
            text=b,
            width=6,
            height=2,
            command=lambda v=b: insert_func(v)
        ).grid(row=row, column=col)

    else:

        tk.Button(
            frame,
            text=b,
            width=6,
            height=2,
            command=lambda v=b: press(v)
        ).grid(row=row, column=col)

    col += 1

    if col > 4:
        col = 0
        row += 1


# -----------------------------
# CONSTANT BUTTONS
# -----------------------------
const_frame = tk.Frame(root)
const_frame.pack(pady=10)


tk.Button(const_frame, text="π", width=10,
          command=lambda: insert_constant(math.pi)).grid(row=0, column=0)

tk.Button(const_frame, text="e", width=10,
          command=lambda: insert_constant(math.e)).grid(row=0, column=1)

tk.Button(const_frame, text="x²", width=10,
          command=lambda: press("**2")).grid(row=0, column=2)


# -----------------------------
# CONTROL BUTTONS
# -----------------------------
tk.Button(root, text="C", height=2, command=clear).pack(fill="both")
tk.Button(root, text="=", height=2, command=calculate).pack(fill="both")


# -----------------------------
# START APP
# -----------------------------
root.mainloop()