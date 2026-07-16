"""
graphs/plotter.py

Provides an interactive graphing window for the calculator.

Features:
- Plot multiple functions
- Add, remove, show, and hide expressions
- Adjustable x-axis range
- Adjustable sampling resolution
- Mouse-wheel zoom
- Live cursor coordinates
- Matplotlib navigation toolbar
- Safe expression evaluation through graphs.evaluator
"""

import math
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox
from typing import Any

from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure

from graphs.evaluator import evaluate_graph_expression


# --------------------------------------------------
# DEFAULT GRAPH SETTINGS
# --------------------------------------------------

DEFAULT_X_MIN = -10.0
DEFAULT_X_MAX = 10.0
DEFAULT_POINT_COUNT = 1000

MIN_POINT_COUNT = 50
MAX_POINT_COUNT = 20_000

# Values above this magnitude are treated as discontinuities.
# This helps avoid giant vertical lines around asymptotes.
MAX_ABSOLUTE_Y = 1_000_000.0


# --------------------------------------------------
# GRAPH EXPRESSION MODEL
# --------------------------------------------------

@dataclass
class GraphExpression:
    """Stores one graph expression and its visibility state."""

    expression: str
    visible: bool = True


# --------------------------------------------------
# GRAPH WINDOW
# --------------------------------------------------

class GraphWindow:
    """Interactive window for graphing one or more expressions."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_expression: str = "",
    ) -> None:
        """
        Create the graphing window.

        Args:
            parent:
                Parent Tkinter window.

            initial_expression:
                Optional expression supplied by the calculator display.
        """
        self.window = tk.Toplevel(parent)
        self.window.title("Function Graph")
        self.window.geometry("1050x700")
        self.window.minsize(800, 550)

        # Expressions currently stored in the graph window.
        self.expressions: list[GraphExpression] = []

        # Tkinter variables used by the interface.
        self.expression_variable = tk.StringVar(
            value=initial_expression,
        )
        self.x_min_variable = tk.StringVar(
            value=str(DEFAULT_X_MIN),
        )
        self.x_max_variable = tk.StringVar(
            value=str(DEFAULT_X_MAX),
        )
        self.point_count_variable = tk.StringVar(
            value=str(DEFAULT_POINT_COUNT),
        )
        self.status_variable = tk.StringVar(
            value="Add an expression to begin graphing.",
        )
        self.coordinate_variable = tk.StringVar(
            value="x: —    y: —",
        )

        self._create_layout()
        self._bind_events()

        self.expression_entry.focus_set()

        # Automatically add and graph an expression supplied by gui.py.
        if initial_expression.strip():
            self.add_expression()

    # --------------------------------------------------
    # LAYOUT CREATION
    # --------------------------------------------------

    def _create_layout(self) -> None:
        """Create the graph window's main layout."""
        self.main_frame = tk.Frame(self.window)
        self.main_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10,
        )

        self.controls_frame = tk.Frame(self.main_frame)
        self.controls_frame.pack(
            side="left",
            fill="y",
            padx=(0, 10),
        )

        self.graph_frame = tk.Frame(self.main_frame)
        self.graph_frame.pack(
            side="right",
            fill="both",
            expand=True,
        )

        self._create_expression_controls()
        self._create_expression_list()
        self._create_range_controls()
        self._create_graph()
        self._create_status_bar()

    def _create_expression_controls(self) -> None:
        """Create expression input and action buttons."""
        expression_frame = tk.LabelFrame(
            self.controls_frame,
            text="Expression",
            padx=8,
            pady=8,
        )
        expression_frame.pack(
            fill="x",
            pady=(0, 10),
        )

        tk.Label(
            expression_frame,
            text="y =",
            font=("Arial", 11, "bold"),
        ).grid(
            row=0,
            column=0,
            padx=(0, 5),
            pady=5,
        )

        self.expression_entry = tk.Entry(
            expression_frame,
            textvariable=self.expression_variable,
            width=26,
            font=("Arial", 11),
        )
        self.expression_entry.grid(
            row=0,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=5,
        )

        tk.Button(
            expression_frame,
            text="Add / Plot",
            command=self.add_expression,
        ).grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(5, 2),
        )

        tk.Button(
            expression_frame,
            text="Update Selected",
            command=self.update_selected_expression,
        ).grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=2,
        )

        expression_frame.columnconfigure(1, weight=1)

    def _create_expression_list(self) -> None:
        """Create the list of stored graph expressions."""
        list_frame = tk.LabelFrame(
            self.controls_frame,
            text="Functions",
            padx=8,
            pady=8,
        )
        list_frame.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        list_container = tk.Frame(list_frame)
        list_container.pack(
            fill="both",
            expand=True,
        )

        self.expression_listbox = tk.Listbox(
            list_container,
            width=32,
            height=14,
            exportselection=False,
        )
        self.expression_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        scrollbar = tk.Scrollbar(
            list_container,
            orient="vertical",
            command=self.expression_listbox.yview,
        )
        scrollbar.pack(
            side="right",
            fill="y",
        )

        self.expression_listbox.configure(
            yscrollcommand=scrollbar.set,
        )

        tk.Button(
            list_frame,
            text="Show / Hide Selected",
            command=self.toggle_selected_expression,
        ).pack(
            fill="x",
            pady=(8, 2),
        )

        tk.Button(
            list_frame,
            text="Remove Selected",
            command=self.remove_selected_expression,
        ).pack(
            fill="x",
            pady=2,
        )

        tk.Button(
            list_frame,
            text="Clear All",
            command=self.clear_all_expressions,
        ).pack(
            fill="x",
            pady=2,
        )

    def _create_range_controls(self) -> None:
        """Create x-range and graph-resolution inputs."""
        range_frame = tk.LabelFrame(
            self.controls_frame,
            text="Graph Settings",
            padx=8,
            pady=8,
        )
        range_frame.pack(
            fill="x",
        )

        tk.Label(
            range_frame,
            text="x minimum:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=3,
        )

        tk.Entry(
            range_frame,
            textvariable=self.x_min_variable,
            width=12,
        ).grid(
            row=0,
            column=1,
            pady=3,
        )

        tk.Label(
            range_frame,
            text="x maximum:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=3,
        )

        tk.Entry(
            range_frame,
            textvariable=self.x_max_variable,
            width=12,
        ).grid(
            row=1,
            column=1,
            pady=3,
        )

        tk.Label(
            range_frame,
            text="Sample points:",
        ).grid(
            row=2,
            column=0,
            sticky="w",
            pady=3,
        )

        tk.Entry(
            range_frame,
            textvariable=self.point_count_variable,
            width=12,
        ).grid(
            row=2,
            column=1,
            pady=3,
        )

        tk.Button(
            range_frame,
            text="Redraw",
            command=self.plot_all_expressions,
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            range_frame,
            text="Reset View",
            command=self.reset_view,
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

    def _create_graph(self) -> None:
        """Create the embedded Matplotlib graph."""
        self.figure = Figure(
            figsize=(8, 6),
            dpi=100,
        )

        self.axes = self.figure.add_subplot(111)
        self._reset_axes_content()

        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=self.graph_frame,
        )
        self.canvas.draw()

        self.canvas.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

        self.toolbar = NavigationToolbar2Tk(
            self.canvas,
            self.graph_frame,
            pack_toolbar=False,
        )
        self.toolbar.update()
        self.toolbar.pack(
            fill="x",
        )

    def _create_status_bar(self) -> None:
        """Create status and cursor-coordinate displays."""
        status_frame = tk.Frame(self.window)
        status_frame.pack(
            fill="x",
            side="bottom",
        )

        tk.Label(
            status_frame,
            textvariable=self.status_variable,
            anchor="w",
            relief="sunken",
        ).pack(
            side="left",
            fill="x",
            expand=True,
        )

        tk.Label(
            status_frame,
            textvariable=self.coordinate_variable,
            anchor="e",
            relief="sunken",
            width=28,
        ).pack(
            side="right",
        )

    # --------------------------------------------------
    # EVENT BINDINGS
    # --------------------------------------------------

    def _bind_events(self) -> None:
        """Bind keyboard and Matplotlib events."""
        self.expression_entry.bind(
            "<Return>",
            self._add_expression_from_event,
        )

        self.expression_listbox.bind(
            "<Double-Button-1>",
            self._toggle_expression_from_event,
        )

        self.canvas.mpl_connect(
            "motion_notify_event",
            self._update_cursor_coordinates,
        )

        self.canvas.mpl_connect(
            "scroll_event",
            self._zoom_with_mouse_wheel,
        )

    # --------------------------------------------------
    # EXPRESSION MANAGEMENT
    # --------------------------------------------------

    def add_expression(self) -> None:
        """Add the current expression and redraw the graph."""
        expression = self.expression_variable.get().strip()

        if not expression:
            messagebox.showwarning(
                "Missing Expression",
                "Enter an expression containing x.",
                parent=self.window,
            )
            return

        if not self._validate_expression(expression):
            return

        # Avoid adding exact duplicates.
        for stored_expression in self.expressions:
            if stored_expression.expression == expression:
                stored_expression.visible = True
                self._refresh_expression_list()
                self.plot_all_expressions()
                return

        self.expressions.append(
            GraphExpression(expression=expression),
        )

        self.expression_variable.set("")
        self._refresh_expression_list()
        self.plot_all_expressions()

    def update_selected_expression(self) -> None:
        """Replace the selected function with the current input."""
        selected_index = self._get_selected_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Selection",
                "Select a function to update.",
                parent=self.window,
            )
            return

        expression = self.expression_variable.get().strip()

        if not expression:
            messagebox.showwarning(
                "Missing Expression",
                "Enter the replacement expression.",
                parent=self.window,
            )
            return

        if not self._validate_expression(expression):
            return

        self.expressions[selected_index].expression = expression
        self.expressions[selected_index].visible = True

        self.expression_variable.set("")
        self._refresh_expression_list()
        self.plot_all_expressions()

    def toggle_selected_expression(self) -> None:
        """Toggle visibility of the selected function."""
        selected_index = self._get_selected_index()

        if selected_index is None:
            return

        expression = self.expressions[selected_index]
        expression.visible = not expression.visible

        self._refresh_expression_list(
            selected_index=selected_index,
        )
        self.plot_all_expressions()

    def remove_selected_expression(self) -> None:
        """Remove the selected function."""
        selected_index = self._get_selected_index()

        if selected_index is None:
            return

        del self.expressions[selected_index]

        self._refresh_expression_list()
        self.plot_all_expressions()

    def clear_all_expressions(self) -> None:
        """Remove all functions from the graph."""
        self.expressions.clear()
        self.expression_listbox.delete(0, tk.END)

        self.axes.clear()
        self._reset_axes_content()
        self.canvas.draw_idle()

        self.status_variable.set(
            "All graph expressions were cleared.",
        )

    def _refresh_expression_list(
        self,
        selected_index: int | None = None,
    ) -> None:
        """Refresh the expression listbox."""
        self.expression_listbox.delete(0, tk.END)

        for graph_expression in self.expressions:
            visibility = "✓" if graph_expression.visible else "○"

            self.expression_listbox.insert(
                tk.END,
                f"{visibility}  y = {graph_expression.expression}",
            )

        if (
            selected_index is not None
            and selected_index < len(self.expressions)
        ):
            self.expression_listbox.selection_set(selected_index)
            self.expression_listbox.activate(selected_index)

    def _get_selected_index(self) -> int | None:
        """Return the selected expression index, if one exists."""
        selection = self.expression_listbox.curselection()

        if not selection:
            return None

        return int(selection[0])

    # --------------------------------------------------
    # GRAPHING
    # --------------------------------------------------

    def plot_all_expressions(self) -> None:
        """Plot every visible expression."""
        settings = self._read_graph_settings()

        if settings is None:
            return

        x_min, x_max, point_count = settings

        self.axes.clear()
        self._reset_axes_content()

        x_values = self._generate_x_values(
            x_min=x_min,
            x_max=x_max,
            point_count=point_count,
        )

        plotted_count = 0
        total_valid_points = 0

        for graph_expression in self.expressions:
            if not graph_expression.visible:
                continue

            y_values, valid_points = self._evaluate_expression_series(
                expression=graph_expression.expression,
                x_values=x_values,
            )

            if valid_points == 0:
                continue

            self.axes.plot(
                x_values,
                y_values,
                label=f"y = {graph_expression.expression}",
            )

            plotted_count += 1
            total_valid_points += valid_points

        self.axes.set_xlim(x_min, x_max)

        if plotted_count:
            self.axes.legend()

            # Let Matplotlib determine a sensible y-range.
            self.axes.relim()
            self.axes.autoscale_view(
                scalex=False,
                scaley=True,
            )

        self.figure.tight_layout()
        self.canvas.draw_idle()

        if plotted_count:
            self.status_variable.set(
                f"Plotted {plotted_count} function(s) using "
                f"{total_valid_points} valid points."
            )
        else:
            self.status_variable.set(
                "No visible function produced valid graph points."
            )

    def _evaluate_expression_series(
        self,
        expression: str,
        x_values: list[float],
    ) -> tuple[list[float], int]:
        """
        Evaluate one expression across all x-values.

        Invalid or extremely large values become NaN, creating graph gaps.
        """
        y_values: list[float] = []
        valid_points = 0
        previous_y: float | None = None

        for x_value in x_values:
            try:
                y_value = evaluate_graph_expression(
                    expression,
                    x_value,
                )

                if not math.isfinite(y_value):
                    raise ValueError("Non-finite graph value.")

                if abs(y_value) > MAX_ABSOLUTE_Y:
                    raise ValueError("Graph value exceeds safe limit.")

                # Break the line when there is a very large jump.
                # This improves plots around tangent-style asymptotes.
                if previous_y is not None:
                    jump = abs(y_value - previous_y)

                    if jump > MAX_ABSOLUTE_Y / 10:
                        y_values.append(float("nan"))
                        previous_y = None
                        continue

                y_values.append(y_value)
                valid_points += 1
                previous_y = y_value

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                y_values.append(float("nan"))
                previous_y = None

        return y_values, valid_points

    # --------------------------------------------------
    # GRAPH SETTINGS
    # --------------------------------------------------

    def _read_graph_settings(
        self,
    ) -> tuple[float, float, int] | None:
        """Read and validate x-range and sample-count settings."""
        try:
            x_min = float(self.x_min_variable.get())
            x_max = float(self.x_max_variable.get())
            point_count = int(self.point_count_variable.get())

        except ValueError:
            messagebox.showerror(
                "Invalid Graph Settings",
                "The range values must be numbers and sample points "
                "must be a whole number.",
                parent=self.window,
            )
            return None

        if x_min >= x_max:
            messagebox.showerror(
                "Invalid Range",
                "The x minimum must be smaller than the x maximum.",
                parent=self.window,
            )
            return None

        if not MIN_POINT_COUNT <= point_count <= MAX_POINT_COUNT:
            messagebox.showerror(
                "Invalid Sample Count",
                f"Sample points must be between "
                f"{MIN_POINT_COUNT} and {MAX_POINT_COUNT}.",
                parent=self.window,
            )
            return None

        return x_min, x_max, point_count

    def reset_view(self) -> None:
        """Restore the configured x-range and automatic y-range."""
        self.plot_all_expressions()

    # --------------------------------------------------
    # VALIDATION
    # --------------------------------------------------

    def _validate_expression(self, expression: str) -> bool:
        """
        Validate an expression before adding it.

        A few sample values are tested so domain-restricted functions
        can still be accepted when at least one point is valid.
        """
        test_values = (-2.0, -1.0, 0.0, 1.0, 2.0)
        valid_test_found = False
        last_error: Exception | None = None

        for x_value in test_values:
            try:
                result = evaluate_graph_expression(
                    expression,
                    x_value,
                )

                if math.isfinite(result):
                    valid_test_found = True
                    break

            except Exception as error:
                last_error = error

        if valid_test_found:
            return True

        error_message = (
            str(last_error)
            if last_error is not None
            else "The expression produced no valid values."
        )

        messagebox.showerror(
            "Invalid Expression",
            f"Could not graph the expression:\n\n{error_message}",
            parent=self.window,
        )

        return False

    # --------------------------------------------------
    # INTERACTION
    # --------------------------------------------------

    def _update_cursor_coordinates(self, event: Any) -> None:
        """Display graph coordinates underneath the mouse cursor."""
        if event.inaxes is not self.axes:
            self.coordinate_variable.set("x: —    y: —")
            return

        if event.xdata is None or event.ydata is None:
            self.coordinate_variable.set("x: —    y: —")
            return

        self.coordinate_variable.set(
            f"x: {event.xdata:.6g}    y: {event.ydata:.6g}"
        )

    def _zoom_with_mouse_wheel(self, event: Any) -> None:
        """Zoom around the mouse cursor using the scroll wheel."""
        if event.inaxes is not self.axes:
            return

        if event.xdata is None or event.ydata is None:
            return

        current_x_min, current_x_max = self.axes.get_xlim()
        current_y_min, current_y_max = self.axes.get_ylim()

        # Scroll up zooms in; scroll down zooms out.
        scale_factor = 0.8 if event.button == "up" else 1.25

        new_x_width = (
            current_x_max - current_x_min
        ) * scale_factor

        new_y_height = (
            current_y_max - current_y_min
        ) * scale_factor

        x_ratio = (
            event.xdata - current_x_min
        ) / (
            current_x_max - current_x_min
        )

        y_ratio = (
            event.ydata - current_y_min
        ) / (
            current_y_max - current_y_min
        )

        new_x_min = event.xdata - new_x_width * x_ratio
        new_x_max = event.xdata + new_x_width * (1 - x_ratio)

        new_y_min = event.ydata - new_y_height * y_ratio
        new_y_max = event.ydata + new_y_height * (1 - y_ratio)

        self.axes.set_xlim(new_x_min, new_x_max)
        self.axes.set_ylim(new_y_min, new_y_max)

        self.canvas.draw_idle()

    # --------------------------------------------------
    # AXIS HELPERS
    # --------------------------------------------------

    def _reset_axes_content(self) -> None:
        """Restore graph labels, reference axes, and grid."""
        self.axes.set_title("Function Graph")
        self.axes.set_xlabel("x")
        self.axes.set_ylabel("y")
        self.axes.grid(True)

        self.axes.axhline(
            y=0,
            linewidth=0.8,
        )
        self.axes.axvline(
            x=0,
            linewidth=0.8,
        )

    @staticmethod
    def _generate_x_values(
        x_min: float,
        x_max: float,
        point_count: int,
    ) -> list[float]:
        """Generate evenly spaced x-values."""
        if point_count < 2:
            raise ValueError(
                "At least two sample points are required."
            )

        step = (x_max - x_min) / (point_count - 1)

        return [
            x_min + index * step
            for index in range(point_count)
        ]

    # --------------------------------------------------
    # TKINTER EVENT HELPERS
    # --------------------------------------------------

    def _add_expression_from_event(
        self,
        _event: tk.Event,
    ) -> str:
        """Add the expression when Enter is pressed."""
        self.add_expression()
        return "break"

    def _toggle_expression_from_event(
        self,
        _event: tk.Event,
    ) -> str:
        """Toggle expression visibility on double-click."""
        self.toggle_selected_expression()
        return "break"


# --------------------------------------------------
# PUBLIC FUNCTION
# --------------------------------------------------

def open_graph_window(
    parent: tk.Misc,
    initial_expression: str = "",
) -> GraphWindow:
    """
    Open a new interactive graphing window.

    Args:
        parent:
            Calculator's main Tkinter window.

        initial_expression:
            Optional expression to add and graph immediately.
    """
    return GraphWindow(
        parent=parent,
        initial_expression=initial_expression,
    )