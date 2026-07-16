"""
buttons.py

Creates the calculator's button sections.

All calculator actions are passed in as callbacks from gui.py.
This module only builds widgets and does not perform calculations.
"""

import tkinter as tk
from collections.abc import Callable
from functools import partial


BUTTON_WIDTH = 6
BUTTON_HEIGHT = 2


def make_button(
    parent: tk.Widget,
    text: str,
    command: Callable[[], None],
    row: int,
    column: int,
    *,
    width: int = BUTTON_WIDTH,
    columnspan: int = 1,
) -> tk.Button:
    """
    Create and position a calculator button.

    Returns the created Button so gui.py can keep a reference if needed.
    """
    button = tk.Button(
        parent,
        text=text,
        width=width,
        height=BUTTON_HEIGHT,
        command=command,
    )

    button.grid(
        row=row,
        column=column,
        columnspan=columnspan,
        padx=2,
        pady=2,
        sticky="nsew",
    )

    return button


def create_scientific_buttons(
    parent: tk.Widget,
    insert_function: Callable[[str], None],
    insert_constant: Callable[[str], None],
    graph_expression: Callable[[], None],
) -> tk.Frame:
    """
    Create the scientific-function buttons.

    The graph button calls a function supplied by gui.py.
    """
    frame = tk.Frame(parent)
    frame.pack(pady=5)

    scientific_buttons = [
        ("sin", partial(insert_function, "sin")),
        ("cos", partial(insert_function, "cos")),
        ("tan", partial(insert_function, "tan")),
        ("sqrt", partial(insert_function, "sqrt")),
        ("ln", partial(insert_function, "ln")),
        ("log10", partial(insert_function, "log10")),
        ("abs", partial(insert_function, "abs")),
        ("π", partial(insert_constant, "pi")),
        ("e", partial(insert_constant, "e")),
        ("ANS", partial(insert_constant, "ANS")),
        ("Graph", graph_expression),
    ]

    for index, (text, command) in enumerate(scientific_buttons):
        row = index // 6
        column = index % 6

        make_button(
            frame,
            text,
            command,
            row,
            column,
        )

    return frame


def create_memory_buttons(
    parent: tk.Widget,
    memory_add: Callable[[], None],
    memory_subtract: Callable[[], None],
    memory_recall: Callable[[], None],
    memory_clear: Callable[[], None],
) -> tk.Frame:
    """Create the M+, M-, MR, and MC buttons."""
    frame = tk.Frame(parent)
    frame.pack(pady=5)

    memory_buttons = [
        ("M+", memory_add),
        ("M-", memory_subtract),
        ("MR", memory_recall),
        ("MC", memory_clear),
    ]

    for column, (text, command) in enumerate(memory_buttons):
        make_button(
            frame,
            text,
            command,
            0,
            column,
        )

    return frame


def create_keypad(
    parent: tk.Widget,
    insert_value: Callable[[str], None],
    calculate: Callable[[], None],
    clear_display: Callable[[], None],
    backspace: Callable[[], None],
) -> tk.Frame:
    """Create the calculator's main numeric keypad."""
    frame = tk.Frame(parent)
    frame.pack(pady=5)

    keypad = [
        ("7", 0, 0),
        ("8", 0, 1),
        ("9", 0, 2),
        ("/", 0, 3),
        ("(", 0, 4),
        ("4", 1, 0),
        ("5", 1, 1),
        ("6", 1, 2),
        ("*", 1, 3),
        (")", 1, 4),
        ("1", 2, 0),
        ("2", 2, 1),
        ("3", 2, 2),
        ("-", 2, 3),
        ("⌫", 2, 4),
        ("0", 3, 0),
        (".", 3, 1),
        ("+", 3, 2),
        ("=", 3, 3),
        ("C", 3, 4),
    ]

    for text, row, column in keypad:
        if text == "=":
            command = calculate
        elif text == "C":
            command = clear_display
        elif text == "⌫":
            command = backspace
        else:
            # Capture the current text value correctly.
            command = partial(insert_value, text)

        make_button(
            frame,
            text,
            command,
            row,
            column,
        )

    return frame


def create_special_buttons(
    parent: tk.Widget,
    insert_value: Callable[[str], None],
) -> tk.Frame:
    """Create power, square, and factorial buttons."""
    frame = tk.Frame(parent)
    frame.pack(pady=5)

    special_buttons = [
        ("x²", lambda: insert_value("**2")),
        ("xʸ", lambda: insert_value("^")),
        ("!", lambda: insert_value("!")),
    ]

    for column, (text, command) in enumerate(special_buttons):
        make_button(
            frame,
            text,
            command,
            0,
            column,
            width=10,
        )

    return frame