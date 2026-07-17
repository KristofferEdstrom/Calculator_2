"""
ui/tooltip.py

Reusable tooltip support for Tkinter widgets.

Example:
    button = tk.Button(parent, text="Save")
    Tooltip(button, "Save the current graph session.")
"""

import tkinter as tk


DEFAULT_DELAY_MS = 450
DEFAULT_WRAP_LENGTH = 320
DEFAULT_OFFSET_X = 14
DEFAULT_OFFSET_Y = 18


class Tooltip:
    """Display a small help popup when the pointer rests over a widget."""

    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        *,
        delay_ms: int = DEFAULT_DELAY_MS,
        wrap_length: int = DEFAULT_WRAP_LENGTH,
    ) -> None:
        """
        Attach a tooltip to a Tkinter widget.

        Args:
            widget:
                Widget that should display the tooltip.

            text:
                Help text shown inside the tooltip.

            delay_ms:
                Delay before the tooltip appears.

            wrap_length:
                Maximum text width before wrapping.
        """
        self.widget = widget
        self.text = text
        self.delay_ms = max(0, delay_ms)
        self.wrap_length = max(100, wrap_length)

        self.tooltip_window: tk.Toplevel | None = None
        self.scheduled_job: str | None = None

        self.widget.bind(
            "<Enter>",
            self._schedule,
            add="+",
        )
        self.widget.bind(
            "<Leave>",
            self._hide,
            add="+",
        )
        self.widget.bind(
            "<ButtonPress>",
            self._hide,
            add="+",
        )
        self.widget.bind(
            "<Destroy>",
            self._handle_widget_destroy,
            add="+",
        )

    def update_text(self, text: str) -> None:
        """Replace the tooltip text."""
        self.text = text

        if self.tooltip_window is not None:
            labels = self.tooltip_window.winfo_children()

            if labels:
                labels[0].configure(text=text)

    def _schedule(
        self,
        _event: tk.Event,
    ) -> None:
        """Schedule the tooltip to appear."""
        self._cancel_schedule()

        self.scheduled_job = self.widget.after(
            self.delay_ms,
            self._show,
        )

    def _show(self) -> None:
        """Create and display the tooltip window."""
        self.scheduled_job = None

        if self.tooltip_window is not None:
            return

        if not self.text.strip():
            return

        try:
            pointer_x = self.widget.winfo_pointerx()
            pointer_y = self.widget.winfo_pointery()
        except tk.TclError:
            return

        x_position = pointer_x + DEFAULT_OFFSET_X
        y_position = pointer_y + DEFAULT_OFFSET_Y

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(
            f"+{x_position}+{y_position}"
        )

        # Keep the tooltip above the application where supported.
        try:
            self.tooltip_window.attributes(
                "-topmost",
                True,
            )
        except tk.TclError:
            pass

        label = tk.Label(
            self.tooltip_window,
            text=self.text,
            justify="left",
            anchor="w",
            background="#fffbe6",
            foreground="#202020",
            relief="solid",
            borderwidth=1,
            padx=7,
            pady=5,
            wraplength=self.wrap_length,
            font=("Segoe UI", 9),
        )
        label.pack()

        # Reposition if the tooltip extends beyond the screen.
        self.tooltip_window.update_idletasks()

        tooltip_width = self.tooltip_window.winfo_width()
        tooltip_height = self.tooltip_window.winfo_height()

        screen_width = self.tooltip_window.winfo_screenwidth()
        screen_height = self.tooltip_window.winfo_screenheight()

        if x_position + tooltip_width > screen_width:
            x_position = max(
                0,
                pointer_x - tooltip_width - DEFAULT_OFFSET_X,
            )

        if y_position + tooltip_height > screen_height:
            y_position = max(
                0,
                pointer_y - tooltip_height - DEFAULT_OFFSET_Y,
            )

        self.tooltip_window.wm_geometry(
            f"+{x_position}+{y_position}"
        )

    def _hide(
        self,
        _event: tk.Event | None = None,
    ) -> None:
        """Cancel and remove the tooltip."""
        self._cancel_schedule()

        if self.tooltip_window is not None:
            try:
                self.tooltip_window.destroy()
            except tk.TclError:
                pass

            self.tooltip_window = None

    def _cancel_schedule(self) -> None:
        """Cancel a pending tooltip display."""
        if self.scheduled_job is None:
            return

        try:
            self.widget.after_cancel(
                self.scheduled_job,
            )
        except tk.TclError:
            pass

        self.scheduled_job = None

    def _handle_widget_destroy(
        self,
        _event: tk.Event,
    ) -> None:
        """Clean up when the attached widget is destroyed."""
        self._hide()