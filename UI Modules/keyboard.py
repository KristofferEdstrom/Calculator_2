"""
keyboard.py

Handles keyboard shortcuts for the calculator.

The module uses callbacks supplied by gui.py. This avoids circular imports.
"""

import tkinter as tk
from collections.abc import Callable


def bind_keyboard(
    root: tk.Tk,
    insert_callback: Callable[[str], None],
    calculate_callback: Callable[[], None],
    backspace_callback: Callable[[], None],
    clear_callback: Callable[[], None],
) -> None:
    """
    Bind calculator keyboard shortcuts to the main window.

    Supported keys:
    - Numbers and operators: inserted into the expression
    - Enter: calculate
    - Backspace: remove last character
    - Escape: clear display
    """

    def on_key(event: tk.Event) -> str:
        """Handle one keyboard event."""
        key = event.char
        keysym = event.keysym

        # Insert calculator-compatible characters.
        if key in "0123456789.()*/-+^!":
            insert_callback(key)
            return "break"

        # Evaluate the current expression.
        if keysym in {"Return", "KP_Enter"}:
            calculate_callback()
            return "break"

        # Remove the last character.
        if keysym == "BackSpace":
            backspace_callback()
            return "break"

        # Clear the calculator display.
        if keysym == "Escape":
            clear_callback()
            return "break"

        # Block other characters from reaching the readonly display.
        return "break"

    root.bind("<Key>", on_key)