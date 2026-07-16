"""
themes.py

Contains calculator color themes and functions for applying them.
"""

import tkinter as tk


THEMES = {
    "light": {
        "background": "#f3f3f3",
        "foreground": "#111111",
        "button_background": "#ffffff",
        "button_foreground": "#111111",
        "display_background": "#ffffff",
        "display_foreground": "#111111",
        "list_background": "#ffffff",
        "list_foreground": "#111111",
        "select_background": "#0078d4",
        "select_foreground": "#ffffff",
    },
    "dark": {
        "background": "#202020",
        "foreground": "#f5f5f5",
        "button_background": "#323232",
        "button_foreground": "#f5f5f5",
        "display_background": "#171717",
        "display_foreground": "#ffffff",
        "list_background": "#252525",
        "list_foreground": "#f5f5f5",
        "select_background": "#4b8ed6",
        "select_foreground": "#ffffff",
    },
}


def get_theme(name: str) -> dict[str, str]:
    """
    Return a theme by name.

    Falls back to the light theme when an invalid name is supplied.
    """
    return THEMES.get(name, THEMES["light"])


def apply_theme(widget: tk.Widget, theme_name: str) -> None:
    """
    Apply a theme recursively to a widget and all its children.
    """
    theme = get_theme(theme_name)

    _style_widget(widget, theme)

    for child in widget.winfo_children():
        apply_theme(child, theme_name)


def _style_widget(widget: tk.Widget, theme: dict[str, str]) -> None:
    """Apply appropriate colors based on a widget's Tkinter type."""
    try:
        if isinstance(widget, tk.Tk):
            widget.configure(background=theme["background"])

        elif isinstance(widget, tk.Frame):
            widget.configure(background=theme["background"])

        elif isinstance(widget, tk.Label):
            widget.configure(
                background=theme["background"],
                foreground=theme["foreground"],
            )

        elif isinstance(widget, tk.Button):
            widget.configure(
                background=theme["button_background"],
                foreground=theme["button_foreground"],
                activebackground=theme["select_background"],
                activeforeground=theme["select_foreground"],
            )

        elif isinstance(widget, tk.Entry):
            widget.configure(
                readonlybackground=theme["display_background"],
                foreground=theme["display_foreground"],
            )

        elif isinstance(widget, tk.Listbox):
            widget.configure(
                background=theme["list_background"],
                foreground=theme["list_foreground"],
                selectbackground=theme["select_background"],
                selectforeground=theme["select_foreground"],
            )

    except tk.TclError:
        # Some widgets do not support every styling option.
        pass