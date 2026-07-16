"""
gui.py

Builds and controls the scientific calculator GUI.

The mathematical evaluation is handled by engine.py.
Display manipulation is handled by display.py.
Buttons, keyboard controls, memory, themes, and settings
are handled by their own modules.
"""

import json
import math
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import core.engine as engine
from ui.buttons import (
    create_keypad,
    create_memory_buttons,
    create_scientific_buttons,
    create_special_buttons,
)
from ui.display import (
    append_display,
    backspace,
    clear_display,
    get_display,
    replace_display,
    set_display_widget,
)
from core.engine import evaluate_expression, format_result
from ui.keyboard import bind_keyboard
from core.memory import MemoryRegister
from core.settings import load_settings, update_setting
from ui.themes import apply_theme


# --------------------------------------------------
# FILE PATHS
# --------------------------------------------------

HISTORY_FILE = Path("history.json")


# --------------------------------------------------
# APPLICATION SETTINGS AND STATE
# --------------------------------------------------

settings = load_settings()

ANS: int | float = 0
ANGLE_MODE: str = str(settings.get("angle_mode", "RAD"))

memory = MemoryRegister()
history: list[str] = []


# --------------------------------------------------
# WINDOW SETUP
# --------------------------------------------------

root = tk.Tk()
root.title("Scientific Calculator")

window_width = int(settings.get("window_width", 650))
window_height = int(settings.get("window_height", 600))

root.geometry(f"{window_width}x{window_height}")
root.minsize(620, 550)


# --------------------------------------------------
# MAIN LAYOUT
# --------------------------------------------------

main_frame = tk.Frame(root)
main_frame.pack(fill="both", expand=True, padx=10, pady=10)

calculator_frame = tk.Frame(main_frame)
calculator_frame.pack(side="left", fill="both", expand=True)

history_frame = tk.Frame(main_frame)
history_frame.pack(side="right", fill="y", padx=(10, 0))


# --------------------------------------------------
# DISPLAY
# --------------------------------------------------

display = tk.Entry(
    calculator_frame,
    font=("Arial", 22),
    borderwidth=5,
    relief="ridge",
    justify="right",
    state="readonly",
    readonlybackground="white",
    insertontime=0,
)

display.pack(fill="x", pady=(0, 10))

# Prevent mouse clicks from placing a cursor inside the display.
display.bind("<Button-1>", lambda event: "break")

# Register the Entry widget with display.py.
set_display_widget(display)


# --------------------------------------------------
# STATUS BAR
# --------------------------------------------------

status_variable = tk.StringVar()

status_label = tk.Label(
    calculator_frame,
    textvariable=status_variable,
    anchor="w",
    font=("Arial", 9),
)

status_label.pack(fill="x", pady=(0, 5))


def update_status() -> None:
    """
    Update the status bar with the current angle mode,
    memory state, and ANS value.
    """
    memory_indicator = "M" if memory.has_value() else "-"

    status_variable.set(
        f"Mode: {ANGLE_MODE}    "
        f"Memory: {memory_indicator}    "
        f"ANS: {format_result(ANS)}"
    )


# --------------------------------------------------
# HISTORY FILE OPERATIONS
# --------------------------------------------------

def load_history() -> list[str]:
    """
    Load saved calculator history from history.json.

    Returns an empty list if the file does not exist,
    is unreadable, or contains invalid JSON.
    """
    if not HISTORY_FILE.exists():
        return []

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            loaded_history = json.load(file)

        if isinstance(loaded_history, list):
            return [str(item) for item in loaded_history]

    except (json.JSONDecodeError, OSError):
        pass

    return []


def save_history() -> None:
    """Save the current history list to history.json."""
    try:
        with HISTORY_FILE.open("w", encoding="utf-8") as file:
            json.dump(history, file, indent=4)

    except OSError as error:
        messagebox.showerror(
            "History Error",
            f"Could not save history:\n{error}",
        )


def add_to_history(expression: str, result: object) -> None:
    """
    Add one completed calculation to memory, the listbox,
    and the history file.
    """
    entry = f"{expression} = {result}"

    history.append(entry)
    history_listbox.insert(tk.END, entry)
    history_listbox.see(tk.END)

    save_history()


def clear_history() -> None:
    """Clear all history from memory, the GUI, and disk."""
    history.clear()
    history_listbox.delete(0, tk.END)
    save_history()


def use_history(_event: tk.Event) -> None:
    """
    Recall the result from the selected history entry.

    For example:

        5 + 5 = 10

    places 10 into the display.
    """
    selection = history_listbox.curselection()

    if not selection:
        return

    entry = history_listbox.get(selection[0])

    # Split only once from the right, in case an expression
    # later contains another equals sign.
    _expression, separator, result = entry.rpartition("=")

    if separator:
        replace_display(result.strip())


# --------------------------------------------------
# HISTORY PANEL
# --------------------------------------------------

history_title = tk.Label(
    history_frame,
    text="History",
    font=("Arial", 14, "bold"),
)

history_title.pack(pady=(0, 5))

history_listbox = tk.Listbox(
    history_frame,
    width=27,
    height=25,
)

history_listbox.pack(fill="both", expand=True)
history_listbox.bind("<<ListboxSelect>>", use_history)

clear_history_button = tk.Button(
    history_frame,
    text="Clear History",
    command=clear_history,
)

clear_history_button.pack(fill="x", pady=(5, 0))

history = load_history()

for history_item in history:
    history_listbox.insert(tk.END, history_item)


# --------------------------------------------------
# ANGLE MODE
# --------------------------------------------------

def sine(value: float) -> float:
    """Calculate sine using the selected DEG/RAD mode."""
    if ANGLE_MODE == "DEG":
        value = math.radians(value)

    return math.sin(value)


def cosine(value: float) -> float:
    """Calculate cosine using the selected DEG/RAD mode."""
    if ANGLE_MODE == "DEG":
        value = math.radians(value)

    return math.cos(value)


def tangent(value: float) -> float:
    """Calculate tangent using the selected DEG/RAD mode."""
    if ANGLE_MODE == "DEG":
        value = math.radians(value)

    return math.tan(value)


# Replace the engine's normal trig functions with
# our angle-mode-aware versions.
engine.functions["sin"] = sine
engine.functions["cos"] = cosine
engine.functions["tan"] = tangent


def toggle_angle_mode() -> None:
    """Switch between radians and degrees."""
    global ANGLE_MODE

    ANGLE_MODE = "DEG" if ANGLE_MODE == "RAD" else "RAD"

    mode_button.config(text=f"Mode: {ANGLE_MODE}")
    update_setting(settings, "angle_mode", ANGLE_MODE)
    update_status()


# --------------------------------------------------
# DISPLAY INPUT HELPERS
# --------------------------------------------------

def safe_insert(value: str) -> None:
    """
    Insert calculator input while preventing some common
    invalid input sequences.

    Examples:
    - Replaces repeated operators such as ++ or /*
    - Prevents multiple decimal points in one number
    - Prevents factorial at the start of an expression
    """
    current = get_display()

    binary_operators = "+-*/^"

    # A binary operator cannot normally start an expression.
    # A leading minus is allowed for negative numbers.
    if value in binary_operators and not current:
        if value == "-":
            append_display(value)
        return

    # Replace the previous operator instead of stacking operators.
    if value in binary_operators and current:
        if current[-1] in binary_operators:
            replace_display(current[:-1] + value)
            return

    # Prevent multiple decimal points in the current number.
    if value == ".":
        current_number = ""

        for character in reversed(current):
            if character in "+-*/^()":
                break

            current_number = character + current_number

        if "." in current_number:
            return

        # Entering "." into an empty expression becomes "0.".
        if not current or current[-1] in "+-*/^(":
            append_display("0.")
            return

    # Factorial requires something before it.
    if value == "!":
        if not current:
            return

        if current[-1] in "+-*/^(.!":
            return

    append_display(value)


def insert_function(function_name: str) -> None:
    """Insert a scientific function followed by an opening parenthesis."""
    append_display(f"{function_name}(")


def insert_constant(value: str) -> None:
    """Insert a mathematical constant or special value."""
    current = get_display()

    # Add multiplication automatically when a number or closing
    # parenthesis appears immediately before a constant.
    if current and (current[-1].isdigit() or current[-1] == ")"):
        append_display("*")

    append_display(str(value))


# --------------------------------------------------
# CALCULATION
# --------------------------------------------------

def calculate() -> None:
    """Evaluate the displayed expression and store its result."""
    global ANS

    original_expression = get_display().strip()

    if not original_expression:
        return

    expression_for_engine = original_expression.replace("ANS", str(ANS))

    try:
        result = evaluate_expression(expression_for_engine)
        result = format_result(result)

    except ZeroDivisionError:
        result = "Cannot divide by zero"

    except (SyntaxError, TypeError, ValueError, OverflowError):
        result = "Error"

    except Exception:
        # Prevent the GUI from crashing if an unexpected parser error occurs.
        result = "Error"

    if isinstance(result, (int, float)):
        ANS = result

    replace_display(str(result))
    add_to_history(original_expression, result)
    update_status()


# --------------------------------------------------
# MEMORY CONTROLS
# --------------------------------------------------

def get_numeric_display_value() -> float | None:
    """
    Return the current display as a number.

    If the display contains an expression, attempt to evaluate it.
    Returns None when it cannot be converted or evaluated.
    """
    text = get_display().strip()

    if not text:
        return None

    try:
        return float(text)

    except ValueError:
        try:
            expression = text.replace("ANS", str(ANS))
            result = evaluate_expression(expression)
            return float(result)

        except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
            return None


def memory_add() -> None:
    """Add the current value or expression result to memory."""
    value = get_numeric_display_value()

    if value is None:
        return

    memory.add(value)
    update_status()


def memory_subtract() -> None:
    """Subtract the current value or expression result from memory."""
    value = get_numeric_display_value()

    if value is None:
        return

    memory.subtract(value)
    update_status()


def memory_recall() -> None:
    """Insert the stored memory value into the display."""
    recalled_value = format_result(memory.recall())

    current = get_display()

    if current and (current[-1].isdigit() or current[-1] == ")"):
        append_display("*")

    append_display(str(recalled_value))


def memory_clear() -> None:
    """Clear the manual memory register."""
    memory.clear()
    update_status()


# --------------------------------------------------
# THEME CONTROLS
# --------------------------------------------------

def set_theme(theme_name: str) -> None:
    """Apply and save a theme."""
    apply_theme(root, theme_name)
    update_setting(settings, "theme", theme_name)


def toggle_theme() -> None:
    """Toggle between the light and dark themes."""
    current_theme = str(settings.get("theme", "light"))
    next_theme = "dark" if current_theme == "light" else "light"

    set_theme(next_theme)


# --------------------------------------------------
# BUTTON WIDGETS
# --------------------------------------------------

button_frame = tk.Frame(calculator_frame)
button_frame.pack(fill="both", expand=True)

create_scientific_buttons(
    parent=button_frame,
    insert_function=insert_function,
    insert_constant=insert_constant,
)

create_memory_buttons(
    parent=button_frame,
    memory_add=memory_add,
    memory_subtract=memory_subtract,
    memory_recall=memory_recall,
    memory_clear=memory_clear,
)

create_keypad(
    parent=button_frame,
    insert_value=safe_insert,
    calculate=calculate,
    clear_display=clear_display,
    backspace=backspace,
)

create_special_buttons(
    parent=button_frame,
    insert_value=safe_insert,
)


# --------------------------------------------------
# CONTROL BUTTONS
# --------------------------------------------------

controls_frame = tk.Frame(calculator_frame)
controls_frame.pack(fill="x", pady=(5, 0))

mode_button = tk.Button(
    controls_frame,
    text=f"Mode: {ANGLE_MODE}",
    command=toggle_angle_mode,
    height=2,
)

mode_button.pack(side="left", fill="x", expand=True, padx=(0, 2))

theme_button = tk.Button(
    controls_frame,
    text="Toggle Theme",
    command=toggle_theme,
    height=2,
)

theme_button.pack(side="left", fill="x", expand=True, padx=(2, 0))


# --------------------------------------------------
# KEYBOARD CONTROLS
# --------------------------------------------------

bind_keyboard(
    root=root,
    insert_callback=safe_insert,
    calculate_callback=calculate,
    backspace_callback=backspace,
    clear_callback=clear_display,
)


# --------------------------------------------------
# WINDOW CLOSING
# --------------------------------------------------

def close_application() -> None:
    """Save window size and close the application."""
    update_setting(settings, "window_width", root.winfo_width())
    update_setting(settings, "window_height", root.winfo_height())

    root.destroy()


root.protocol("WM_DELETE_WINDOW", close_application)


# --------------------------------------------------
# INITIAL APPLICATION STATE
# --------------------------------------------------

replace_display("")
update_status()
apply_theme(root, str(settings.get("theme", "light")))


# --------------------------------------------------
# PUBLIC START FUNCTION
# --------------------------------------------------

def run() -> None:
    """Start the Tkinter application event loop."""
    root.mainloop()