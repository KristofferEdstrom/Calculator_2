"""
display.py

Contains helper functions for interacting with the calculator display.

No other module should directly modify the Tkinter Entry widget.
"""

import tkinter as tk

# Reference to the Entry widget
_display = None


def set_display_widget(widget: tk.Entry) -> None:
    """
    Store a reference to the calculator display.
    """
    global _display
    _display = widget


def get_display() -> str:
    """
    Return the current display text.
    """
    return _display.get()


def replace_display(text: str) -> None:
    """
    Replace the entire display.
    """
    _display.config(state="normal")
    _display.delete(0, tk.END)
    _display.insert(0, text)
    _display.config(state="readonly")


def append_display(text: str) -> None:
    """
    Append text to the display.
    """
    _display.config(state="normal")
    _display.insert(tk.END, text)
    _display.config(state="readonly")


def clear_display() -> None:
    """
    Clear the display.
    """
    replace_display("")


def backspace() -> None:
    """
    Delete the last character.
    """
    current = get_display()
    replace_display(current[:-1])