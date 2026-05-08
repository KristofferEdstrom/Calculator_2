import tkinter as tk
import math

# ------------------------
# SAFE EVALUATOR (simple for GUI start)
# ------------------------

def evaluate(expr):
    try:
        return eval(expr, {"__builtins__": None}, math.__dict__)
    except Exception:
        return "Error"


# ------------------------
# GUI SETUP
# ------------------------

root = tk.Tk()
root.title("Scientific Calculator")
root.geometry("350x450")


# Display
display = tk.Entry(root, font=("Arial", 20), borderwidth=5, relief="ridge")
display.pack(fill="both", padx=10, pady=10)


# ------------------------
# FUNCTIONS
# ------------------------

def press(value):
    display.insert(tk.END, value)


def clear():
    display.delete(0, tk.END)


def calculate():
    expr = display.get()
    result = evaluate(expr)
    display.delete(0, tk.END)
    display.insert(0, str(result))


# ------------------------
# BUTTONS
# ------------------------

buttons = [
    "7", "8", "9", "/",
    "4", "5", "6", "*",
    "1", "2", "3", "-",
    "0", ".", "(", ")",
]

frame = tk.Frame(root)
frame.pack()

for i, b in enumerate(buttons):
    tk.Button(frame, text=b, width=5, height=2,
              command=lambda v=b: press(v)).grid(row=i//4, column=i%4)


# Control buttons
tk.Button(root, text="C", command=clear).pack(fill="both")
tk.Button(root, text="=", command=calculate).pack(fill="both")


root.mainloop()