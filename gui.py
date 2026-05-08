# gui.py
# -----------------------------
# Scientific Calculator GUI
# Now with HISTORY PANEL
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
root.geometry("650x600")


# -----------------------------
# DISPLAY (main input)
# -----------------------------
display = tk.Entry(root, font=("Arial", 22), borderwidth=5, relief="ridge")
display.pack(fill="both", padx=10, pady=10)


# -----------------------------
# HISTORY STORAGE
# -----------------------------
history = []


# -----------------------------
# HISTORY UI (right side panel)
# -----------------------------
history_frame = tk.Frame(root)
history_frame.pack(side="right", fill="y", padx=10)

tk.Label(history_frame, text="History", font=("Arial", 14, "bold")).pack()

history_listbox = tk.Listbox(history_frame, width=25, height=25)
history_listbox.pack()


# -----------------------------
# CORE FUNCTIONS
# -----------------------------
def press(value):
    """
    Insert value into calculator display.
    """
    display.insert(tk.END, value)


def clear():
    """
    Clear display.
    """
    display.delete(0, tk.END)


def add_to_history(expression, result):
    """
    Save calculation to history and update UI list.
    """
    entry = f"{expression} = {result}"
    history.append(entry)

    history_listbox.insert(tk.END, entry)


def use_history(event):
    """
    When user clicks history item,
    load result back into display.
    """
    selection = history_listbox.curselection()

    if selection:
        value = history_listbox.get(selection[0])

        # split "expr = result"
        result = value.split("=")[-1].strip()

        display.delete(0, tk.END)
        display.insert(0, result)


history_listbox.bind("<<ListboxSelect>>", use_history)


def calculate():
    """
    Evaluate expression using engine and store history.
    """
    expr = display.get()

    try:
        result = evaluate_expression(expr)
    except Exception:
        result = "Error"

    # update display
    display.delete(0, tk.END)
    display.insert(0, str(result))

    # save history
    add_to_history(expr, result)


# -----------------------------
# SCIENTIFIC HELPERS
# -----------------------------
def insert_func(func_name):
    display.insert(tk.END, func_name + "(")


def insert_constant(value):
    display.insert(tk.END, str(value))


# -----------------------------
# REFINED SCIENTIFIC BUTTON LAYOUT
# -----------------------------

button_frame = tk.Frame(root)
button_frame.pack()


# -----------------------------
# TOP SCIENTIFIC ROW
# -----------------------------
scientific_row = tk.Frame(button_frame)
scientific_row.pack(pady=5)

tk.Button(scientific_row, text="sin", width=6,
          command=lambda: insert_func("sin")).grid(row=0, column=0)

tk.Button(scientific_row, text="cos", width=6,
          command=lambda: insert_func("cos")).grid(row=0, column=1)

tk.Button(scientific_row, text="tan", width=6,
          command=lambda: insert_func("tan")).grid(row=0, column=2)

tk.Button(scientific_row, text="sqrt", width=6,
          command=lambda: insert_func("sqrt")).grid(row=0, column=3)

tk.Button(scientific_row, text="π", width=6,
          command=lambda: insert_constant(math.pi)).grid(row=0, column=4)

tk.Button(scientific_row, text="e", width=6,
          command=lambda: insert_constant(math.e)).grid(row=0, column=5)


# -----------------------------
# MAIN GRID (numbers + operators)
# -----------------------------
grid = tk.Frame(button_frame)
grid.pack()


# Row 1
tk.Button(grid, text="7", width=6, command=lambda: press("7")).grid(row=0, column=0)
tk.Button(grid, text="8", width=6, command=lambda: press("8")).grid(row=0, column=1)
tk.Button(grid, text="9", width=6, command=lambda: press("9")).grid(row=0, column=2)
tk.Button(grid, text="/", width=6, command=lambda: press("/")).grid(row=0, column=3)
tk.Button(grid, text="C", width=6, command=clear).grid(row=0, column=4)


# Row 2
tk.Button(grid, text="4", width=6, command=lambda: press("4")).grid(row=1, column=0)
tk.Button(grid, text="5", width=6, command=lambda: press("5")).grid(row=1, column=1)
tk.Button(grid, text="6", width=6, command=lambda: press("6")).grid(row=1, column=2)
tk.Button(grid, text="*", width=6, command=lambda: press("*")).grid(row=1, column=3)
tk.Button(grid, text="(", width=6, command=lambda: press("(")).grid(row=1, column=4)


# Row 3
tk.Button(grid, text="1", width=6, command=lambda: press("1")).grid(row=2, column=0)
tk.Button(grid, text="2", width=6, command=lambda: press("2")).grid(row=2, column=1)
tk.Button(grid, text="3", width=6, command=lambda: press("3")).grid(row=2, column=2)
tk.Button(grid, text="-", width=6, command=lambda: press("-")).grid(row=2, column=3)
tk.Button(grid, text=")", width=6, command=lambda: press(")")).grid(row=2, column=4)


# Row 4
tk.Button(grid, text="0", width=6, command=lambda: press("0")).grid(row=3, column=0)
tk.Button(grid, text=".", width=6, command=lambda: press(".")).grid(row=3, column=1)
tk.Button(grid, text="+", width=6, command=lambda: press("+")).grid(row=3, column=2)
tk.Button(grid, text="=", width=6, command=calculate).grid(row=3, column=3)

# -----------------------------
# CONSTANTS + SPECIAL BUTTONS
# -----------------------------
bottom = tk.Frame(root)
bottom.pack(pady=10)


tk.Button(bottom, text="π", width=10,
          command=lambda: insert_constant(math.pi)).grid(row=0, column=0)

tk.Button(bottom, text="e", width=10,
          command=lambda: insert_constant(math.e)).grid(row=0, column=1)

tk.Button(bottom, text="x²", width=10,
          command=lambda: press("**2")).grid(row=0, column=2)


# -----------------------------
# CONTROL BUTTONS
# -----------------------------
tk.Button(root, text="C", height=2, command=clear).pack(fill="both")
tk.Button(root, text="=", height=2, command=calculate).pack(fill="both")

# -----------------------------
# KEYBOARD SUPPORT
# -----------------------------

def on_key(event):
    """
    Handles keyboard input for calculator.
    """

    key = event.char

    # Allow digits and operators
    if key in "0123456789.()*/-+":
        press(key)

    # Enter = calculate
    elif event.keysym == "Return":
        calculate()

    # Backspace = delete last character
    elif event.keysym == "BackSpace":
        current = display.get()
        display.delete(0, tk.END)
        display.insert(0, current[:-1])


# Bind keyboard events
root.bind("<Key>", on_key)

# -----------------------------
# START APP
# -----------------------------
root.mainloop()