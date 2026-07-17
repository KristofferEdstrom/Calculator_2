"""
graphs/plotter.py

Interactive graphing window for the scientific calculator.

Features:
- Plot multiple functions
- Add, update, remove, show, and hide expressions
- Live graph preview while typing
- Adjustable x-range and sampling resolution
- Mouse-wheel zoom around the cursor
- Live cursor coordinates
- Clickable nearest-curve point selection
- Root detection
- Intersection detection
- Table of values for a selected function
- CSV export for table data
- Matplotlib navigation toolbar
- Safe expression evaluation through graphs.evaluator
"""

import ast
import csv
import json
import math
import re
import tkinter as tk
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any

from matplotlib.artist import Artist
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)
from matplotlib.figure import Figure

from graphs.evaluator import evaluate_graph_expression
from ui.tooltip import Tooltip


# --------------------------------------------------
# DEFAULT GRAPH SETTINGS
# --------------------------------------------------

DEFAULT_X_MIN = -10.0
DEFAULT_X_MAX = 10.0
DEFAULT_POINT_COUNT = 1000

MIN_POINT_COUNT = 50
MAX_POINT_COUNT = 20_000

MAX_ABSOLUTE_Y = 1_000_000.0
POINT_SELECTION_THRESHOLD = 0.05
LIVE_UPDATE_DELAY_MS = 350

ROOT_Y_TOLERANCE = 1e-7
POINT_DUPLICATE_TOLERANCE = 1e-5

DEFAULT_TABLE_X_MIN = -5.0
DEFAULT_TABLE_X_MAX = 5.0
DEFAULT_TABLE_STEP = 1.0
MAX_TABLE_ROWS = 10_000

# Numerical derivative settings.
DERIVATIVE_STEP = 1e-5
DEFAULT_INTEGRAL_A = 0.0
DEFAULT_INTEGRAL_B = 1.0
INTEGRATION_INTERVALS = 1000
EXTREMA_DERIVATIVE_TOLERANCE = 1e-5
EXTREMA_DUPLICATE_TOLERANCE = 1e-4
INFLECTION_DUPLICATE_TOLERANCE = 1e-4
SECOND_DERIVATIVE_STEP = 1e-4
DEFAULT_RIEMANN_INTERVALS = 12
MIN_RIEMANN_INTERVALS = 1
MAX_RIEMANN_INTERVALS = 500
ARC_LENGTH_INTERVALS = 1000
DEFAULT_PARAMETRIC_T_MIN = 0.0
DEFAULT_PARAMETRIC_T_MAX = 2 * math.pi
DEFAULT_PARAMETRIC_POINTS = 1200
MIN_PARAMETRIC_POINTS = 100
MAX_PARAMETRIC_POINTS = 20_000
DEFAULT_POLAR_THETA_MIN = 0.0
DEFAULT_POLAR_THETA_MAX = 2 * math.pi
DEFAULT_POLAR_POINTS = 1600
MIN_POLAR_POINTS = 100
MAX_POLAR_POINTS = 20_000
DEFAULT_PIECEWISE_X_MIN = -10.0
DEFAULT_PIECEWISE_X_MAX = 10.0
DEFAULT_PIECEWISE_POINTS = 1600
MIN_PIECEWISE_POINTS = 100
MAX_PIECEWISE_POINTS = 20_000

PARAMETER_DEFAULT_VALUE = 1.0
PARAMETER_MIN_VALUE = -10.0
PARAMETER_MAX_VALUE = 10.0
PARAMETER_RESOLUTION = 0.1
DEFAULT_ANIMATION_DELAY_MS = 60
MIN_ANIMATION_DELAY_MS = 15
MAX_ANIMATION_DELAY_MS = 300

# Names that belong to the expression language rather than sliders.
RESERVED_PARAMETER_NAMES = {
    "x",
    "pi",
    "e",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "sqrt",
    "abs",
    "ln",
    "log",
    "log10",
    "exp",
    "floor",
    "ceil",
    "round",
    "factorial",
    "ANS",
}
SESSION_FILE_EXTENSION = ".graph.json"
SESSION_FILE_TYPES = [
    ("Graph session files", "*.graph.json"),
    ("JSON files", "*.json"),
    ("All files", "*.*"),
]

GRAPH_THEMES = {
    "Light": {
        "figure_facecolor": "white",
        "axes_facecolor": "white",
        "text_color": "black",
        "grid_color": "#c7c7c7",
        "axis_color": "#444444",
    },
    "Dark": {
        "figure_facecolor": "#202124",
        "axes_facecolor": "#2b2d31",
        "text_color": "#f1f3f4",
        "grid_color": "#5f6368",
        "axis_color": "#dadce0",
    },
    "Blueprint": {
        "figure_facecolor": "#0b2d4d",
        "axes_facecolor": "#103b63",
        "text_color": "#eef7ff",
        "grid_color": "#4f86b8",
        "axis_color": "#d6ecff",
    },
    "Presentation": {
        "figure_facecolor": "#f7f3ea",
        "axes_facecolor": "#fffdf7",
        "text_color": "#2a2a2a",
        "grid_color": "#d6cfc0",
        "axis_color": "#555555",
    },
}


# --------------------------------------------------
# DATA MODELS
# --------------------------------------------------

@dataclass
class GraphExpression:
    """Store one graph expression and its display settings."""

    expression: str
    visible: bool = True
    color: str | None = None
    line_width: float = 2.0
    line_style: str = "-"
    custom_label: str = ""

    def legend_label(self) -> str:
        """Return the custom legend label or a default expression label."""
        return self.custom_label.strip() or f"y = {self.expression}"


@dataclass
class SelectedPoint:
    """Store a manually selected point on a plotted curve."""

    expression: str
    x: float
    y: float
    distance: float


@dataclass
class SpecialPoint:
    """Store a detected root or intersection."""

    point_type: str
    x: float
    y: float
    first_expression: str
    second_expression: str | None = None

    def description(self) -> str:
        """Return a readable description for the analysis list."""
        if self.point_type == "root":
            return (
                f"Root: y = {self.first_expression} "
                f"at ({self.x:.8g}, {self.y:.8g})"
            )

        return (
            f"Intersection: y = {self.first_expression} and "
            f"y = {self.second_expression} "
            f"at ({self.x:.8g}, {self.y:.8g})"
        )


# --------------------------------------------------
# TABLE OF VALUES WINDOW
# --------------------------------------------------

class ValuesTableWindow:
    """Display x and f(x) values for one expression."""

    def __init__(
        self,
        parent: tk.Misc,
        expression: str,
    ) -> None:
        """Create a table-of-values window."""
        self.expression = expression
        self.rows: list[tuple[float, float | None]] = []

        self.window = tk.Toplevel(parent)
        self.window.title(f"Table of Values — y = {expression}")
        self.window.geometry("650x600")
        self.window.minsize(500, 400)

        self.x_min_variable = tk.StringVar(
            value=str(DEFAULT_TABLE_X_MIN)
        )
        self.x_max_variable = tk.StringVar(
            value=str(DEFAULT_TABLE_X_MAX)
        )
        self.step_variable = tk.StringVar(
            value=str(DEFAULT_TABLE_STEP)
        )
        self.status_variable = tk.StringVar(
            value=f"Expression: y = {expression}"
        )

        self._create_controls()
        self._create_table()
        self._create_status_bar()

        self.generate_table()

    def _create_controls(self) -> None:
        """Create table range and action controls."""
        controls = tk.LabelFrame(
            self.window,
            text="Table Settings",
            padx=8,
            pady=8,
        )
        controls.pack(
            fill="x",
            padx=10,
            pady=10,
        )

        tk.Label(
            controls,
            text="x minimum:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            controls,
            textvariable=self.x_min_variable,
            width=12,
        ).grid(
            row=0,
            column=1,
            pady=3,
        )

        tk.Label(
            controls,
            text="x maximum:",
        ).grid(
            row=0,
            column=2,
            sticky="w",
            padx=(12, 5),
            pady=3,
        )

        tk.Entry(
            controls,
            textvariable=self.x_max_variable,
            width=12,
        ).grid(
            row=0,
            column=3,
            pady=3,
        )

        tk.Label(
            controls,
            text="Step:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            controls,
            textvariable=self.step_variable,
            width=12,
        ).grid(
            row=1,
            column=1,
            pady=3,
        )

        tk.Button(
            controls,
            text="Generate",
            command=self.generate_table,
        ).grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(12, 5),
            pady=3,
        )

        tk.Button(
            controls,
            text="Export CSV",
            command=self.export_csv,
        ).grid(
            row=1,
            column=3,
            sticky="ew",
            pady=3,
        )

        for column in range(4):
            controls.columnconfigure(column, weight=1)

    def _create_table(self) -> None:
        """Create the scrollable values table."""
        table_frame = tk.Frame(self.window)
        table_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10),
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=("x", "y"),
            show="headings",
        )

        self.tree.heading("x", text="x")
        self.tree.heading(
            "y",
            text=f"f(x) = {self.expression}",
        )

        self.tree.column(
            "x",
            width=180,
            anchor="center",
        )
        self.tree.column(
            "y",
            width=300,
            anchor="center",
        )

        vertical_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )

        horizontal_scrollbar = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview,
        )

        self.tree.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        vertical_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        horizontal_scrollbar.grid(
            row=1,
            column=0,
            sticky="ew",
        )

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

    def _create_status_bar(self) -> None:
        """Create the table window status bar."""
        tk.Label(
            self.window,
            textvariable=self.status_variable,
            anchor="w",
            relief="sunken",
        ).pack(
            fill="x",
            side="bottom",
        )

    def generate_table(self) -> None:
        """Evaluate the expression across the requested x range."""
        settings = self._read_settings()

        if settings is None:
            return

        x_min, x_max, step = settings
        x_values = self._generate_x_values(
            x_min,
            x_max,
            step,
        )

        self.rows.clear()
        self.tree.delete(*self.tree.get_children())

        valid_rows = 0

        for x_value in x_values:
            try:
                y_value = evaluate_graph_expression(
                    self.expression,
                    x_value,
                )

                if (
                    not math.isfinite(y_value)
                    or abs(y_value) > MAX_ABSOLUTE_Y
                ):
                    raise ValueError("Undefined value.")

                stored_y: float | None = y_value
                display_y = f"{y_value:.12g}"
                valid_rows += 1

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                stored_y = None
                display_y = "undefined"

            self.rows.append(
                (x_value, stored_y)
            )

            self.tree.insert(
                "",
                tk.END,
                values=(
                    f"{x_value:.12g}",
                    display_y,
                ),
            )

        self.status_variable.set(
            f"Generated {len(self.rows)} row(s); "
            f"{valid_rows} valid value(s)."
        )

    def export_csv(self) -> None:
        """Export the generated values to a CSV file."""
        if not self.rows:
            messagebox.showinfo(
                "No Table Data",
                "Generate the table before exporting.",
                parent=self.window,
            )
            return

        default_name = "function_values.csv"

        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Table as CSV",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )

        if not filepath:
            return

        try:
            with Path(filepath).open(
                "w",
                newline="",
                encoding="utf-8",
            ) as csv_file:
                writer = csv.writer(csv_file)

                writer.writerow(
                    ["expression", self.expression]
                )
                writer.writerow(["x", "y"])

                for x_value, y_value in self.rows:
                    writer.writerow(
                        [
                            f"{x_value:.15g}",
                            (
                                f"{y_value:.15g}"
                                if y_value is not None
                                else "undefined"
                            ),
                        ]
                    )

        except OSError as error:
            messagebox.showerror(
                "Export Error",
                f"Could not export the CSV file:\n\n{error}",
                parent=self.window,
            )
            return

        self.status_variable.set(
            f"Exported table to {filepath}"
        )

    def _read_settings(
        self,
    ) -> tuple[float, float, float] | None:
        """Read and validate table settings."""
        try:
            x_min = float(self.x_min_variable.get())
            x_max = float(self.x_max_variable.get())
            step = float(self.step_variable.get())

        except ValueError:
            messagebox.showerror(
                "Invalid Table Settings",
                "x minimum, x maximum, and step must be numbers.",
                parent=self.window,
            )
            return None

        if x_min > x_max:
            messagebox.showerror(
                "Invalid Range",
                "x minimum must be smaller than or equal to x maximum.",
                parent=self.window,
            )
            return None

        if step <= 0:
            messagebox.showerror(
                "Invalid Step",
                "The table step must be greater than zero.",
                parent=self.window,
            )
            return None

        estimated_rows = (
            int(math.floor((x_max - x_min) / step)) + 1
        )

        if estimated_rows > MAX_TABLE_ROWS:
            messagebox.showerror(
                "Too Many Rows",
                f"The requested table would contain approximately "
                f"{estimated_rows} rows.\n\n"
                f"The maximum allowed is {MAX_TABLE_ROWS}.",
                parent=self.window,
            )
            return None

        return x_min, x_max, step

    @staticmethod
    def _generate_x_values(
        x_min: float,
        x_max: float,
        step: float,
    ) -> list[float]:
        """Generate table x-values while limiting floating-point drift."""
        values: list[float] = []
        index = 0

        while True:
            x_value = x_min + index * step

            if x_value > x_max + abs(step) * 1e-10:
                break

            values.append(x_value)
            index += 1

            if index > MAX_TABLE_ROWS:
                break

        return values


# --------------------------------------------------
# GRAPH WINDOW
# --------------------------------------------------

class GraphWindow:
    """Interactive window for graphing mathematical functions."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_expression: str = "",
    ) -> None:
        """Create the graphing window."""
        self.window = tk.Toplevel(parent)
        self.window.title("Function Graph")
        self.window.geometry("1180x800")
        self.window.minsize(900, 650)

        self.expressions: list[GraphExpression] = []

        self.plotted_series: list[
            tuple[GraphExpression, list[float], list[float]]
        ] = []

        self.special_points: list[SpecialPoint] = []
        self.special_point_artists: list[Artist] = []

        self.point_marker: Artist | None = None
        self.point_annotation: Artist | None = None

        # Artists created by calculus tools, such as tangent lines.
        self.calculus_artists: list[Artist] = []

        # Local minima and maxima detected for the selected function.
        self.extrema_points: list[SpecialPoint] = []
        self.extrema_artists: list[Artist] = []

        # Inflection points and concavity overlays.
        self.inflection_points: list[SpecialPoint] = []
        self.inflection_artists: list[Artist] = []

        # Dynamic symbolic parameters used by expressions such as
        # a*sin(b*x) + c.
        self.parameter_values: dict[str, tk.DoubleVar] = {}

        # Parameter animation state.
        self.animation_job: str | None = None
        self.animation_direction = 1
        self.animation_parameter_variable = tk.StringVar(value="")
        self.animation_delay_variable = tk.IntVar(
            value=DEFAULT_ANIMATION_DELAY_MS,
        )
        self.animation_mode_variable = tk.StringVar(
            value="Ping-pong",
        )

        self.live_update_job: str | None = None

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
        self.live_update_enabled = tk.BooleanVar(
            value=True,
        )
        self.derivative_x_variable = tk.StringVar(
            value="0",
        )
        self.integral_a_variable = tk.StringVar(
            value=str(DEFAULT_INTEGRAL_A),
        )
        self.integral_b_variable = tk.StringVar(
            value=str(DEFAULT_INTEGRAL_B),
        )
        self.arc_length_a_variable = tk.StringVar(
            value=str(DEFAULT_INTEGRAL_A),
        )
        self.arc_length_b_variable = tk.StringVar(
            value=str(DEFAULT_INTEGRAL_B),
        )
        self.riemann_method_variable = tk.StringVar(
            value="Midpoint",
        )
        self.riemann_intervals_variable = tk.IntVar(
            value=DEFAULT_RIEMANN_INTERVALS,
        )
        self.style_color_variable = tk.StringVar(
            value="",
        )
        self.style_line_width_variable = tk.StringVar(
            value="2.0",
        )
        self.style_line_style_variable = tk.StringVar(
            value="Solid",
        )
        self.style_label_variable = tk.StringVar(
            value="",
        )
        self.graph_theme_variable = tk.StringVar(
            value="Light",
        )
        self.show_grid_variable = tk.BooleanVar(
            value=True,
        )
        self.show_axes_variable = tk.BooleanVar(
            value=True,
        )
        self.show_legend_variable = tk.BooleanVar(
            value=True,
        )
        self.status_variable = tk.StringVar(
            value="Add an expression to begin graphing.",
        )
        self.coordinate_variable = tk.StringVar(
            value="x: —    y: —",
        )

        self._create_layout()
        self._bind_events()

        self.window.protocol(
            "WM_DELETE_WINDOW",
            self._close_window,
        )

        self.expression_entry.focus_set()

        if initial_expression.strip():
            self.add_expression()

    def _close_window(self) -> None:
        """Stop scheduled callbacks before closing the graph window."""
        self.pause_parameter_animation()

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(self.live_update_job)
            except (ValueError, tk.TclError):
                pass
            self.live_update_job = None

        self.window.destroy()

    def _attach_tooltip(
        self,
        widget: tk.Widget,
        text: str,
    ) -> tk.Widget:
        """
        Attach a tooltip and return the widget.

        Returning the widget makes this helper convenient when widgets
        are created and assigned in a single expression.
        """
        Tooltip(
            widget,
            text,
        )

        return widget

    # --------------------------------------------------
    # LAYOUT
    # --------------------------------------------------

    def _create_layout(self) -> None:
        """
        Create the graph window layout.

        The left control panel is placed inside a scrollable canvas,
        preventing lower widgets from being clipped.
        """
        self.main_frame = tk.Frame(self.window)
        self.main_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10,
        )

        # ------------------------------------------
        # Scrollable left sidebar
        # ------------------------------------------

        self.sidebar_frame = tk.Frame(self.main_frame)
        self.sidebar_frame.pack(
            side="left",
            fill="y",
            padx=(0, 10),
        )

        self.sidebar_canvas = tk.Canvas(
            self.sidebar_frame,
            width=290,
            highlightthickness=0,
        )
        self.sidebar_canvas.pack(
            side="left",
            fill="both",
            expand=True,
        )

        self.sidebar_scrollbar = tk.Scrollbar(
            self.sidebar_frame,
            orient="vertical",
            command=self.sidebar_canvas.yview,
        )
        self.sidebar_scrollbar.pack(
            side="right",
            fill="y",
        )

        self.sidebar_canvas.configure(
            yscrollcommand=self.sidebar_scrollbar.set,
        )

        # All control sections live inside this frame.
        self.controls_frame = tk.Frame(self.sidebar_canvas)

        self.sidebar_window = self.sidebar_canvas.create_window(
            (0, 0),
            window=self.controls_frame,
            anchor="nw",
        )

        # Update the scrolling region whenever the sidebar changes size.
        self.controls_frame.bind(
            "<Configure>",
            self._update_sidebar_scrollregion,
        )

        # Keep the inner controls frame the same width as the canvas.
        self.sidebar_canvas.bind(
            "<Configure>",
            self._resize_sidebar_contents,
        )

        # Enable mouse-wheel scrolling while hovering over the sidebar.
        self.sidebar_canvas.bind(
            "<Enter>",
            self._enable_sidebar_mousewheel,
        )
        self.sidebar_canvas.bind(
            "<Leave>",
            self._disable_sidebar_mousewheel,
        )

        # ------------------------------------------
        # Graph area
        # ------------------------------------------

        self.graph_frame = tk.Frame(self.main_frame)
        self.graph_frame.pack(
            side="right",
            fill="both",
            expand=True,
        )

        self._create_expression_controls()
        self._create_expression_list()
        self._create_style_controls()
        self._create_parameter_controls()
        self._create_analysis_controls()
        self._create_calculus_controls()
        self._create_extrema_controls()
        self._create_inflection_controls()
        self._create_session_controls()
        self._create_theme_export_controls()
        self._create_range_controls()
        self._create_graph()
        self._create_status_bar()

    def _update_sidebar_scrollregion(
        self,
        _event: tk.Event,
    ) -> None:
        """Update the scrollable sidebar area."""
        bounding_box = self.sidebar_canvas.bbox("all")

        if bounding_box is not None:
            self.sidebar_canvas.configure(
                scrollregion=bounding_box,
            )

    def _resize_sidebar_contents(
        self,
        event: tk.Event,
    ) -> None:
        """Keep the controls frame as wide as the sidebar canvas."""
        self.sidebar_canvas.itemconfigure(
            self.sidebar_window,
            width=event.width,
        )

    def _enable_sidebar_mousewheel(
        self,
        _event: tk.Event,
    ) -> None:
        """Enable mouse-wheel scrolling over the sidebar."""
        self.window.bind_all(
            "<MouseWheel>",
            self._scroll_sidebar,
        )

    def _disable_sidebar_mousewheel(
        self,
        _event: tk.Event,
    ) -> None:
        """Disable sidebar scrolling when the pointer leaves it."""
        self.window.unbind_all("<MouseWheel>")

    def _scroll_sidebar(
        self,
        event: tk.Event,
    ) -> str:
        """Scroll the sidebar using the mouse wheel."""
        direction = -1 if event.delta > 0 else 1

        self.sidebar_canvas.yview_scroll(
            direction,
            "units",
        )

        return "break"

    def _create_expression_controls(self) -> None:
        """Create expression input widgets."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Expression",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="x",
            pady=(0, 10),
        )

        tk.Label(
            frame,
            text="y =",
            font=("Arial", 11, "bold"),
        ).grid(
            row=0,
            column=0,
            padx=(0, 5),
            pady=5,
        )

        self.expression_entry = tk.Entry(
            frame,
            textvariable=self.expression_variable,
            width=28,
            font=("Arial", 11),
        )
        self.expression_entry.grid(
            row=0,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=5,
        )

        add_button = tk.Button(
            frame,
            text="Add / Plot",
            command=self.add_expression,
        )
        add_button.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(5, 2),
        )
        self._attach_tooltip(
            add_button,
            "Add the expression to the function list and plot it.",
        )

        update_button = tk.Button(
            frame,
            text="Update Selected",
            command=self.update_selected_expression,
        )
        update_button.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=2,
        )
        self._attach_tooltip(
            update_button,
            "Replace the selected function with the expression above.",
        )

        tk.Checkbutton(
            frame,
            text="Live update",
            variable=self.live_update_enabled,
            command=self._handle_live_update_toggle,
        ).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(6, 0),
        )

        frame.columnconfigure(1, weight=1)

    def _create_expression_list(self) -> None:
        """Create the stored-functions list."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Functions",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        container = tk.Frame(frame)
        container.pack(
            fill="both",
            expand=True,
        )

        self.expression_listbox = tk.Listbox(
            container,
            width=34,
            height=8,
            exportselection=False,
        )
        self.expression_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        scrollbar = tk.Scrollbar(
            container,
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

        visibility_button = tk.Button(
            frame,
            text="Show / Hide Selected",
            command=self.toggle_selected_expression,
        )
        visibility_button.pack(
            fill="x",
            pady=(8, 2),
        )
        self._attach_tooltip(
            visibility_button,
            "Toggle visibility for the selected function.",
        )

        remove_button = tk.Button(
            frame,
            text="Remove Selected",
            command=self.remove_selected_expression,
        )
        remove_button.pack(
            fill="x",
            pady=2,
        )
        self._attach_tooltip(
            remove_button,
            "Remove the selected function from the graph.",
        )

        table_button = tk.Button(
            frame,
            text="Open Table of Values",
            command=self.open_values_table,
        )
        table_button.pack(
            fill="x",
            pady=2,
        )
        self._attach_tooltip(
            table_button,
            "Generate x and f(x) values for the selected function.",
        )

        clear_all_button = tk.Button(
            frame,
            text="Clear All",
            command=self.clear_all_expressions,
        )
        clear_all_button.pack(
            fill="x",
            pady=2,
        )
        self._attach_tooltip(
            clear_all_button,
            "Remove every function and graph overlay.",
        )

    def _create_style_controls(self) -> None:
        """Create per-function styling controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Function Style",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="x",
            pady=(0, 10),
        )

        tk.Label(
            frame,
            text="Display name:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            frame,
            textvariable=self.style_label_variable,
            width=16,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=3,
        )

        tk.Label(
            frame,
            text="Line width:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        ttk.Combobox(
            frame,
            textvariable=self.style_line_width_variable,
            values=(
                "1.0",
                "1.5",
                "2.0",
                "2.5",
                "3.0",
                "4.0",
                "5.0",
            ),
            width=13,
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=3,
        )

        tk.Label(
            frame,
            text="Line style:",
        ).grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        ttk.Combobox(
            frame,
            textvariable=self.style_line_style_variable,
            values=(
                "Solid",
                "Dashed",
                "Dotted",
                "Dash-dot",
            ),
            state="readonly",
            width=13,
        ).grid(
            row=2,
            column=1,
            sticky="ew",
            pady=3,
        )

        tk.Button(
            frame,
            text="Choose Color",
            command=self.choose_function_color,
        ).grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(6, 2),
        )

        self.color_preview_label = tk.Label(
            frame,
            text="Automatic",
            relief="sunken",
            width=14,
        )
        self.color_preview_label.grid(
            row=3,
            column=1,
            sticky="ew",
            pady=(6, 2),
        )

        tk.Button(
            frame,
            text="Apply Style to Selected",
            command=self.apply_selected_function_style,
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        tk.Button(
            frame,
            text="Reset Selected Style",
            command=self.reset_selected_function_style,
        ).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        frame.columnconfigure(1, weight=1)

    def _create_parameter_controls(self) -> None:
        """Create symbolic-parameter sliders and animation controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Parameter Sliders",
            padx=8,
            pady=8,
        )
        frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            frame,
            text=(
                "Use letters such as a, b, or c in functions. "
                "Sliders are generated automatically."
            ),
            justify="left",
            wraplength=255,
        ).pack(fill="x", pady=(0, 6))

        self.parameter_sliders_frame = tk.Frame(frame)
        self.parameter_sliders_frame.pack(fill="x", expand=True)

        tk.Button(
            frame,
            text="Refresh Parameters",
            command=self._rebuild_parameter_sliders,
        ).pack(fill="x", pady=(8, 2))

        tk.Button(
            frame,
            text="Reset Parameters to 1",
            command=self.reset_parameters,
        ).pack(fill="x", pady=2)

        ttk.Separator(frame, orient="horizontal").pack(
            fill="x",
            pady=8,
        )

        animation_frame = tk.Frame(frame)
        animation_frame.pack(fill="x")

        tk.Label(animation_frame, text="Animate:").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        self.animation_parameter_menu = ttk.Combobox(
            animation_frame,
            textvariable=self.animation_parameter_variable,
            values=(),
            state="readonly",
            width=12,
        )
        self.animation_parameter_menu.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=3,
        )

        tk.Label(animation_frame, text="Mode:").grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        ttk.Combobox(
            animation_frame,
            textvariable=self.animation_mode_variable,
            values=("Ping-pong", "Loop", "One-shot"),
            state="readonly",
            width=12,
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=3,
        )

        tk.Label(animation_frame, text="Speed:").grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Scale(
            animation_frame,
            from_=MAX_ANIMATION_DELAY_MS,
            to=MIN_ANIMATION_DELAY_MS,
            orient="horizontal",
            variable=self.animation_delay_variable,
            showvalue=False,
        ).grid(
            row=2,
            column=1,
            sticky="ew",
            pady=3,
        )

        button_row = tk.Frame(animation_frame)
        button_row.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 0),
        )

        self.animation_play_button = tk.Button(
            button_row,
            text="▶ Play",
            command=self.start_parameter_animation,
        )
        self._attach_tooltip(
            self.animation_play_button,
            "Animate the selected symbolic parameter.",
        )
        self.animation_play_button.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 2),
        )

        tk.Button(
            button_row,
            text="⏸ Pause",
            command=self.pause_parameter_animation,
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=2,
        )

        tk.Button(
            button_row,
            text="↺ Reset",
            command=self.reset_animation_parameter,
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(2, 0),
        )

        animation_frame.columnconfigure(1, weight=1)

        self.parameter_empty_label = tk.Label(
            self.parameter_sliders_frame,
            text="No symbolic parameters detected.",
            anchor="w",
        )
        self.parameter_empty_label.pack(fill="x")

    def _create_analysis_controls(self) -> None:
        """Create root and intersection analysis controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Roots and Intersections",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        container = tk.Frame(frame)
        container.pack(
            fill="both",
            expand=True,
        )

        self.analysis_listbox = tk.Listbox(
            container,
            width=34,
            height=7,
            exportselection=False,
        )
        self.analysis_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=self.analysis_listbox.yview,
        )
        scrollbar.pack(
            side="right",
            fill="y",
        )

        self.analysis_listbox.configure(
            yscrollcommand=scrollbar.set,
        )

        analysis_button = tk.Button(
            frame,
            text="Find Roots and Intersections",
            command=self.find_roots_and_intersections,
        )
        analysis_button.pack(
            fill="x",
            pady=(8, 2),
        )
        self._attach_tooltip(
            analysis_button,
            "Find x-intercepts and intersections among visible functions.",
        )

        tk.Button(
            frame,
            text="Clear Analysis Markers",
            command=self.clear_analysis_markers,
        ).pack(
            fill="x",
            pady=2,
        )

    def _create_calculus_controls(self) -> None:
        """Create derivative, normal-line, integration, and arc-length controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Calculus",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="x",
            pady=(0, 10),
        )

        # ------------------------------------------
        # Derivative, tangent, and normal controls
        # ------------------------------------------

        tk.Label(
            frame,
            text="Evaluate at x:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            frame,
            textvariable=self.derivative_x_variable,
            width=12,
        ).grid(
            row=0,
            column=1,
            pady=3,
        )

        derivative_button = tk.Button(
            frame,
            text="Derivative + Tangent",
            command=self.show_derivative_and_tangent,
        )
        derivative_button.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )
        self._attach_tooltip(
            derivative_button,
            "Estimate f'(x) and draw the tangent line at the chosen x-value.",
        )

        normal_button = tk.Button(
            frame,
            text="Normal Line",
            command=self.show_normal_line,
        )
        normal_button.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )
        self._attach_tooltip(
            normal_button,
            "Draw the line perpendicular to the tangent at the chosen point.",
        )

        tk.Button(
            frame,
            text="Clear Calculus Overlays",
            command=self.clear_calculus_artists,
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        ttk.Separator(
            frame,
            orient="horizontal",
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=8,
        )

        # ------------------------------------------
        # Definite integration controls
        # ------------------------------------------

        tk.Label(
            frame,
            text="Integral start a:",
        ).grid(
            row=5,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            frame,
            textvariable=self.integral_a_variable,
            width=12,
        ).grid(
            row=5,
            column=1,
            pady=3,
        )

        tk.Label(
            frame,
            text="Integral end b:",
        ).grid(
            row=6,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            frame,
            textvariable=self.integral_b_variable,
            width=12,
        ).grid(
            row=6,
            column=1,
            pady=3,
        )

        integral_button = tk.Button(
            frame,
            text="Integrate + Shade Area",
            command=self.show_integral_area,
        )
        integral_button.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )
        self._attach_tooltip(
            integral_button,
            "Approximate the definite integral and shade the selected interval.",
        )

        ttk.Separator(
            frame,
            orient="horizontal",
        ).grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=8,
        )

        # ------------------------------------------
        # Arc-length controls
        # ------------------------------------------

        tk.Label(
            frame,
            text="Arc start a:",
        ).grid(
            row=9,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            frame,
            textvariable=self.arc_length_a_variable,
            width=12,
        ).grid(
            row=9,
            column=1,
            pady=3,
        )

        tk.Label(
            frame,
            text="Arc end b:",
        ).grid(
            row=10,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Entry(
            frame,
            textvariable=self.arc_length_b_variable,
            width=12,
        ).grid(
            row=10,
            column=1,
            pady=3,
        )

        arc_button = tk.Button(
            frame,
            text="Calculate Arc Length",
            command=self.show_arc_length,
        )
        arc_button.grid(
            row=11,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )
        self._attach_tooltip(
            arc_button,
            "Approximate the curve length between the selected bounds.",
        )

        ttk.Separator(
            frame,
            orient="horizontal",
        ).grid(
            row=12,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=8,
        )

        # ------------------------------------------
        # Riemann-sum controls
        # ------------------------------------------

        tk.Label(
            frame,
            text="Riemann method:",
        ).grid(
            row=13,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        ttk.Combobox(
            frame,
            textvariable=self.riemann_method_variable,
            values=(
                "Left",
                "Right",
                "Midpoint",
                "Trapezoid",
            ),
            state="readonly",
            width=12,
        ).grid(
            row=13,
            column=1,
            pady=3,
        )

        tk.Label(
            frame,
            text="Intervals n:",
        ).grid(
            row=14,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        tk.Spinbox(
            frame,
            from_=MIN_RIEMANN_INTERVALS,
            to=MAX_RIEMANN_INTERVALS,
            textvariable=self.riemann_intervals_variable,
            width=10,
        ).grid(
            row=14,
            column=1,
            pady=3,
        )

        tk.Scale(
            frame,
            from_=MIN_RIEMANN_INTERVALS,
            to=100,
            orient="horizontal",
            variable=self.riemann_intervals_variable,
            showvalue=False,
            command=self._schedule_riemann_redraw,
        ).grid(
            row=15,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=3,
        )

        riemann_button = tk.Button(
            frame,
            text="Show Riemann Sum",
            command=self.show_riemann_sum,
        )
        riemann_button.grid(
            row=16,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )
        self._attach_tooltip(
            riemann_button,
            "Visualize a left, right, midpoint, or trapezoid approximation.",
        )

    def _create_extrema_controls(self) -> None:
        """Create local minimum and maximum controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Local Minima and Maxima",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        container = tk.Frame(frame)
        container.pack(
            fill="both",
            expand=True,
        )

        self.extrema_listbox = tk.Listbox(
            container,
            width=34,
            height=6,
            exportselection=False,
        )
        self.extrema_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=self.extrema_listbox.yview,
        )
        scrollbar.pack(
            side="right",
            fill="y",
        )

        self.extrema_listbox.configure(
            yscrollcommand=scrollbar.set,
        )

        extrema_button = tk.Button(
            frame,
            text="Find Local Extrema",
            command=self.find_local_extrema,
        )
        extrema_button.pack(
            fill="x",
            pady=(8, 2),
        )
        self._attach_tooltip(
            extrema_button,
            "Detect local minima and maxima in the current graph range.",
        )

        tk.Button(
            frame,
            text="Clear Extrema Markers",
            command=self.clear_extrema_markers,
        ).pack(
            fill="x",
            pady=2,
        )

    def _create_inflection_controls(self) -> None:
        """Create inflection-point and concavity controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Inflection and Concavity",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        container = tk.Frame(frame)
        container.pack(
            fill="both",
            expand=True,
        )

        self.inflection_listbox = tk.Listbox(
            container,
            width=34,
            height=6,
            exportselection=False,
        )
        self.inflection_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=self.inflection_listbox.yview,
        )
        scrollbar.pack(
            side="right",
            fill="y",
        )

        self.inflection_listbox.configure(
            yscrollcommand=scrollbar.set,
        )

        inflection_button = tk.Button(
            frame,
            text="Find Inflection Points",
            command=self.find_inflection_points,
        )
        inflection_button.pack(
            fill="x",
            pady=(8, 2),
        )
        self._attach_tooltip(
            inflection_button,
            "Detect points where the graph changes concavity.",
        )

        concavity_button = tk.Button(
            frame,
            text="Show Concavity",
            command=self.show_concavity,
        )
        concavity_button.pack(
            fill="x",
            pady=2,
        )
        self._attach_tooltip(
            concavity_button,
            "Highlight concave-up and concave-down graph regions.",
        )

        tk.Button(
            frame,
            text="Clear Inflection Overlays",
            command=self.clear_inflection_markers,
        ).pack(
            fill="x",
            pady=2,
        )

    def _create_session_controls(self) -> None:
        """Create graph-session save and load controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Graph Session",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="x",
            pady=(0, 10),
        )

        save_session_button = tk.Button(
            frame,
            text="Save Session",
            command=self.save_session,
        )
        save_session_button.pack(
            fill="x",
            pady=2,
        )
        self._attach_tooltip(
            save_session_button,
            "Save functions, styles, ranges, parameters, and settings.",
        )

        load_session_button = tk.Button(
            frame,
            text="Load Session",
            command=self.load_session,
        )
        load_session_button.pack(
            fill="x",
            pady=2,
        )
        self._attach_tooltip(
            load_session_button,
            "Restore a previously saved graph session.",
        )

        new_session_button = tk.Button(
            frame,
            text="New Session",
            command=self.new_session,
        )
        new_session_button.pack(
            fill="x",
            pady=2,
        )
        self._attach_tooltip(
            new_session_button,
            "Clear the current workspace and restore default settings.",
        )

    def _create_theme_export_controls(self) -> None:
        """Create graph theme, visibility, and export controls."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Appearance and Export",
            padx=8,
            pady=8,
        )
        frame.pack(
            fill="x",
            pady=(0, 10),
        )

        tk.Label(
            frame,
            text="Graph theme:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        theme_menu = ttk.Combobox(
            frame,
            textvariable=self.graph_theme_variable,
            values=tuple(GRAPH_THEMES),
            state="readonly",
            width=14,
        )
        theme_menu.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=3,
        )
        theme_menu.bind(
            "<<ComboboxSelected>>",
            self._apply_theme_from_event,
        )

        tk.Checkbutton(
            frame,
            text="Show grid",
            variable=self.show_grid_variable,
            command=self.apply_graph_appearance,
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=2,
        )

        tk.Checkbutton(
            frame,
            text="Show x/y axes",
            variable=self.show_axes_variable,
            command=self.apply_graph_appearance,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=2,
        )

        tk.Checkbutton(
            frame,
            text="Show legend",
            variable=self.show_legend_variable,
            command=self.apply_graph_appearance,
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            pady=2,
        )

        export_png_button = tk.Button(
            frame,
            text="Export PNG",
            command=lambda: self.export_graph("png"),
        )
        export_png_button.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(8, 2),        )
        self._attach_tooltip(
            export_png_button,
            "Export the current graph as a PNG image.",
        )

        export_svg_button = tk.Button(
            frame,
            text="Export SVG",
            command=lambda: self.export_graph("svg"),
        )
        export_svg_button.grid(
            row=4,
            column=1,
            sticky="ew",
            pady=(8, 2),        )
        self._attach_tooltip(
            export_svg_button,
            "Export the current graph as a scalable SVG image.",
        )

        export_pdf_button = tk.Button(
            frame,
            text="Export PDF",
            command=lambda: self.export_graph("pdf"),
        )
        export_pdf_button.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,        )
        self._attach_tooltip(
            export_pdf_button,
            "Export the current graph as a PDF document.",
        )

        ttk.Separator(
            frame,
            orient="horizontal",
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=8,
        )

        parametric_button = tk.Button(
            frame,
            text="Open Parametric Plotter",
            command=self.open_parametric_plotter,
        )
        parametric_button.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,        )
        self._attach_tooltip(
            parametric_button,
            "Open the x(t), y(t) parametric graph workspace.",
        )

        polar_button = tk.Button(
            frame,
            text="Open Polar Plotter",
            command=self.open_polar_plotter,
        )
        polar_button.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,        )
        self._attach_tooltip(
            polar_button,
            "Open the r(theta) polar graph workspace.",
        )

        piecewise_button = tk.Button(
            frame,
            text="Open Piecewise Plotter",
            command=self.open_piecewise_plotter,
        )
        piecewise_button.grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,        )
        self._attach_tooltip(
            piecewise_button,
            "Open the condition-based piecewise function workspace.",
        )

        frame.columnconfigure(1, weight=1)

    def _create_range_controls(self) -> None:
        """Create graph range and resolution inputs."""
        frame = tk.LabelFrame(
            self.controls_frame,
            text="Graph Settings",
            padx=8,
            pady=8,
        )
        frame.pack(fill="x")

        labels = (
            ("x minimum:", self.x_min_variable),
            ("x maximum:", self.x_max_variable),
            ("Sample points:", self.point_count_variable),
        )

        for row, (label_text, variable) in enumerate(labels):
            tk.Label(
                frame,
                text=label_text,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                pady=3,
            )

            tk.Entry(
                frame,
                textvariable=variable,
                width=12,
            ).grid(
                row=row,
                column=1,
                pady=3,
            )

        tk.Button(
            frame,
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
            frame,
            text="Reset View",
            command=self.reset_view,
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        tk.Button(
            frame,
            text="Clear Point Marker",
            command=self._clear_point_marker,
        ).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

    def _create_graph(self) -> None:
        """Create the Matplotlib figure and toolbar."""
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
        self.toolbar.pack(fill="x")

    def _create_status_bar(self) -> None:
        """Create status and coordinate labels."""
        frame = tk.Frame(self.window)
        frame.pack(
            fill="x",
            side="bottom",
        )

        tk.Label(
            frame,
            textvariable=self.status_variable,
            anchor="w",
            relief="sunken",
        ).pack(
            side="left",
            fill="x",
            expand=True,
        )

        tk.Label(
            frame,
            textvariable=self.coordinate_variable,
            anchor="e",
            relief="sunken",
            width=32,
        ).pack(side="right")

    # --------------------------------------------------
    # EVENT BINDINGS
    # --------------------------------------------------

    def _bind_events(self) -> None:
        """Bind Tkinter and Matplotlib events."""
        self.expression_entry.bind(
            "<Return>",
            self._add_expression_from_event,
        )

        self.expression_listbox.bind(
            "<Double-Button-1>",
            self._toggle_expression_from_event,
        )

        self.expression_listbox.bind(
            "<<ListboxSelect>>",
            self._load_selected_function_style,
        )

        self.analysis_listbox.bind(
            "<<ListboxSelect>>",
            self._select_analysis_result,
        )

        self.extrema_listbox.bind(
            "<<ListboxSelect>>",
            self._select_extrema_result,
        )

        self.inflection_listbox.bind(
            "<<ListboxSelect>>",
            self._select_inflection_result,
        )

        self.expression_variable.trace_add(
            "write",
            self._schedule_live_update,
        )

        self.canvas.mpl_connect(
            "motion_notify_event",
            self._update_cursor_coordinates,
        )
        self.canvas.mpl_connect(
            "scroll_event",
            self._zoom_with_mouse_wheel,
        )
        self.canvas.mpl_connect(
            "button_press_event",
            self._select_nearest_point,
        )

    # --------------------------------------------------
    # SYMBOLIC PARAMETERS
    # --------------------------------------------------

    @staticmethod
    def _detect_parameters(
        expression: str,
    ) -> set[str]:
        """Return symbolic parameter names used in an expression."""
        names = set(
            re.findall(
                r"\b[A-Za-z_][A-Za-z0-9_]*\b",
                expression,
            )
        )

        return {
            name
            for name in names
            if name not in RESERVED_PARAMETER_NAMES
        }

    def _ensure_parameters_for_expression(
        self,
        expression: str,
    ) -> None:
        """Create default values for parameters used by an expression."""
        for name in self._detect_parameters(expression):
            if name not in self.parameter_values:
                self.parameter_values[name] = tk.DoubleVar(
                    value=PARAMETER_DEFAULT_VALUE,
                )

    def _rebuild_parameter_sliders(self) -> None:
        """Rebuild sliders from parameters used by all saved functions."""
        detected: set[str] = set()

        for graph_expression in self.expressions:
            detected.update(
                self._detect_parameters(
                    graph_expression.expression,
                )
            )

        previous_values = {
            name: variable.get()
            for name, variable in self.parameter_values.items()
            if name in detected
        }

        self.parameter_values = {
            name: tk.DoubleVar(
                value=previous_values.get(
                    name,
                    PARAMETER_DEFAULT_VALUE,
                )
            )
            for name in sorted(detected)
        }

        for child in self.parameter_sliders_frame.winfo_children():
            child.destroy()

        if not self.parameter_values:
            self.parameter_empty_label = tk.Label(
                self.parameter_sliders_frame,
                text="No symbolic parameters detected.",
                anchor="w",
            )
            self.parameter_empty_label.pack(fill="x")

            self.pause_parameter_animation()
            self.animation_parameter_menu.configure(values=())
            self.animation_parameter_variable.set("")
            return

        parameter_names = tuple(self.parameter_values)

        self.animation_parameter_menu.configure(
            values=parameter_names,
        )

        if (
            self.animation_parameter_variable.get()
            not in self.parameter_values
        ):
            self.animation_parameter_variable.set(
                parameter_names[0]
            )

        for row, (name, variable) in enumerate(
            self.parameter_values.items()
        ):
            row_frame = tk.Frame(
                self.parameter_sliders_frame,
            )
            row_frame.pack(
                fill="x",
                pady=2,
            )

            tk.Label(
                row_frame,
                text=name,
                width=4,
                anchor="w",
                font=("Arial", 10, "bold"),
            ).pack(
                side="left",
            )

            scale = tk.Scale(
                row_frame,
                from_=PARAMETER_MIN_VALUE,
                to=PARAMETER_MAX_VALUE,
                resolution=PARAMETER_RESOLUTION,
                orient="horizontal",
                variable=variable,
                showvalue=True,
                length=185,
                command=partial(
                    self._parameter_changed,
                    name,
                ),
            )
            scale.pack(
                side="left",
                fill="x",
                expand=True,
            )

    def _parameter_changed(
        self,
        _name: str,
        _value: str,
    ) -> None:
        """Redraw the graph whenever a parameter slider changes."""
        self.plot_all_expressions()

    def reset_parameters(self) -> None:
        """Reset every symbolic parameter to its default value."""
        for variable in self.parameter_values.values():
            variable.set(PARAMETER_DEFAULT_VALUE)

        self.plot_all_expressions()

    def _expression_with_parameters(
        self,
        expression: str,
    ) -> str:
        """Substitute slider values into a mathematical expression."""
        resolved_expression = expression

        # Replace longer names first to avoid partial-name collisions.
        for name in sorted(
            self.parameter_values,
            key=len,
            reverse=True,
        ):
            value = self.parameter_values[name].get()

            resolved_expression = re.sub(
                rf"\b{re.escape(name)}\b",
                f"({value:.15g})",
                resolved_expression,
            )

        return resolved_expression

    def _evaluate_parameterized_expression(
        self,
        expression: str,
        x_value: float,
    ) -> float:
        """Evaluate an expression after substituting slider parameters."""
        self._ensure_parameters_for_expression(expression)

        resolved_expression = self._expression_with_parameters(
            expression,
        )

        return evaluate_graph_expression(
            resolved_expression,
            x_value,
        )

    # --------------------------------------------------
    # PARAMETER ANIMATION
    # --------------------------------------------------

    def start_parameter_animation(self) -> None:
        """Start animating the selected symbolic parameter."""
        parameter_name = self.animation_parameter_variable.get()

        if parameter_name not in self.parameter_values:
            messagebox.showinfo(
                "No Parameter Selected",
                "Add a parameterized function and select a parameter.",
                parent=self.window,
            )
            return

        if self.animation_job is not None:
            return

        self.animation_direction = 1
        self.animation_play_button.configure(text="▶ Playing")
        self._animate_parameter_step()

    def pause_parameter_animation(self) -> None:
        """Pause the current parameter animation."""
        if self.animation_job is not None:
            try:
                self.window.after_cancel(self.animation_job)
            except (ValueError, tk.TclError):
                pass
            self.animation_job = None

        if hasattr(self, "animation_play_button"):
            self.animation_play_button.configure(text="▶ Play")

    def reset_animation_parameter(self) -> None:
        """Reset the selected animated parameter."""
        self.pause_parameter_animation()

        parameter_name = self.animation_parameter_variable.get()
        if parameter_name not in self.parameter_values:
            return

        self.parameter_values[parameter_name].set(
            PARAMETER_DEFAULT_VALUE
        )
        self.animation_direction = 1
        self.plot_all_expressions()

    def _animate_parameter_step(self) -> None:
        """Advance the selected parameter by one animation frame."""
        parameter_name = self.animation_parameter_variable.get()

        if parameter_name not in self.parameter_values:
            self.pause_parameter_animation()
            return

        variable = self.parameter_values[parameter_name]
        next_value = (
            variable.get()
            + PARAMETER_RESOLUTION * self.animation_direction
        )
        mode = self.animation_mode_variable.get()

        if next_value > PARAMETER_MAX_VALUE:
            if mode == "Ping-pong":
                self.animation_direction = -1
                next_value = (
                    PARAMETER_MAX_VALUE - PARAMETER_RESOLUTION
                )
            elif mode == "Loop":
                next_value = PARAMETER_MIN_VALUE
            else:
                variable.set(PARAMETER_MAX_VALUE)
                self.plot_all_expressions()
                self.pause_parameter_animation()
                return

        elif next_value < PARAMETER_MIN_VALUE:
            if mode == "Ping-pong":
                self.animation_direction = 1
                next_value = (
                    PARAMETER_MIN_VALUE + PARAMETER_RESOLUTION
                )
            elif mode == "Loop":
                next_value = PARAMETER_MAX_VALUE
            else:
                variable.set(PARAMETER_MIN_VALUE)
                self.plot_all_expressions()
                self.pause_parameter_animation()
                return

        variable.set(next_value)
        self.plot_all_expressions()

        delay = max(
            MIN_ANIMATION_DELAY_MS,
            min(
                MAX_ANIMATION_DELAY_MS,
                int(self.animation_delay_variable.get()),
            ),
        )

        self.animation_job = self.window.after(
            delay,
            self._animate_parameter_step,
        )

    # --------------------------------------------------
    # FUNCTION STYLING
    # --------------------------------------------------

    @staticmethod
    def _line_style_name_to_value(style_name: str) -> str:
        """Convert a readable style name into a Matplotlib line style."""
        styles = {
            "Solid": "-",
            "Dashed": "--",
            "Dotted": ":",
            "Dash-dot": "-.",
        }

        return styles.get(style_name, "-")

    @staticmethod
    def _line_style_value_to_name(style_value: str) -> str:
        """Convert a Matplotlib line style into a readable name."""
        styles = {
            "-": "Solid",
            "--": "Dashed",
            ":": "Dotted",
            "-.": "Dash-dot",
        }

        return styles.get(style_value, "Solid")

    def choose_function_color(self) -> None:
        """Open a color chooser for the selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before choosing its color.",
                parent=self.window,
            )
            return

        initial_color = (
            self.style_color_variable.get().strip()
            or self.expressions[selected_index].color
            or "#1f77b4"
        )

        _rgb_color, hex_color = colorchooser.askcolor(
            color=initial_color,
            parent=self.window,
            title="Choose Function Color",
        )

        if not hex_color:
            return

        self.style_color_variable.set(hex_color)
        self._update_color_preview(hex_color)

    def apply_selected_function_style(self) -> None:
        """Apply the style editor settings to the selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before applying style settings.",
                parent=self.window,
            )
            return

        try:
            line_width = float(
                self.style_line_width_variable.get()
            )
        except ValueError:
            messagebox.showerror(
                "Invalid Line Width",
                "Line width must be a valid number.",
                parent=self.window,
            )
            return

        if not 0.5 <= line_width <= 10:
            messagebox.showerror(
                "Invalid Line Width",
                "Line width must be between 0.5 and 10.",
                parent=self.window,
            )
            return

        graph_expression = self.expressions[selected_index]

        graph_expression.custom_label = (
            self.style_label_variable.get().strip()
        )
        graph_expression.line_width = line_width
        graph_expression.line_style = (
            self._line_style_name_to_value(
                self.style_line_style_variable.get()
            )
        )

        selected_color = self.style_color_variable.get().strip()
        graph_expression.color = selected_color or None

        self._refresh_expression_list(
            selected_index=selected_index,
        )
        self.plot_all_expressions()

        self.status_variable.set(
            f"Updated style for y = {graph_expression.expression}."
        )

    def reset_selected_function_style(self) -> None:
        """Restore automatic styling for the selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before resetting its style.",
                parent=self.window,
            )
            return

        graph_expression = self.expressions[selected_index]
        graph_expression.color = None
        graph_expression.line_width = 2.0
        graph_expression.line_style = "-"
        graph_expression.custom_label = ""

        self._load_style_values(graph_expression)
        self._refresh_expression_list(
            selected_index=selected_index,
        )
        self.plot_all_expressions()

        self.status_variable.set(
            f"Reset style for y = {graph_expression.expression}."
        )

    def _load_selected_function_style(
        self,
        _event: tk.Event,
    ) -> None:
        """Load the selected function's style into the editor."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            return

        self._load_style_values(
            self.expressions[selected_index]
        )

    def _load_style_values(
        self,
        graph_expression: GraphExpression,
    ) -> None:
        """Populate style controls from one function."""
        self.style_label_variable.set(
            graph_expression.custom_label
        )
        self.style_line_width_variable.set(
            f"{graph_expression.line_width:g}"
        )
        self.style_line_style_variable.set(
            self._line_style_value_to_name(
                graph_expression.line_style
            )
        )
        self.style_color_variable.set(
            graph_expression.color or ""
        )
        self._update_color_preview(
            graph_expression.color
        )

    def _update_color_preview(
        self,
        color: str | None,
    ) -> None:
        """Update the color preview label."""
        if not color:
            self.color_preview_label.configure(
                text="Automatic",
                background=self.window.cget("background"),
                foreground="black",
            )
            return

        self.color_preview_label.configure(
            text=color,
            background=color,
            foreground=self._contrast_text_color(color),
        )

    @staticmethod
    def _contrast_text_color(hex_color: str) -> str:
        """Return black or white text based on color brightness."""
        clean_color = hex_color.lstrip("#")

        if len(clean_color) != 6:
            return "black"

        try:
            red = int(clean_color[0:2], 16)
            green = int(clean_color[2:4], 16)
            blue = int(clean_color[4:6], 16)
        except ValueError:
            return "black"

        brightness = (
            0.299 * red
            + 0.587 * green
            + 0.114 * blue
        )

        return "black" if brightness > 160 else "white"

    # --------------------------------------------------
    # ADVANCED GRAPH MODES
    # --------------------------------------------------

    def open_parametric_plotter(self) -> None:
        """Open a dedicated parametric-graph window."""
        ParametricGraphWindow(
            parent=self.window,
            theme_name=self.graph_theme_variable.get(),
        )

    def open_polar_plotter(self) -> None:
        """Open a dedicated polar-graph window."""
        PolarGraphWindow(
            parent=self.window,
            theme_name=self.graph_theme_variable.get(),
        )

    def open_piecewise_plotter(self) -> None:
        """Open a dedicated piecewise-function window."""
        PiecewiseGraphWindow(
            parent=self.window,
            theme_name=self.graph_theme_variable.get(),
        )

    # --------------------------------------------------
    # GRAPH APPEARANCE AND EXPORT
    # --------------------------------------------------

    def _apply_theme_from_event(
        self,
        _event: tk.Event,
    ) -> None:
        """Apply the selected graph theme."""
        self.apply_graph_appearance()

    def apply_graph_appearance(self) -> None:
        """Apply theme, grid, axis, and legend preferences."""
        self._apply_theme_to_axes()

        if self.show_legend_variable.get():
            handles, labels = self.axes.get_legend_handles_labels()

            visible_items = [
                (handle, label)
                for handle, label in zip(handles, labels)
                if label and label != "_nolegend_"
            ]

            if visible_items:
                legend_handles, legend_labels = zip(*visible_items)
                legend = self.axes.legend(
                    legend_handles,
                    legend_labels,
                )
                self._style_legend(legend)
        else:
            legend = self.axes.get_legend()

            if legend is not None:
                legend.remove()

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _apply_theme_to_axes(self) -> None:
        """Apply the selected theme directly to the figure and axes."""
        theme_name = self.graph_theme_variable.get()

        theme = GRAPH_THEMES.get(
            theme_name,
            GRAPH_THEMES["Light"],
        )

        figure_color = theme["figure_facecolor"]
        axes_color = theme["axes_facecolor"]
        text_color = theme["text_color"]
        grid_color = theme["grid_color"]
        axis_color = theme["axis_color"]

        self.figure.set_facecolor(figure_color)
        self.axes.set_facecolor(axes_color)

        self.axes.title.set_color(text_color)
        self.axes.xaxis.label.set_color(text_color)
        self.axes.yaxis.label.set_color(text_color)

        self.axes.tick_params(
            axis="both",
            colors=text_color,
        )

        for spine in self.axes.spines.values():
            spine.set_color(axis_color)

        if self.show_grid_variable.get():
            self.axes.grid(
                True,
                color=grid_color,
                linestyle="--",
                linewidth=0.7,
                alpha=0.65,
            )
        else:
            self.axes.grid(False)

        # Reference-axis artists are tagged when created.
        for artist in self.axes.lines:
            if getattr(artist, "_calculator_reference_axis", False):
                artist.set_visible(
                    self.show_axes_variable.get()
                )
                artist.set_color(axis_color)

    def _style_legend(self, legend: Any) -> None:
        """Style a legend to match the selected graph theme."""
        theme = GRAPH_THEMES.get(
            self.graph_theme_variable.get(),
            GRAPH_THEMES["Light"],
        )

        legend.get_frame().set_facecolor(
            theme["axes_facecolor"]
        )
        legend.get_frame().set_edgecolor(
            theme["axis_color"]
        )

        for text_item in legend.get_texts():
            text_item.set_color(
                theme["text_color"]
            )

    def _refresh_legend(self) -> None:
        """Create, remove, and style the graph legend."""
        existing_legend = self.axes.get_legend()

        if existing_legend is not None:
            existing_legend.remove()

        if not self.show_legend_variable.get():
            return

        handles, labels = self.axes.get_legend_handles_labels()

        filtered = [
            (handle, label)
            for handle, label in zip(handles, labels)
            if label and label != "_nolegend_"
        ]

        if not filtered:
            return

        legend_handles, legend_labels = zip(*filtered)
        legend = self.axes.legend(
            legend_handles,
            legend_labels,
        )
        self._style_legend(legend)

    def export_graph(self, file_format: str) -> None:
        """Export the current graph as PNG, SVG, or PDF."""
        supported_formats = {
            "png": ("PNG image", "*.png"),
            "svg": ("SVG vector image", "*.svg"),
            "pdf": ("PDF document", "*.pdf"),
        }

        if file_format not in supported_formats:
            messagebox.showerror(
                "Export Error",
                f"Unsupported export format: {file_format}",
                parent=self.window,
            )
            return

        description, pattern = supported_formats[file_format]

        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title=f"Export Graph as {file_format.upper()}",
            defaultextension=f".{file_format}",
            initialfile=f"graph.{file_format}",
            filetypes=[
                (description, pattern),
                ("All files", "*.*"),
            ],
        )

        if not filepath:
            return

        try:
            self.figure.savefig(
                filepath,
                format=file_format,
                bbox_inches="tight",
                facecolor=self.figure.get_facecolor(),
            )

        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Export Error",
                f"Could not export the graph:\n\n{error}",
                parent=self.window,
            )
            return

        self.status_variable.set(
            f"Exported graph to {filepath}"
        )

    # --------------------------------------------------
    # GRAPH SESSION PERSISTENCE
    # --------------------------------------------------

    def save_session(self) -> None:
        """Save the current graph workspace to a JSON session file."""
        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title="Save Graph Session",
            defaultextension=SESSION_FILE_EXTENSION,
            initialfile="graph_session.graph.json",
            filetypes=SESSION_FILE_TYPES,
        )

        if not filepath:
            return

        session_data = {
            "version": 1,
            "expressions": [
                {
                    "expression": item.expression,
                    "visible": item.visible,
                    "color": item.color,
                    "line_width": item.line_width,
                    "line_style": item.line_style,
                    "custom_label": item.custom_label,
                }
                for item in self.expressions
            ],
            "parameters": {
                name: variable.get()
                for name, variable in self.parameter_values.items()
            },
            "graph_settings": {
                "x_min": self.x_min_variable.get(),
                "x_max": self.x_max_variable.get(),
                "point_count": self.point_count_variable.get(),
            },
            "interface_settings": {
                "live_update": self.live_update_enabled.get(),
                "graph_theme": self.graph_theme_variable.get(),
                "show_grid": self.show_grid_variable.get(),
                "show_axes": self.show_axes_variable.get(),
                "show_legend": self.show_legend_variable.get(),
                "animation_parameter": (
                    self.animation_parameter_variable.get()
                ),
                "animation_delay_ms": (
                    self.animation_delay_variable.get()
                ),
                "animation_mode": (
                    self.animation_mode_variable.get()
                ),
            },
            "calculus_settings": {
                "derivative_x": self.derivative_x_variable.get(),
                "integral_a": self.integral_a_variable.get(),
                "integral_b": self.integral_b_variable.get(),
                "arc_length_a": self.arc_length_a_variable.get(),
                "arc_length_b": self.arc_length_b_variable.get(),
                "riemann_method": self.riemann_method_variable.get(),
                "riemann_intervals": self.riemann_intervals_variable.get(),
            },
        }

        try:
            with Path(filepath).open(
                "w",
                encoding="utf-8",
            ) as session_file:
                json.dump(
                    session_data,
                    session_file,
                    indent=4,
                )

        except (OSError, TypeError) as error:
            messagebox.showerror(
                "Save Session Error",
                f"Could not save the graph session:\n\n{error}",
                parent=self.window,
            )
            return

        self.status_variable.set(
            f"Saved graph session to {filepath}"
        )

    def load_session(self) -> None:
        """Load a graph workspace from a JSON session file."""
        self.pause_parameter_animation()
        filepath = filedialog.askopenfilename(
            parent=self.window,
            title="Load Graph Session",
            filetypes=SESSION_FILE_TYPES,
        )

        if not filepath:
            return

        try:
            with Path(filepath).open(
                "r",
                encoding="utf-8",
            ) as session_file:
                session_data = json.load(session_file)

            self._validate_session_data(session_data)
            self._apply_session_data(session_data)

        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            messagebox.showerror(
                "Load Session Error",
                f"Could not load the graph session:\n\n{error}",
                parent=self.window,
            )
            return

        self.status_variable.set(
            f"Loaded graph session from {filepath}"
        )

    def new_session(self) -> None:
        """Reset the graph workspace after confirmation."""
        self.pause_parameter_animation()
        if self.expressions:
            confirmed = messagebox.askyesno(
                "New Graph Session",
                "Clear the current graph session?",
                parent=self.window,
            )

            if not confirmed:
                return

        self.expressions.clear()
        self.plotted_series.clear()
        self.parameter_values.clear()

        self.expression_variable.set("")
        self.x_min_variable.set(str(DEFAULT_X_MIN))
        self.x_max_variable.set(str(DEFAULT_X_MAX))
        self.point_count_variable.set(
            str(DEFAULT_POINT_COUNT)
        )
        self.live_update_enabled.set(True)

        self.derivative_x_variable.set("0")
        self.integral_a_variable.set(
            str(DEFAULT_INTEGRAL_A)
        )
        self.integral_b_variable.set(
            str(DEFAULT_INTEGRAL_B)
        )
        self.arc_length_a_variable.set(
            str(DEFAULT_INTEGRAL_A)
        )
        self.arc_length_b_variable.set(
            str(DEFAULT_INTEGRAL_B)
        )
        self.riemann_method_variable.set("Midpoint")
        self.riemann_intervals_variable.set(
            DEFAULT_RIEMANN_INTERVALS
        )
        self.style_color_variable.set("")
        self.style_line_width_variable.set("2.0")
        self.style_line_style_variable.set("Solid")
        self.style_label_variable.set("")
        self._update_color_preview(None)
        self.graph_theme_variable.set("Light")
        self.show_grid_variable.set(True)
        self.show_axes_variable.set(True)
        self.show_legend_variable.set(True)
        self.animation_delay_variable.set(
            DEFAULT_ANIMATION_DELAY_MS
        )
        self.animation_mode_variable.set("Ping-pong")
        self.animation_parameter_variable.set("")

        self._refresh_expression_list()
        self._rebuild_parameter_sliders()

        self._clear_point_marker(redraw=False)
        self.clear_analysis_markers(redraw=False)
        self.clear_calculus_artists(redraw=False)
        self.clear_extrema_markers(redraw=False)
        self.clear_inflection_markers(redraw=False)

        self.axes.clear()
        self._reset_axes_content()
        self.canvas.draw_idle()

        self.coordinate_variable.set("x: —    y: —")
        self.status_variable.set(
            "Started a new graph session."
        )

    @staticmethod
    def _validate_session_data(
        session_data: object,
    ) -> None:
        """Validate the minimum required session-file structure."""
        if not isinstance(session_data, dict):
            raise ValueError(
                "The session file must contain a JSON object."
            )

        expressions = session_data.get("expressions")

        if not isinstance(expressions, list):
            raise ValueError(
                "The session file has no valid expression list."
            )

        for item in expressions:
            if not isinstance(item, dict):
                raise ValueError(
                    "An expression entry is not a JSON object."
                )

            expression = item.get("expression")
            visible = item.get("visible")

            if not isinstance(expression, str):
                raise ValueError(
                    "A saved expression is not a string."
                )

            if not isinstance(visible, bool):
                raise ValueError(
                    "A saved visibility value is not true or false."
                )

        graph_settings = session_data.get("graph_settings")

        if not isinstance(graph_settings, dict):
            raise ValueError(
                "The session file has no valid graph settings."
            )

        required_graph_settings = (
            "x_min",
            "x_max",
            "point_count",
        )

        for key in required_graph_settings:
            if key not in graph_settings:
                raise ValueError(
                    f"The graph setting '{key}' is missing."
                )

    def _apply_session_data(
        self,
        session_data: dict[str, Any],
    ) -> None:
        """Apply validated session data to the graph window."""
        graph_settings = session_data["graph_settings"]

        # Validate settings using temporary conversions before
        # replacing the current workspace.
        x_min = float(graph_settings["x_min"])
        x_max = float(graph_settings["x_max"])
        point_count = int(graph_settings["point_count"])

        if x_min >= x_max:
            raise ValueError(
                "The saved x minimum must be smaller than x maximum."
            )

        if not MIN_POINT_COUNT <= point_count <= MAX_POINT_COUNT:
            raise ValueError(
                "The saved sample count is outside the allowed range."
            )

        loaded_expressions: list[GraphExpression] = []

        for item in session_data["expressions"]:
            expression = item["expression"].strip()

            if not expression:
                raise ValueError(
                    "The session contains an empty expression."
                )

            # Validate saved expressions quietly before applying them.
            if not self._expression_has_valid_sample(expression):
                raise ValueError(
                    f"Could not evaluate saved expression: {expression}"
                )

            color = item.get("color")

            if color is not None and not isinstance(color, str):
                raise ValueError(
                    "A saved function color is invalid."
                )

            line_width = float(item.get("line_width", 2.0))

            if not 0.5 <= line_width <= 10:
                raise ValueError(
                    "A saved line width is outside the allowed range."
                )

            line_style = str(item.get("line_style", "-"))

            if line_style not in {"-", "--", ":", "-."}:
                line_style = "-"

            custom_label = item.get("custom_label", "")

            if not isinstance(custom_label, str):
                raise ValueError(
                    "A saved custom label is invalid."
                )

            loaded_expressions.append(
                GraphExpression(
                    expression=expression,
                    visible=item["visible"],
                    color=color or None,
                    line_width=line_width,
                    line_style=line_style,
                    custom_label=custom_label,
                )
            )

        interface_settings = session_data.get(
            "interface_settings",
            {},
        )
        calculus_settings = session_data.get(
            "calculus_settings",
            {},
        )

        self.expressions = loaded_expressions

        saved_parameters = session_data.get(
            "parameters",
            {},
        )

        if not isinstance(saved_parameters, dict):
            raise ValueError(
                "The saved parameter data is invalid."
            )

        self.parameter_values.clear()
        self._rebuild_parameter_sliders()

        for name, raw_value in saved_parameters.items():
            if name not in self.parameter_values:
                continue

            value = float(raw_value)

            if not math.isfinite(value):
                raise ValueError(
                    f"The saved value for parameter '{name}' is invalid."
                )

            self.parameter_values[name].set(value)

        self.x_min_variable.set(str(x_min))
        self.x_max_variable.set(str(x_max))
        self.point_count_variable.set(str(point_count))

        live_update = interface_settings.get(
            "live_update",
            True,
        )
        self.live_update_enabled.set(bool(live_update))

        saved_theme = str(
            interface_settings.get(
                "graph_theme",
                "Light",
            )
        )

        if saved_theme not in GRAPH_THEMES:
            saved_theme = "Light"

        self.graph_theme_variable.set(saved_theme)
        self.show_grid_variable.set(
            bool(interface_settings.get("show_grid", True))
        )
        self.show_axes_variable.set(
            bool(interface_settings.get("show_axes", True))
        )
        self.show_legend_variable.set(
            bool(interface_settings.get("show_legend", True))
        )

        saved_animation_delay = int(
            interface_settings.get(
                "animation_delay_ms",
                DEFAULT_ANIMATION_DELAY_MS,
            )
        )
        self.animation_delay_variable.set(
            max(
                MIN_ANIMATION_DELAY_MS,
                min(
                    MAX_ANIMATION_DELAY_MS,
                    saved_animation_delay,
                ),
            )
        )

        saved_animation_mode = str(
            interface_settings.get(
                "animation_mode",
                "Ping-pong",
            )
        )
        if saved_animation_mode not in {
            "Ping-pong",
            "Loop",
            "One-shot",
        }:
            saved_animation_mode = "Ping-pong"
        self.animation_mode_variable.set(saved_animation_mode)

        saved_animation_parameter = str(
            interface_settings.get(
                "animation_parameter",
                "",
            )
        )
        if saved_animation_parameter in self.parameter_values:
            self.animation_parameter_variable.set(
                saved_animation_parameter
            )

        self.derivative_x_variable.set(
            str(calculus_settings.get("derivative_x", "0"))
        )
        self.integral_a_variable.set(
            str(
                calculus_settings.get(
                    "integral_a",
                    DEFAULT_INTEGRAL_A,
                )
            )
        )
        self.integral_b_variable.set(
            str(
                calculus_settings.get(
                    "integral_b",
                    DEFAULT_INTEGRAL_B,
                )
            )
        )
        self.arc_length_a_variable.set(
            str(
                calculus_settings.get(
                    "arc_length_a",
                    DEFAULT_INTEGRAL_A,
                )
            )
        )
        self.arc_length_b_variable.set(
            str(
                calculus_settings.get(
                    "arc_length_b",
                    DEFAULT_INTEGRAL_B,
                )
            )
        )

        saved_method = str(
            calculus_settings.get(
                "riemann_method",
                "Midpoint",
            )
        )

        if saved_method not in {
            "Left",
            "Right",
            "Midpoint",
            "Trapezoid",
        }:
            saved_method = "Midpoint"

        self.riemann_method_variable.set(saved_method)

        saved_intervals = int(
            calculus_settings.get(
                "riemann_intervals",
                DEFAULT_RIEMANN_INTERVALS,
            )
        )

        saved_intervals = max(
            MIN_RIEMANN_INTERVALS,
            min(
                MAX_RIEMANN_INTERVALS,
                saved_intervals,
            ),
        )

        self.riemann_intervals_variable.set(
            saved_intervals
        )

        self.expression_variable.set("")
        self._refresh_expression_list()
        self._rebuild_parameter_sliders()
        self.plot_all_expressions()
        self.apply_graph_appearance()

    # --------------------------------------------------
    # TABLE OF VALUES
    # --------------------------------------------------

    def open_values_table(self) -> None:
        """Open a table for the selected visible function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before opening its table of values.",
                parent=self.window,
            )
            return

        expression = self.expressions[selected_index].expression

        ValuesTableWindow(
            parent=self.window,
            expression=expression,
        )

    # --------------------------------------------------
    # LIVE PREVIEW
    # --------------------------------------------------

    def _schedule_live_update(
        self,
        *_args: object,
    ) -> None:
        """Schedule a live preview after typing stops."""
        if not self.live_update_enabled.get():
            return

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(self.live_update_job)
            except (ValueError, tk.TclError):
                pass

        self.live_update_job = self.window.after(
            LIVE_UPDATE_DELAY_MS,
            self._perform_live_update,
        )

    def _perform_live_update(self) -> None:
        """Draw the temporary expression preview."""
        self.live_update_job = None

        expression = self.expression_variable.get().strip()

        if not expression:
            self.plot_all_expressions()
            return

        if not self._expression_has_valid_sample(expression):
            return

        self._plot_with_preview(expression)

    def _handle_live_update_toggle(self) -> None:
        """Enable or disable live preview."""
        if not self.live_update_enabled.get():
            if self.live_update_job is not None:
                try:
                    self.window.after_cancel(self.live_update_job)
                except (ValueError, tk.TclError):
                    pass

                self.live_update_job = None

            self.plot_all_expressions()
            return

        self._schedule_live_update()

    def _plot_with_preview(
        self,
        preview_expression: str,
    ) -> None:
        """Plot stored functions and a temporary dashed preview."""
        settings = self._read_graph_settings(
            show_errors=False,
        )

        if settings is None:
            return

        x_min, x_max, point_count = settings
        x_values = self._generate_x_values(
            x_min,
            x_max,
            point_count,
        )

        self._clear_point_marker(redraw=False)
        self._clear_analysis_artists(redraw=False)
        self.clear_calculus_artists(redraw=False)
        self.clear_extrema_markers(redraw=False)
        self.clear_inflection_markers(redraw=False)
        self.plotted_series.clear()

        self.axes.clear()
        self._reset_axes_content()

        plotted_count = 0

        for graph_expression in self.expressions:
            if not graph_expression.visible:
                continue

            y_values, valid_count = self._evaluate_expression_series(
                graph_expression.expression,
                x_values,
            )

            if valid_count == 0:
                continue

            self.axes.plot(
                x_values,
                y_values,
                label=graph_expression.legend_label(),
                color=graph_expression.color,
                linewidth=graph_expression.line_width,
                linestyle=graph_expression.line_style,
            )

            self.plotted_series.append(
                (
                    graph_expression,
                    x_values.copy(),
                    y_values.copy(),
                )
            )

            plotted_count += 1

        preview_y_values, preview_valid_count = (
            self._evaluate_expression_series(
                preview_expression,
                x_values,
            )
        )

        if preview_valid_count > 0:
            self.axes.plot(
                x_values,
                preview_y_values,
                linestyle="--",
                linewidth=2,
                label=f"Preview: y = {preview_expression}",
            )
            plotted_count += 1

        self.axes.set_xlim(x_min, x_max)

        if plotted_count:
            self._refresh_legend()
            self.axes.relim()
            self.axes.autoscale_view(
                scalex=False,
                scaley=True,
            )

        self.figure.tight_layout()
        self.canvas.draw_idle()

        self.status_variable.set(
            f"Live preview: y = {preview_expression}"
        )

    # --------------------------------------------------
    # EXPRESSION MANAGEMENT
    # --------------------------------------------------

    def add_expression(self) -> None:
        """Add a graph expression."""
        expression = self.expression_variable.get().strip()

        if not expression:
            messagebox.showwarning(
                "Missing Expression",
                "Enter an expression containing x.",
                parent=self.window,
            )
            return

        self._ensure_parameters_for_expression(expression)

        if not self._validate_expression(expression):
            return

        for stored in self.expressions:
            if stored.expression == expression:
                stored.visible = True
                self.expression_variable.set("")
                self._refresh_expression_list()
                self._rebuild_parameter_sliders()
                self.plot_all_expressions()
                return

        self.expressions.append(
            GraphExpression(expression),
        )

        self.expression_variable.set("")
        self._refresh_expression_list()
        self._rebuild_parameter_sliders()
        self.plot_all_expressions()

    def update_selected_expression(self) -> None:
        """Replace the selected expression."""
        selected_index = self._get_selected_expression_index()

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

        self._ensure_parameters_for_expression(expression)

        if not self._validate_expression(expression):
            return

        self.expressions[selected_index].expression = expression
        self.expressions[selected_index].visible = True

        self.expression_variable.set("")
        self._refresh_expression_list(selected_index)
        self._rebuild_parameter_sliders()
        self.plot_all_expressions()

    def toggle_selected_expression(self) -> None:
        """Show or hide the selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            return

        selected = self.expressions[selected_index]
        selected.visible = not selected.visible

        self._refresh_expression_list(selected_index)
        self.plot_all_expressions()

    def remove_selected_expression(self) -> None:
        """Remove the selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            return

        del self.expressions[selected_index]

        self._refresh_expression_list()
        self._rebuild_parameter_sliders()
        self.plot_all_expressions()

    def clear_all_expressions(self) -> None:
        """Remove all functions and markers."""
        self.pause_parameter_animation()
        self.expressions.clear()
        self.plotted_series.clear()

        self.expression_listbox.delete(0, tk.END)
        self._rebuild_parameter_sliders()

        self._clear_point_marker(redraw=False)
        self.clear_analysis_markers(redraw=False)
        self.clear_calculus_artists(redraw=False)
        self.clear_extrema_markers(redraw=False)
        self.clear_inflection_markers(redraw=False)

        self.axes.clear()
        self._reset_axes_content()
        self.canvas.draw_idle()

        self.coordinate_variable.set("x: —    y: —")
        self.status_variable.set(
            "All graph expressions were cleared."
        )

    def _refresh_expression_list(
        self,
        selected_index: int | None = None,
    ) -> None:
        """Refresh the function list."""
        self.expression_listbox.delete(0, tk.END)

        for graph_expression in self.expressions:
            symbol = "✓" if graph_expression.visible else "○"

            label = (
                graph_expression.custom_label.strip()
                or f"y = {graph_expression.expression}"
            )

            self.expression_listbox.insert(
                tk.END,
                f"{symbol}  {label}",
            )

        if (
            selected_index is not None
            and selected_index < len(self.expressions)
        ):
            self.expression_listbox.selection_set(selected_index)
            self.expression_listbox.activate(selected_index)

    def _get_selected_expression_index(self) -> int | None:
        """Return the selected function index."""
        selection = self.expression_listbox.curselection()

        if not selection:
            return None

        return int(selection[0])

    # --------------------------------------------------
    # GRAPHING
    # --------------------------------------------------

    def plot_all_expressions(self) -> None:
        """Plot all visible stored expressions."""
        settings = self._read_graph_settings()

        if settings is None:
            return

        x_min, x_max, point_count = settings

        self._clear_point_marker(redraw=False)
        self.clear_analysis_markers(redraw=False)
        self.clear_calculus_artists(redraw=False)
        self.clear_extrema_markers(redraw=False)
        self.clear_inflection_markers(redraw=False)
        self.plotted_series.clear()

        self.axes.clear()
        self._reset_axes_content()

        x_values = self._generate_x_values(
            x_min,
            x_max,
            point_count,
        )

        plotted_count = 0
        total_valid_points = 0

        for graph_expression in self.expressions:
            if not graph_expression.visible:
                continue

            y_values, valid_count = self._evaluate_expression_series(
                graph_expression.expression,
                x_values,
            )

            if valid_count == 0:
                continue

            self.axes.plot(
                x_values,
                y_values,
                label=graph_expression.legend_label(),
                color=graph_expression.color,
                linewidth=graph_expression.line_width,
                linestyle=graph_expression.line_style,
            )

            self.plotted_series.append(
                (
                    graph_expression,
                    x_values.copy(),
                    y_values.copy(),
                )
            )

            plotted_count += 1
            total_valid_points += valid_count

        self.axes.set_xlim(x_min, x_max)

        if plotted_count:
            self._refresh_legend()
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
        """Evaluate a function across sampled x-values."""
        y_values: list[float] = []
        valid_count = 0
        previous_y: float | None = None

        for x_value in x_values:
            try:
                y_value = self._evaluate_parameterized_expression(
                    expression,
                    x_value,
                )

                if not math.isfinite(y_value):
                    raise ValueError("Non-finite graph value.")

                if abs(y_value) > MAX_ABSOLUTE_Y:
                    raise ValueError("Graph value exceeds limit.")

                if previous_y is not None:
                    jump = abs(y_value - previous_y)

                    if jump > MAX_ABSOLUTE_Y / 10:
                        y_values.append(float("nan"))
                        previous_y = None
                        continue

                y_values.append(y_value)
                valid_count += 1
                previous_y = y_value

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                y_values.append(float("nan"))
                previous_y = None

        return y_values, valid_count

    # --------------------------------------------------
    # DERIVATIVE AND TANGENT LINE
    # --------------------------------------------------

    def show_derivative_and_tangent(self) -> None:
        """Calculate a numerical derivative and draw its tangent line."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before calculating its derivative.",
                parent=self.window,
            )
            return

        try:
            x_value = float(self.derivative_x_variable.get())
        except ValueError:
            messagebox.showerror(
                "Invalid x Value",
                "The derivative x value must be a valid number.",
                parent=self.window,
            )
            return

        expression = self.expressions[selected_index].expression

        try:
            y_value = self._evaluate_parameterized_expression(
                expression,
                x_value,
            )
            slope = self._numerical_derivative(
                expression,
                x_value,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            messagebox.showerror(
                "Derivative Error",
                f"Could not calculate the derivative:\n\n{error}",
                parent=self.window,
            )
            return

        if not math.isfinite(y_value) or not math.isfinite(slope):
            messagebox.showerror(
                "Derivative Error",
                "The function or derivative is undefined at that x value.",
                parent=self.window,
            )
            return

        self.clear_calculus_artists(redraw=False)

        x_min, x_max = self.axes.get_xlim()
        tangent_x = [x_min, x_max]
        tangent_y = [
            y_value + slope * (x_coordinate - x_value)
            for x_coordinate in tangent_x
        ]

        tangent_line = self.axes.plot(
            tangent_x,
            tangent_y,
            linestyle="--",
            linewidth=2,
            label=(
                f"Tangent to y = {expression} "
                f"at x = {x_value:.6g}"
            ),
        )[0]

        tangent_point = self.axes.scatter(
            [x_value],
            [y_value],
            marker="o",
            s=70,
            zorder=12,
            label="_nolegend_",
        )

        tangent_annotation = self.axes.annotate(
            (
                f"x = {x_value:.8g}\n"
                f"f(x) = {y_value:.8g}\n"
                f"f'(x) ≈ {slope:.8g}"
            ),
            xy=(x_value, y_value),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": "white",
                "alpha": 0.9,
            },
            arrowprops={
                "arrowstyle": "->",
            },
            zorder=13,
        )

        self.calculus_artists.extend(
            [
                tangent_line,
                tangent_point,
                tangent_annotation,
            ]
        )

        self._refresh_legend()
        self.canvas.draw_idle()

        self.coordinate_variable.set(
            f"x: {x_value:.8g}    y: {y_value:.8g}"
        )
        self.status_variable.set(
            f"Derivative of y = {expression} at x = "
            f"{x_value:.8g} is approximately {slope:.8g}."
        )

    def _numerical_derivative(
        self,
        expression: str,
        x_value: float,
    ) -> float:
        """Estimate f'(x) with a central difference formula."""
        step = DERIVATIVE_STEP * max(1.0, abs(x_value))

        left_value = self._evaluate_parameterized_expression(
            expression,
            x_value - step,
        )
        right_value = self._evaluate_parameterized_expression(
            expression,
            x_value + step,
        )

        return (right_value - left_value) / (2 * step)

    def clear_calculus_artists(
        self,
        redraw: bool = True,
    ) -> None:
        """Safely remove tangent lines and calculus annotations."""
        for artist in self.calculus_artists:
            try:
                artist.remove()
            except (
                ValueError,
                NotImplementedError,
            ):
                pass

        self.calculus_artists.clear()

        if redraw:
            self.canvas.draw_idle()

    def show_integral_area(self) -> None:
        """
        Numerically integrate the selected function and shade its area.

        Simpson's rule is used when possible. Undefined points inside
        the interval cause the calculation to stop with an error.
        """
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before calculating an integral.",
                parent=self.window,
            )
            return

        try:
            lower_bound = float(self.integral_a_variable.get())
            upper_bound = float(self.integral_b_variable.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Integration Bounds",
                "The integral bounds must both be valid numbers.",
                parent=self.window,
            )
            return

        if lower_bound == upper_bound:
            messagebox.showinfo(
                "Zero-Width Interval",
                "The integral is 0 because both bounds are equal.",
                parent=self.window,
            )
            return

        # Preserve orientation so reversing the bounds changes the sign.
        integration_sign = 1.0

        if lower_bound > upper_bound:
            lower_bound, upper_bound = upper_bound, lower_bound
            integration_sign = -1.0

        expression = self.expressions[selected_index].expression

        try:
            integral_value = integration_sign * self._simpson_integral(
                expression,
                lower_bound,
                upper_bound,
                INTEGRATION_INTERVALS,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            messagebox.showerror(
                "Integration Error",
                f"Could not calculate the integral:\n\n{error}",
                parent=self.window,
            )
            return

        sample_count = 600
        x_values = self._generate_x_values(
            lower_bound,
            upper_bound,
            sample_count,
        )

        y_values: list[float] = []

        try:
            for x_value in x_values:
                y_value = self._evaluate_parameterized_expression(
                    expression,
                    x_value,
                )

                if not math.isfinite(y_value):
                    raise ValueError(
                        "The function is undefined inside the interval."
                    )

                y_values.append(y_value)

        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            messagebox.showerror(
                "Integration Error",
                f"Could not shade the integration interval:\n\n{error}",
                parent=self.window,
            )
            return

        self.clear_calculus_artists(redraw=False)

        area_artist = self.axes.fill_between(
            x_values,
            y_values,
            0,
            alpha=0.3,
            label=(
                f"Integral of y = {expression} "
                f"from {lower_bound:.6g} to {upper_bound:.6g}"
            ),
        )

        lower_line = self.axes.axvline(
            lower_bound,
            linestyle=":",
            linewidth=1.2,
        )

        upper_line = self.axes.axvline(
            upper_bound,
            linestyle=":",
            linewidth=1.2,
        )

        midpoint_x = (lower_bound + upper_bound) / 2

        try:
            midpoint_y = self._evaluate_parameterized_expression(
                expression,
                midpoint_x,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            midpoint_y = 0.0

        annotation = self.axes.annotate(
            f"Integral ≈ {integral_value:.10g}",
            xy=(midpoint_x, midpoint_y),
            xytext=(12, 18),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": "white",
                "alpha": 0.9,
            },
            arrowprops={
                "arrowstyle": "->",
            },
            zorder=13,
        )

        self.calculus_artists.extend(
            [
                area_artist,
                lower_line,
                upper_line,
                annotation,
            ]
        )

        self._refresh_legend()
        self.canvas.draw_idle()

        original_a = float(self.integral_a_variable.get())
        original_b = float(self.integral_b_variable.get())

        self.status_variable.set(
            f"Integral of y = {expression} from "
            f"{original_a:.8g} to {original_b:.8g} "
            f"is approximately {integral_value:.10g}."
        )

    def _simpson_integral(
        self,
        expression: str,
        lower_bound: float,
        upper_bound: float,
        interval_count: int,
    ) -> float:
        """
        Approximate a definite integral using composite Simpson's rule.

        Simpson's rule requires an even number of intervals.
        """
        if interval_count < 2:
            raise ValueError(
                "At least two integration intervals are required."
            )

        if interval_count % 2 != 0:
            interval_count += 1

        width = (
            upper_bound - lower_bound
        ) / interval_count

        first_value = self._evaluate_parameterized_expression(
            expression,
            lower_bound,
        )
        final_value = self._evaluate_parameterized_expression(
            expression,
            upper_bound,
        )

        if (
            not math.isfinite(first_value)
            or not math.isfinite(final_value)
        ):
            raise ValueError(
                "The function is undefined at an integration bound."
            )

        weighted_sum = first_value + final_value

        for index in range(1, interval_count):
            x_value = lower_bound + index * width
            y_value = self._evaluate_parameterized_expression(
                expression,
                x_value,
            )

            if not math.isfinite(y_value):
                raise ValueError(
                    "The function is undefined inside the interval."
                )

            coefficient = 4 if index % 2 == 1 else 2
            weighted_sum += coefficient * y_value

        return weighted_sum * width / 3

    def show_normal_line(self) -> None:
        """Calculate and draw the normal line at the selected x value."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before drawing its normal line.",
                parent=self.window,
            )
            return

        try:
            x_value = float(self.derivative_x_variable.get())
        except ValueError:
            messagebox.showerror(
                "Invalid x Value",
                "The normal-line x value must be a valid number.",
                parent=self.window,
            )
            return

        expression = self.expressions[selected_index].expression

        try:
            y_value = self._evaluate_parameterized_expression(
                expression,
                x_value,
            )
            tangent_slope = self._numerical_derivative(
                expression,
                x_value,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            messagebox.showerror(
                "Normal Line Error",
                f"Could not calculate the normal line:\n\n{error}",
                parent=self.window,
            )
            return

        if not math.isfinite(y_value) or not math.isfinite(tangent_slope):
            messagebox.showerror(
                "Normal Line Error",
                "The function or derivative is undefined at that x value.",
                parent=self.window,
            )
            return

        self.clear_calculus_artists(redraw=False)

        x_min, x_max = self.axes.get_xlim()

        if abs(tangent_slope) < 1e-12:
            # Horizontal tangent means a vertical normal line.
            normal_line = self.axes.axvline(
                x_value,
                linestyle="--",
                linewidth=2,
                label=(
                    f"Normal to y = {expression} "
                    f"at x = {x_value:.6g}"
                ),
            )

            equation_text = f"x = {x_value:.8g}"
            normal_slope_text = "undefined (vertical)"
        else:
            normal_slope = -1 / tangent_slope

            normal_x = [x_min, x_max]
            normal_y = [
                y_value + normal_slope * (x_coordinate - x_value)
                for x_coordinate in normal_x
            ]

            normal_line = self.axes.plot(
                normal_x,
                normal_y,
                linestyle="--",
                linewidth=2,
                label=(
                    f"Normal to y = {expression} "
                    f"at x = {x_value:.6g}"
                ),
            )[0]

            intercept = y_value - normal_slope * x_value
            equation_text = (
                f"y = {normal_slope:.8g}x "
                f"{intercept:+.8g}"
            )
            normal_slope_text = f"{normal_slope:.8g}"

        normal_point = self.axes.scatter(
            [x_value],
            [y_value],
            marker="o",
            s=70,
            zorder=12,
            label="_nolegend_",
        )

        annotation = self.axes.annotate(
            (
                f"x = {x_value:.8g}\n"
                f"f(x) = {y_value:.8g}\n"
                f"normal slope = {normal_slope_text}\n"
                f"{equation_text}"
            ),
            xy=(x_value, y_value),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": "white",
                "alpha": 0.9,
            },
            arrowprops={
                "arrowstyle": "->",
            },
            zorder=13,
        )

        self.calculus_artists.extend(
            [
                normal_line,
                normal_point,
                annotation,
            ]
        )

        self._refresh_legend()
        self.canvas.draw_idle()

        self.coordinate_variable.set(
            f"x: {x_value:.8g}    y: {y_value:.8g}"
        )
        self.status_variable.set(
            f"Normal line for y = {expression} at x = "
            f"{x_value:.8g}: {equation_text}"
        )

    def show_arc_length(self) -> None:
        """Calculate and highlight the arc length of a selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before calculating arc length.",
                parent=self.window,
            )
            return

        try:
            original_a = float(self.arc_length_a_variable.get())
            original_b = float(self.arc_length_b_variable.get())
        except ValueError:
            messagebox.showerror(
                "Invalid Arc Bounds",
                "The arc-length bounds must both be valid numbers.",
                parent=self.window,
            )
            return

        if original_a == original_b:
            messagebox.showinfo(
                "Zero-Length Interval",
                "The arc length is 0 because both bounds are equal.",
                parent=self.window,
            )
            return

        lower_bound = min(original_a, original_b)
        upper_bound = max(original_a, original_b)
        expression = self.expressions[selected_index].expression

        try:
            arc_length = self._calculate_arc_length(
                expression,
                lower_bound,
                upper_bound,
                ARC_LENGTH_INTERVALS,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            messagebox.showerror(
                "Arc Length Error",
                f"Could not calculate arc length:\n\n{error}",
                parent=self.window,
            )
            return

        sample_count = 600
        x_values = self._generate_x_values(
            lower_bound,
            upper_bound,
            sample_count,
        )

        y_values: list[float] = []

        try:
            for x_value in x_values:
                y_value = self._evaluate_parameterized_expression(
                    expression,
                    x_value,
                )

                if not math.isfinite(y_value):
                    raise ValueError(
                        "The function is undefined inside the interval."
                    )

                y_values.append(y_value)

        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            messagebox.showerror(
                "Arc Length Error",
                f"Could not highlight the curve segment:\n\n{error}",
                parent=self.window,
            )
            return

        self.clear_calculus_artists(redraw=False)

        highlighted_curve = self.axes.plot(
            x_values,
            y_values,
            linewidth=4,
            label=(
                f"Arc of y = {expression} "
                f"from {lower_bound:.6g} to {upper_bound:.6g}"
            ),
        )[0]

        lower_point = self.axes.scatter(
            [x_values[0]],
            [y_values[0]],
            marker="o",
            s=55,
            zorder=12,
            label="_nolegend_",
        )

        upper_point = self.axes.scatter(
            [x_values[-1]],
            [y_values[-1]],
            marker="o",
            s=55,
            zorder=12,
            label="_nolegend_",
        )

        midpoint_index = len(x_values) // 2
        annotation = self.axes.annotate(
            f"Arc length ≈ {arc_length:.10g}",
            xy=(
                x_values[midpoint_index],
                y_values[midpoint_index],
            ),
            xytext=(12, 18),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": "white",
                "alpha": 0.9,
            },
            arrowprops={
                "arrowstyle": "->",
            },
            zorder=13,
        )

        self.calculus_artists.extend(
            [
                highlighted_curve,
                lower_point,
                upper_point,
                annotation,
            ]
        )

        self._refresh_legend()
        self.canvas.draw_idle()

        self.status_variable.set(
            f"Arc length of y = {expression} from "
            f"{original_a:.8g} to {original_b:.8g} "
            f"is approximately {arc_length:.10g}."
        )

    def _calculate_arc_length(
        self,
        expression: str,
        lower_bound: float,
        upper_bound: float,
        interval_count: int,
    ) -> float:
        """Approximate arc length using Simpson's rule."""
        if interval_count < 2:
            raise ValueError(
                "At least two arc-length intervals are required."
            )

        if interval_count % 2 != 0:
            interval_count += 1

        width = (
            upper_bound - lower_bound
        ) / interval_count

        def arc_integrand(x_value: float) -> float:
            derivative = self._numerical_derivative(
                expression,
                x_value,
            )

            if not math.isfinite(derivative):
                raise ValueError(
                    "The derivative is undefined inside the interval."
                )

            return math.sqrt(
                1 + derivative * derivative
            )

        first_value = arc_integrand(lower_bound)
        final_value = arc_integrand(upper_bound)

        weighted_sum = first_value + final_value

        for index in range(1, interval_count):
            x_value = lower_bound + index * width
            coefficient = 4 if index % 2 == 1 else 2

            weighted_sum += (
                coefficient * arc_integrand(x_value)
            )

        return weighted_sum * width / 3

    # --------------------------------------------------
    # RIEMANN SUM VISUALIZER
    # --------------------------------------------------

    def _schedule_riemann_redraw(
        self,
        _value: str,
    ) -> None:
        """
        Redraw the Riemann visualization when the slider moves.

        The redraw only occurs when a function is selected and the
        integration bounds are valid.
        """
        if not hasattr(self, "canvas"):
            return

        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            return

        try:
            float(self.integral_a_variable.get())
            float(self.integral_b_variable.get())
        except ValueError:
            return

        self.show_riemann_sum(
            show_errors=False,
        )

    def show_riemann_sum(
        self,
        *,
        show_errors: bool = True,
    ) -> None:
        """Draw and calculate a Riemann-sum approximation."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            if show_errors:
                messagebox.showinfo(
                    "No Function Selected",
                    "Select a function before showing a Riemann sum.",
                    parent=self.window,
                )
            return

        try:
            original_a = float(self.integral_a_variable.get())
            original_b = float(self.integral_b_variable.get())
            interval_count = int(
                self.riemann_intervals_variable.get()
            )
        except (ValueError, tk.TclError):
            if show_errors:
                messagebox.showerror(
                    "Invalid Riemann Settings",
                    "The bounds and interval count must be valid numbers.",
                    parent=self.window,
                )
            return

        if original_a == original_b:
            if show_errors:
                messagebox.showinfo(
                    "Zero-Width Interval",
                    "The Riemann sum is 0 because both bounds are equal.",
                    parent=self.window,
                )
            return

        if not (
            MIN_RIEMANN_INTERVALS
            <= interval_count
            <= MAX_RIEMANN_INTERVALS
        ):
            if show_errors:
                messagebox.showerror(
                    "Invalid Interval Count",
                    f"Intervals must be between "
                    f"{MIN_RIEMANN_INTERVALS} and "
                    f"{MAX_RIEMANN_INTERVALS}.",
                    parent=self.window,
                )
            return

        method = self.riemann_method_variable.get()
        expression = self.expressions[selected_index].expression

        lower_bound = min(original_a, original_b)
        upper_bound = max(original_a, original_b)
        orientation = 1.0 if original_a < original_b else -1.0

        width = (
            upper_bound - lower_bound
        ) / interval_count

        self.clear_calculus_artists(redraw=False)

        try:
            approximation = self._draw_riemann_geometry(
                expression=expression,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                interval_count=interval_count,
                method=method,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            if show_errors:
                messagebox.showerror(
                    "Riemann Sum Error",
                    f"Could not calculate the Riemann sum:\n\n{error}",
                    parent=self.window,
                )
            return

        approximation *= orientation

        exact_integral: float | None

        try:
            exact_integral = orientation * self._simpson_integral(
                expression,
                lower_bound,
                upper_bound,
                max(
                    INTEGRATION_INTERVALS,
                    interval_count * 2,
                ),
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            exact_integral = None

        if exact_integral is None:
            annotation_text = (
                f"{method} sum\n"
                f"n = {interval_count}\n"
                f"Approx. = {approximation:.10g}"
            )
            status_text = (
                f"{method} Riemann sum for y = {expression}: "
                f"{approximation:.10g}"
            )
        else:
            error_value = approximation - exact_integral

            annotation_text = (
                f"{method} sum\n"
                f"n = {interval_count}\n"
                f"Approx. = {approximation:.10g}\n"
                f"Integral ≈ {exact_integral:.10g}\n"
                f"Error ≈ {error_value:.6g}"
            )

            status_text = (
                f"{method} Riemann sum for y = {expression}: "
                f"{approximation:.10g}; "
                f"integral ≈ {exact_integral:.10g}; "
                f"error ≈ {error_value:.6g}."
            )

        midpoint_x = (
            lower_bound + upper_bound
        ) / 2

        try:
            midpoint_y = self._evaluate_parameterized_expression(
                expression,
                midpoint_x,
            )
        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            midpoint_y = 0.0

        annotation = self.axes.annotate(
            annotation_text,
            xy=(midpoint_x, midpoint_y),
            xytext=(12, 18),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": "white",
                "alpha": 0.92,
            },
            arrowprops={
                "arrowstyle": "->",
            },
            zorder=14,
        )

        lower_line = self.axes.axvline(
            lower_bound,
            linestyle=":",
            linewidth=1.2,
        )

        upper_line = self.axes.axvline(
            upper_bound,
            linestyle=":",
            linewidth=1.2,
        )

        self.calculus_artists.extend(
            [
                lower_line,
                upper_line,
                annotation,
            ]
        )

        self._refresh_legend()
        self.canvas.draw_idle()

        self.status_variable.set(status_text)

    def _draw_riemann_geometry(
        self,
        *,
        expression: str,
        lower_bound: float,
        upper_bound: float,
        interval_count: int,
        method: str,
    ) -> float:
        """
        Draw the chosen Riemann geometry and return its approximation.
        """
        width = (
            upper_bound - lower_bound
        ) / interval_count

        approximation = 0.0

        if method == "Trapezoid":
            for index in range(interval_count):
                x_left = lower_bound + index * width
                x_right = x_left + width

                y_left = self._evaluate_parameterized_expression(
                    expression,
                    x_left,
                )
                y_right = self._evaluate_parameterized_expression(
                    expression,
                    x_right,
                )

                if (
                    not math.isfinite(y_left)
                    or not math.isfinite(y_right)
                ):
                    raise ValueError(
                        "The function is undefined inside the interval."
                    )

                polygon = self.axes.fill(
                    [
                        x_left,
                        x_left,
                        x_right,
                        x_right,
                    ],
                    [
                        0,
                        y_left,
                        y_right,
                        0,
                    ],
                    alpha=0.25,
                    edgecolor="black",
                    linewidth=0.7,
                    label=(
                        f"{method} Riemann sum"
                        if index == 0
                        else "_nolegend_"
                    ),
                )[0]

                self.calculus_artists.append(polygon)

                approximation += (
                    y_left + y_right
                ) * width / 2

            return approximation

        for index in range(interval_count):
            x_left = lower_bound + index * width

            if method == "Left":
                sample_x = x_left
            elif method == "Right":
                sample_x = x_left + width
            else:
                sample_x = x_left + width / 2

            sample_y = self._evaluate_parameterized_expression(
                expression,
                sample_x,
            )

            if not math.isfinite(sample_y):
                raise ValueError(
                    "The function is undefined inside the interval."
                )

            rectangle = self.axes.bar(
                x_left,
                sample_y,
                width=width,
                align="edge",
                alpha=0.28,
                edgecolor="black",
                linewidth=0.7,
                label=(
                    f"{method} Riemann sum"
                    if index == 0
                    else "_nolegend_"
                ),
            )

            self.calculus_artists.extend(
                list(rectangle)
            )

            approximation += sample_y * width

        return approximation

    # --------------------------------------------------
    # LOCAL MINIMA AND MAXIMA
    # --------------------------------------------------

    def find_local_extrema(self) -> None:
        """Detect local minima and maxima for the selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before searching for local extrema.",
                parent=self.window,
            )
            return

        settings = self._read_graph_settings()

        if settings is None:
            return

        x_min, x_max, point_count = settings
        expression = self.expressions[selected_index].expression

        x_values = self._generate_x_values(
            x_min,
            x_max,
            point_count,
        )

        derivatives: list[float | None] = []

        for x_value in x_values:
            try:
                derivative = self._numerical_derivative(
                    expression,
                    x_value,
                )

                if not math.isfinite(derivative):
                    derivatives.append(None)
                else:
                    derivatives.append(derivative)

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                derivatives.append(None)

        detected: list[SpecialPoint] = []

        for index in range(len(x_values) - 1):
            derivative1 = derivatives[index]
            derivative2 = derivatives[index + 1]

            if derivative1 is None or derivative2 is None:
                continue

            if (
                abs(derivative1) <= EXTREMA_DERIVATIVE_TOLERANCE
                and abs(derivative2) <= EXTREMA_DERIVATIVE_TOLERANCE
            ):
                continue

            extremum_type: str | None = None

            if derivative1 > 0 and derivative2 < 0:
                extremum_type = "local maximum"
            elif derivative1 < 0 and derivative2 > 0:
                extremum_type = "local minimum"

            if extremum_type is None:
                continue

            extremum_x = self._linear_zero_interpolation(
                x_values[index],
                derivative1,
                x_values[index + 1],
                derivative2,
            )

            try:
                extremum_y = self._evaluate_parameterized_expression(
                    expression,
                    extremum_x,
                )
            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                continue

            if not math.isfinite(extremum_y):
                continue

            detected.append(
                SpecialPoint(
                    point_type=extremum_type,
                    x=extremum_x,
                    y=extremum_y,
                    first_expression=expression,
                )
            )

        self.extrema_points = self._deduplicate_extrema(
            detected
        )

        self._refresh_extrema_list()
        self._draw_extrema_markers()

        minimum_count = sum(
            point.point_type == "local minimum"
            for point in self.extrema_points
        )
        maximum_count = sum(
            point.point_type == "local maximum"
            for point in self.extrema_points
        )

        self.status_variable.set(
            f"Found {minimum_count} local minimum/minima and "
            f"{maximum_count} local maximum/maxima for "
            f"y = {expression}."
        )

    def _deduplicate_extrema(
        self,
        points: list[SpecialPoint],
    ) -> list[SpecialPoint]:
        """Remove near-duplicate extrema."""
        unique: list[SpecialPoint] = []

        for point in sorted(points, key=lambda item: item.x):
            duplicate = any(
                point.point_type == existing.point_type
                and math.isclose(
                    point.x,
                    existing.x,
                    abs_tol=EXTREMA_DUPLICATE_TOLERANCE,
                )
                and math.isclose(
                    point.y,
                    existing.y,
                    abs_tol=EXTREMA_DUPLICATE_TOLERANCE,
                )
                for existing in unique
            )

            if not duplicate:
                unique.append(point)

        return unique

    def _refresh_extrema_list(self) -> None:
        """Display detected local minima and maxima."""
        self.extrema_listbox.delete(0, tk.END)

        for point in self.extrema_points:
            label = (
                "Minimum"
                if point.point_type == "local minimum"
                else "Maximum"
            )

            self.extrema_listbox.insert(
                tk.END,
                (
                    f"{label}: y = {point.first_expression} "
                    f"at ({point.x:.8g}, {point.y:.8g})"
                ),
            )

        if not self.extrema_points:
            self.extrema_listbox.insert(
                tk.END,
                "No local extrema detected in the current range.",
            )

    def _draw_extrema_markers(self) -> None:
        """Draw markers for detected local minima and maxima."""
        self._clear_extrema_artists(redraw=False)

        for point in self.extrema_points:
            marker = self.axes.scatter(
                [point.x],
                [point.y],
                marker=(
                    "v"
                    if point.point_type == "local minimum"
                    else "^"
                ),
                s=85,
                zorder=10,
                label="_nolegend_",
            )

            self.extrema_artists.append(marker)

        self.canvas.draw_idle()

    def _select_extrema_result(
        self,
        _event: tk.Event,
    ) -> None:
        """Highlight a selected local extremum."""
        selection = self.extrema_listbox.curselection()

        if not selection:
            return

        index = int(selection[0])

        if index >= len(self.extrema_points):
            return

        point = self.extrema_points[index]

        self._show_point_marker(
            SelectedPoint(
                expression=point.point_type,
                x=point.x,
                y=point.y,
                distance=0.0,
            )
        )

    def clear_extrema_markers(
        self,
        redraw: bool = True,
    ) -> None:
        """Clear detected extrema and their list."""
        self.extrema_points.clear()

        if hasattr(self, "extrema_listbox"):
            self.extrema_listbox.delete(0, tk.END)

        self._clear_extrema_artists(
            redraw=redraw,
        )

    def _clear_extrema_artists(
        self,
        redraw: bool = True,
    ) -> None:
        """Safely remove extrema marker artists."""
        for artist in self.extrema_artists:
            try:
                artist.remove()
            except (
                ValueError,
                NotImplementedError,
            ):
                pass

        self.extrema_artists.clear()

        if redraw:
            self.canvas.draw_idle()

    # --------------------------------------------------
    # INFLECTION POINTS AND CONCAVITY
    # --------------------------------------------------

    def find_inflection_points(self) -> None:
        """Detect inflection points for the selected function."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before searching for inflection points.",
                parent=self.window,
            )
            return

        settings = self._read_graph_settings()

        if settings is None:
            return

        x_min, x_max, point_count = settings
        expression = self.expressions[selected_index].expression

        x_values = self._generate_x_values(
            x_min,
            x_max,
            point_count,
        )

        second_derivatives: list[float | None] = []

        for x_value in x_values:
            try:
                value = self._numerical_second_derivative(
                    expression,
                    x_value,
                )

                if math.isfinite(value):
                    second_derivatives.append(value)
                else:
                    second_derivatives.append(None)

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                second_derivatives.append(None)

        detected: list[SpecialPoint] = []

        for index in range(len(x_values) - 1):
            second1 = second_derivatives[index]
            second2 = second_derivatives[index + 1]

            if second1 is None or second2 is None:
                continue

            # An inflection point requires a concavity sign change.
            if second1 * second2 >= 0:
                continue

            inflection_x = self._linear_zero_interpolation(
                x_values[index],
                second1,
                x_values[index + 1],
                second2,
            )

            try:
                inflection_y = self._evaluate_parameterized_expression(
                    expression,
                    inflection_x,
                )
            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                continue

            if not math.isfinite(inflection_y):
                continue

            detected.append(
                SpecialPoint(
                    point_type="inflection point",
                    x=inflection_x,
                    y=inflection_y,
                    first_expression=expression,
                )
            )

        self.inflection_points = self._deduplicate_inflection_points(
            detected
        )

        self._refresh_inflection_list()
        self._draw_inflection_markers()

        self.status_variable.set(
            f"Found {len(self.inflection_points)} inflection point(s) "
            f"for y = {expression}."
        )

    def show_concavity(self) -> None:
        """Highlight concave-up and concave-down regions."""
        selected_index = self._get_selected_expression_index()

        if selected_index is None:
            messagebox.showinfo(
                "No Function Selected",
                "Select a function before displaying concavity.",
                parent=self.window,
            )
            return

        settings = self._read_graph_settings()

        if settings is None:
            return

        x_min, x_max, point_count = settings
        expression = self.expressions[selected_index].expression

        x_values = self._generate_x_values(
            x_min,
            x_max,
            point_count,
        )

        y_values: list[float] = []
        concave_up: list[bool] = []
        concave_down: list[bool] = []

        for x_value in x_values:
            try:
                y_value = self._evaluate_parameterized_expression(
                    expression,
                    x_value,
                )
                second_derivative = self._numerical_second_derivative(
                    expression,
                    x_value,
                )

                if (
                    not math.isfinite(y_value)
                    or not math.isfinite(second_derivative)
                ):
                    raise ValueError("Undefined point.")

                y_values.append(y_value)
                concave_up.append(second_derivative > 0)
                concave_down.append(second_derivative < 0)

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                y_values.append(float("nan"))
                concave_up.append(False)
                concave_down.append(False)

        self.clear_inflection_markers(redraw=False)

        up_artist = self.axes.fill_between(
            x_values,
            y_values,
            0,
            where=concave_up,
            alpha=0.15,
            interpolate=True,
            label="Concave up",
        )

        down_artist = self.axes.fill_between(
            x_values,
            y_values,
            0,
            where=concave_down,
            alpha=0.15,
            interpolate=True,
            label="Concave down",
        )

        self.inflection_artists.extend(
            [
                up_artist,
                down_artist,
            ]
        )

        self._refresh_legend()
        self.canvas.draw_idle()

        self.status_variable.set(
            f"Displayed concavity regions for y = {expression}."
        )

    def _numerical_second_derivative(
        self,
        expression: str,
        x_value: float,
    ) -> float:
        """Estimate f''(x) with a central second-difference formula."""
        step = SECOND_DERIVATIVE_STEP * max(1.0, abs(x_value))

        left_value = self._evaluate_parameterized_expression(
            expression,
            x_value - step,
        )
        center_value = self._evaluate_parameterized_expression(
            expression,
            x_value,
        )
        right_value = self._evaluate_parameterized_expression(
            expression,
            x_value + step,
        )

        return (
            left_value
            - 2 * center_value
            + right_value
        ) / (step * step)

    def _deduplicate_inflection_points(
        self,
        points: list[SpecialPoint],
    ) -> list[SpecialPoint]:
        """Remove near-duplicate inflection points."""
        unique: list[SpecialPoint] = []

        for point in sorted(points, key=lambda item: item.x):
            duplicate = any(
                math.isclose(
                    point.x,
                    existing.x,
                    abs_tol=INFLECTION_DUPLICATE_TOLERANCE,
                )
                and math.isclose(
                    point.y,
                    existing.y,
                    abs_tol=INFLECTION_DUPLICATE_TOLERANCE,
                )
                for existing in unique
            )

            if not duplicate:
                unique.append(point)

        return unique

    def _refresh_inflection_list(self) -> None:
        """Display detected inflection points."""
        self.inflection_listbox.delete(0, tk.END)

        for point in self.inflection_points:
            self.inflection_listbox.insert(
                tk.END,
                (
                    f"Inflection: y = {point.first_expression} "
                    f"at ({point.x:.8g}, {point.y:.8g})"
                ),
            )

        if not self.inflection_points:
            self.inflection_listbox.insert(
                tk.END,
                "No inflection points detected in the current range.",
            )

    def _draw_inflection_markers(self) -> None:
        """Draw detected inflection-point markers."""
        self._clear_inflection_artists(redraw=False)

        for point in self.inflection_points:
            marker = self.axes.scatter(
                [point.x],
                [point.y],
                marker="D",
                s=75,
                zorder=10,
                label="_nolegend_",
            )

            self.inflection_artists.append(marker)

        self.canvas.draw_idle()

    def _select_inflection_result(
        self,
        _event: tk.Event,
    ) -> None:
        """Highlight the selected inflection point."""
        selection = self.inflection_listbox.curselection()

        if not selection:
            return

        index = int(selection[0])

        if index >= len(self.inflection_points):
            return

        point = self.inflection_points[index]

        self._show_point_marker(
            SelectedPoint(
                expression="inflection point",
                x=point.x,
                y=point.y,
                distance=0.0,
            )
        )

    def clear_inflection_markers(
        self,
        redraw: bool = True,
    ) -> None:
        """Clear inflection points and concavity overlays."""
        self.inflection_points.clear()

        if hasattr(self, "inflection_listbox"):
            self.inflection_listbox.delete(0, tk.END)

        self._clear_inflection_artists(
            redraw=redraw,
        )

    def _clear_inflection_artists(
        self,
        redraw: bool = True,
    ) -> None:
        """Safely remove inflection and concavity artists."""
        for artist in self.inflection_artists:
            try:
                artist.remove()
            except (
                ValueError,
                NotImplementedError,
            ):
                pass

        self.inflection_artists.clear()

        if redraw:
            self.canvas.draw_idle()

    # --------------------------------------------------
    # ROOTS AND INTERSECTIONS
    # --------------------------------------------------

    def find_roots_and_intersections(self) -> None:
        """Find roots and pairwise intersections."""
        if not self.plotted_series:
            messagebox.showinfo(
                "No Functions",
                "Plot at least one visible function first.",
                parent=self.window,
            )
            return

        self.clear_analysis_markers(redraw=False)

        detected: list[SpecialPoint] = []

        for graph_expression, x_values, y_values in self.plotted_series:
            detected.extend(
                self._find_roots_for_series(
                    graph_expression.expression,
                    x_values,
                    y_values,
                )
            )

        for first_index in range(len(self.plotted_series)):
            for second_index in range(
                first_index + 1,
                len(self.plotted_series),
            ):
                detected.extend(
                    self._find_intersections_between_series(
                        self.plotted_series[first_index],
                        self.plotted_series[second_index],
                    )
                )

        self.special_points = self._deduplicate_special_points(
            detected
        )

        self._refresh_analysis_list()
        self._draw_analysis_markers()

        roots = sum(
            point.point_type == "root"
            for point in self.special_points
        )
        intersections = sum(
            point.point_type == "intersection"
            for point in self.special_points
        )

        self.status_variable.set(
            f"Found {roots} root(s) and "
            f"{intersections} intersection(s)."
        )

    def _find_roots_for_series(
        self,
        expression: str,
        x_values: list[float],
        y_values: list[float],
    ) -> list[SpecialPoint]:
        """Find approximate roots from sampled data."""
        roots: list[SpecialPoint] = []

        for index in range(len(x_values) - 1):
            x1 = x_values[index]
            x2 = x_values[index + 1]
            y1 = y_values[index]
            y2 = y_values[index + 1]

            if not math.isfinite(y1) or not math.isfinite(y2):
                continue

            if abs(y1) <= ROOT_Y_TOLERANCE:
                roots.append(
                    SpecialPoint(
                        "root",
                        x1,
                        0.0,
                        expression,
                    )
                )
                continue

            if y1 * y2 < 0:
                root_x = self._linear_zero_interpolation(
                    x1,
                    y1,
                    x2,
                    y2,
                )

                try:
                    root_y = self._evaluate_parameterized_expression(
                        expression,
                        root_x,
                    )
                except (
                    ArithmeticError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    root_y = 0.0

                roots.append(
                    SpecialPoint(
                        "root",
                        root_x,
                        root_y,
                        expression,
                    )
                )

        if x_values and y_values:
            final_y = y_values[-1]

            if (
                math.isfinite(final_y)
                and abs(final_y) <= ROOT_Y_TOLERANCE
            ):
                roots.append(
                    SpecialPoint(
                        "root",
                        x_values[-1],
                        0.0,
                        expression,
                    )
                )

        return roots

    def _find_intersections_between_series(
        self,
        first_series: tuple[
            GraphExpression,
            list[float],
            list[float],
        ],
        second_series: tuple[
            GraphExpression,
            list[float],
            list[float],
        ],
    ) -> list[SpecialPoint]:
        """Find approximate intersections between two functions."""
        first_expression, first_x, first_y = first_series
        second_expression, second_x, second_y = second_series

        count = min(
            len(first_x),
            len(second_x),
            len(first_y),
            len(second_y),
        )

        intersections: list[SpecialPoint] = []

        for index in range(count - 1):
            x1 = first_x[index]
            x2 = first_x[index + 1]

            first_y1 = first_y[index]
            first_y2 = first_y[index + 1]
            second_y1 = second_y[index]
            second_y2 = second_y[index + 1]

            values = (
                first_y1,
                first_y2,
                second_y1,
                second_y2,
            )

            if not all(math.isfinite(value) for value in values):
                continue

            difference1 = first_y1 - second_y1
            difference2 = first_y2 - second_y2

            if abs(difference1) <= ROOT_Y_TOLERANCE:
                intersection_x = x1
            elif difference1 * difference2 < 0:
                intersection_x = self._linear_zero_interpolation(
                    x1,
                    difference1,
                    x2,
                    difference2,
                )
            else:
                continue

            try:
                first_result = self._evaluate_parameterized_expression(
                    first_expression.expression,
                    intersection_x,
                )
                second_result = self._evaluate_parameterized_expression(
                    second_expression.expression,
                    intersection_x,
                )

                intersection_y = (
                    first_result + second_result
                ) / 2

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                continue

            if not math.isfinite(intersection_y):
                continue

            intersections.append(
                SpecialPoint(
                    "intersection",
                    intersection_x,
                    intersection_y,
                    first_expression.expression,
                    second_expression.expression,
                )
            )

        return intersections

    @staticmethod
    def _linear_zero_interpolation(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> float:
        """Estimate where a line segment crosses zero."""
        denominator = y2 - y1

        if denominator == 0:
            return (x1 + x2) / 2

        return x1 - y1 * (x2 - x1) / denominator

    def _deduplicate_special_points(
        self,
        points: list[SpecialPoint],
    ) -> list[SpecialPoint]:
        """Remove near-duplicate roots and intersections."""
        unique: list[SpecialPoint] = []

        for point in sorted(
            points,
            key=lambda item: (
                item.point_type,
                item.x,
                item.y,
            ),
        ):
            duplicate = False

            for existing in unique:
                if (
                    point.point_type == existing.point_type
                    and point.first_expression
                    == existing.first_expression
                    and point.second_expression
                    == existing.second_expression
                    and math.isclose(
                        point.x,
                        existing.x,
                        abs_tol=POINT_DUPLICATE_TOLERANCE,
                    )
                    and math.isclose(
                        point.y,
                        existing.y,
                        abs_tol=POINT_DUPLICATE_TOLERANCE,
                    )
                ):
                    duplicate = True
                    break

            if not duplicate:
                unique.append(point)

        return unique

    def _refresh_analysis_list(self) -> None:
        """Display detected analysis points."""
        self.analysis_listbox.delete(0, tk.END)

        for point in self.special_points:
            self.analysis_listbox.insert(
                tk.END,
                point.description(),
            )

        if not self.special_points:
            self.analysis_listbox.insert(
                tk.END,
                "No roots or intersections detected.",
            )

    def _draw_analysis_markers(self) -> None:
        """Draw roots and intersections."""
        self._clear_analysis_artists(redraw=False)

        for point in self.special_points:
            marker = self.axes.scatter(
                [point.x],
                [point.y],
                marker=(
                    "o"
                    if point.point_type == "root"
                    else "X"
                ),
                s=(
                    55
                    if point.point_type == "root"
                    else 75
                ),
                zorder=9,
                label="_nolegend_",
            )

            self.special_point_artists.append(marker)

        self.canvas.draw_idle()

    def _select_analysis_result(
        self,
        _event: tk.Event,
    ) -> None:
        """Highlight a selected root or intersection."""
        selection = self.analysis_listbox.curselection()

        if not selection:
            return

        index = int(selection[0])

        if index >= len(self.special_points):
            return

        point = self.special_points[index]
        name = point.first_expression

        if point.second_expression is not None:
            name = (
                f"{point.first_expression} ∩ "
                f"{point.second_expression}"
            )

        self._show_point_marker(
            SelectedPoint(
                name,
                point.x,
                point.y,
                0.0,
            )
        )

    def clear_analysis_markers(
        self,
        redraw: bool = True,
    ) -> None:
        """Clear detected analysis points."""
        self.special_points.clear()
        self.analysis_listbox.delete(0, tk.END)

        self._clear_analysis_artists(
            redraw=redraw,
        )

    def _clear_analysis_artists(
        self,
        redraw: bool = True,
    ) -> None:
        """Safely remove Matplotlib analysis artists."""
        for artist in self.special_point_artists:
            try:
                artist.remove()
            except (
                ValueError,
                NotImplementedError,
            ):
                pass

        self.special_point_artists.clear()

        if redraw:
            self.canvas.draw_idle()

    # --------------------------------------------------
    # MANUAL POINT SELECTION
    # --------------------------------------------------

    def _select_nearest_point(self, event: Any) -> None:
        """Select the nearest sampled curve point."""
        if event.button != 1:
            return

        if event.inaxes is not self.axes:
            return

        if event.xdata is None or event.ydata is None:
            return

        if self.toolbar.mode:
            return

        selected = self._find_nearest_plotted_point(
            float(event.xdata),
            float(event.ydata),
        )

        if selected is None:
            self._clear_point_marker()
            self.status_variable.set(
                "No curve was close enough to the selected point."
            )
            return

        self._show_point_marker(selected)

    def _find_nearest_plotted_point(
        self,
        click_x: float,
        click_y: float,
    ) -> SelectedPoint | None:
        """Find the sampled graph point nearest to a click."""
        if not self.plotted_series:
            return None

        x_min, x_max = self.axes.get_xlim()
        y_min, y_max = self.axes.get_ylim()

        x_range = x_max - x_min
        y_range = y_max - y_min

        if x_range == 0 or y_range == 0:
            return None

        nearest: SelectedPoint | None = None

        for graph_expression, x_values, y_values in self.plotted_series:
            for x_value, y_value in zip(
                x_values,
                y_values,
            ):
                if not math.isfinite(y_value):
                    continue

                distance = math.hypot(
                    (x_value - click_x) / x_range,
                    (y_value - click_y) / y_range,
                )

                if nearest is None or distance < nearest.distance:
                    nearest = SelectedPoint(
                        graph_expression.expression,
                        x_value,
                        y_value,
                        distance,
                    )

        if (
            nearest is None
            or nearest.distance > POINT_SELECTION_THRESHOLD
        ):
            return None

        return nearest

    def _show_point_marker(
        self,
        point: SelectedPoint,
    ) -> None:
        """Draw a selected-point marker and annotation."""
        self._clear_point_marker(redraw=False)

        marker_line = self.axes.plot(
            point.x,
            point.y,
            marker="o",
            markersize=7,
            linestyle="None",
            zorder=10,
        )

        self.point_marker = marker_line[0]

        annotation = (
            f"y = {point.expression}\n"
            f"x = {point.x:.8g}\n"
            f"y = {point.y:.8g}"
        )

        self.point_annotation = self.axes.annotate(
            annotation,
            xy=(point.x, point.y),
            xytext=(12, 12),
            textcoords="offset points",
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": "white",
                "alpha": 0.9,
            },
            arrowprops={
                "arrowstyle": "->",
            },
            zorder=11,
        )

        self.coordinate_variable.set(
            f"x: {point.x:.8g}    y: {point.y:.8g}"
        )
        self.status_variable.set(
            f"Selected {point.expression} at "
            f"({point.x:.8g}, {point.y:.8g})."
        )

        self.canvas.draw_idle()

    def _clear_point_marker(
        self,
        redraw: bool = True,
    ) -> None:
        """Safely remove the selected point marker."""
        if self.point_marker is not None:
            try:
                self.point_marker.remove()
            except (
                ValueError,
                NotImplementedError,
            ):
                pass
            finally:
                self.point_marker = None

        if self.point_annotation is not None:
            try:
                self.point_annotation.remove()
            except (
                ValueError,
                NotImplementedError,
            ):
                pass
            finally:
                self.point_annotation = None

        self.coordinate_variable.set("x: —    y: —")

        if redraw:
            self.canvas.draw_idle()

    # --------------------------------------------------
    # GRAPH SETTINGS AND VALIDATION
    # --------------------------------------------------

    def _read_graph_settings(
        self,
        *,
        show_errors: bool = True,
    ) -> tuple[float, float, int] | None:
        """Read and validate graph settings."""
        try:
            x_min = float(self.x_min_variable.get())
            x_max = float(self.x_max_variable.get())
            point_count = int(self.point_count_variable.get())

        except ValueError:
            if show_errors:
                messagebox.showerror(
                    "Invalid Graph Settings",
                    "Range values must be numbers and sample points "
                    "must be a whole number.",
                    parent=self.window,
                )

            return None

        if x_min >= x_max:
            if show_errors:
                messagebox.showerror(
                    "Invalid Range",
                    "The x minimum must be smaller than the x maximum.",
                    parent=self.window,
                )

            return None

        if not MIN_POINT_COUNT <= point_count <= MAX_POINT_COUNT:
            if show_errors:
                messagebox.showerror(
                    "Invalid Sample Count",
                    f"Sample points must be between "
                    f"{MIN_POINT_COUNT} and {MAX_POINT_COUNT}.",
                    parent=self.window,
                )

            return None

        return x_min, x_max, point_count

    def reset_view(self) -> None:
        """Restore the configured range."""
        self.plot_all_expressions()

    def _validate_expression(self, expression: str) -> bool:
        """Validate an expression before adding it."""
        last_error: Exception | None = None

        for x_value in (-2.0, -1.0, 0.0, 1.0, 2.0):
            try:
                result = self._evaluate_parameterized_expression(
                    expression,
                    x_value,
                )

                if math.isfinite(result):
                    return True

            except Exception as error:
                last_error = error

        messagebox.showerror(
            "Invalid Expression",
            "Could not graph the expression:\n\n"
            + (
                str(last_error)
                if last_error is not None
                else "The expression produced no valid values."
            ),
            parent=self.window,
        )

        return False

    def _expression_has_valid_sample(
        self,
        expression: str,
    ) -> bool:
        """Quietly validate an expression for live preview."""
        for x_value in (-2.0, -1.0, 0.0, 1.0, 2.0):
            try:
                result = self._evaluate_parameterized_expression(
                    expression,
                    x_value,
                )

                if math.isfinite(result):
                    return True

            except (
                ArithmeticError,
                SyntaxError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                continue

        return False

    # --------------------------------------------------
    # INTERACTION
    # --------------------------------------------------

    def _update_cursor_coordinates(self, event: Any) -> None:
        """Display cursor coordinates."""
        if event.inaxes is not self.axes:
            if self.point_marker is None:
                self.coordinate_variable.set("x: —    y: —")
            return

        if event.xdata is None or event.ydata is None:
            return

        if self.point_marker is not None:
            return

        self.coordinate_variable.set(
            f"x: {event.xdata:.6g}    y: {event.ydata:.6g}"
        )

    def _zoom_with_mouse_wheel(self, event: Any) -> None:
        """Zoom around the mouse cursor."""
        if event.inaxes is not self.axes:
            return

        if event.xdata is None or event.ydata is None:
            return

        x_min, x_max = self.axes.get_xlim()
        y_min, y_max = self.axes.get_ylim()

        x_width = x_max - x_min
        y_height = y_max - y_min

        if x_width == 0 or y_height == 0:
            return

        scale = 0.8 if event.button == "up" else 1.25

        new_x_width = x_width * scale
        new_y_height = y_height * scale

        x_ratio = (event.xdata - x_min) / x_width
        y_ratio = (event.ydata - y_min) / y_height

        self.axes.set_xlim(
            event.xdata - new_x_width * x_ratio,
            event.xdata + new_x_width * (1 - x_ratio),
        )
        self.axes.set_ylim(
            event.ydata - new_y_height * y_ratio,
            event.ydata + new_y_height * (1 - y_ratio),
        )

        self.canvas.draw_idle()

    # --------------------------------------------------
    # AXES AND SAMPLING
    # --------------------------------------------------

    def _reset_axes_content(self) -> None:
        """Restore labels, axes, and grid."""
        self.axes.set_title("Function Graph")
        self.axes.set_xlabel("x")
        self.axes.set_ylabel("y")
        self.axes.grid(True)

        horizontal_axis = self.axes.axhline(
            y=0,
            linewidth=0.8,
        )
        vertical_axis = self.axes.axvline(
            x=0,
            linewidth=0.8,
        )

        horizontal_axis._calculator_reference_axis = True
        vertical_axis._calculator_reference_axis = True

        self._apply_theme_to_axes()

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
        """Add an expression when Enter is pressed."""
        self.add_expression()
        return "break"

    def _toggle_expression_from_event(
        self,
        _event: tk.Event,
    ) -> str:
        """Toggle visibility on double-click."""
        self.toggle_selected_expression()
        return "break"


# --------------------------------------------------
# PARAMETRIC GRAPH WINDOW
# --------------------------------------------------

class ParametricGraphWindow:
    """Interactive window for plotting x(t) and y(t)."""

    def __init__(
        self,
        parent: tk.Misc,
        theme_name: str = "Light",
    ) -> None:
        """Create the parametric graph window."""
        self.window = tk.Toplevel(parent)
        self.window.title("Parametric Graph")
        self.window.geometry("1000x700")
        self.window.minsize(760, 520)

        self.theme_name = (
            theme_name
            if theme_name in GRAPH_THEMES
            else "Light"
        )

        self.x_expression_variable = tk.StringVar(
            value="cos(t)",
        )
        self.y_expression_variable = tk.StringVar(
            value="sin(t)",
        )
        self.t_min_variable = tk.StringVar(
            value=str(DEFAULT_PARAMETRIC_T_MIN),
        )
        self.t_max_variable = tk.StringVar(
            value=str(DEFAULT_PARAMETRIC_T_MAX),
        )
        self.point_count_variable = tk.StringVar(
            value=str(DEFAULT_PARAMETRIC_POINTS),
        )
        self.live_update_enabled = tk.BooleanVar(
            value=True,
        )
        self.status_variable = tk.StringVar(
            value="Enter x(t) and y(t), then click Plot.",
        )
        self.coordinate_variable = tk.StringVar(
            value="x: —    y: —    t: —",
        )

        self.live_update_job: str | None = None
        self.t_values: list[float] = []
        self.x_values: list[float] = []
        self.y_values: list[float] = []

        self._create_layout()
        self._bind_events()
        self.plot_parametric(show_errors=False)

    def _attach_tooltip(
        self,
        widget: tk.Widget,
        text: str,
    ) -> tk.Widget:
        """Attach a tooltip and return the widget."""
        Tooltip(
            widget,
            text,
        )

        return widget

    def _create_layout(self) -> None:
        """Create the parametric plotter layout."""
        main_frame = tk.Frame(self.window)
        main_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10,
        )

        controls = tk.LabelFrame(
            main_frame,
            text="Parametric Function",
            padx=8,
            pady=8,
        )
        controls.pack(
            side="left",
            fill="y",
            padx=(0, 10),
        )

        graph_frame = tk.Frame(main_frame)
        graph_frame.pack(
            side="right",
            fill="both",
            expand=True,
        )

        labels = (
            ("x(t) =", self.x_expression_variable),
            ("y(t) =", self.y_expression_variable),
            ("t minimum:", self.t_min_variable),
            ("t maximum:", self.t_max_variable),
            ("Sample points:", self.point_count_variable),
        )

        for row, (label_text, variable) in enumerate(labels):
            tk.Label(
                controls,
                text=label_text,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 5),
                pady=4,
            )

            tk.Entry(
                controls,
                textvariable=variable,
                width=24,
            ).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=4,
            )

        tk.Checkbutton(
            controls,
            text="Live update",
            variable=self.live_update_enabled,
            command=self._handle_live_toggle,
        ).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 2),
        )

        tk.Button(
            controls,
            text="Plot Parametric Curve",
            command=self.plot_parametric,
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Clear",
            command=self.clear_graph,
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        tk.Button(
            controls,
            text="Export PNG",
            command=lambda: self.export_graph("png"),
        ).grid(
            row=8,
            column=0,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Export SVG",
            command=lambda: self.export_graph("svg"),
        ).grid(
            row=8,
            column=1,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Export PDF",
            command=lambda: self.export_graph("pdf"),
        ).grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        examples = (
            "Examples:\n\n"
            "Circle:\n"
            "x(t) = cos(t)\n"
            "y(t) = sin(t)\n\n"
            "Lissajous:\n"
            "x(t) = sin(3*t)\n"
            "y(t) = sin(2*t)\n\n"
            "Spiral:\n"
            "x(t) = t*cos(t)\n"
            "y(t) = t*sin(t)"
        )

        tk.Label(
            controls,
            text=examples,
            justify="left",
            anchor="nw",
        ).grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
        )

        controls.columnconfigure(1, weight=1)

        self.figure = Figure(
            figsize=(7, 6),
            dpi=100,
        )
        self.axes = self.figure.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=graph_frame,
        )
        self.canvas.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

        self.toolbar = NavigationToolbar2Tk(
            self.canvas,
            graph_frame,
            pack_toolbar=False,
        )
        self.toolbar.update()
        self.toolbar.pack(fill="x")

        status_frame = tk.Frame(self.window)
        status_frame.pack(
            side="bottom",
            fill="x",
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
            width=34,
        ).pack(side="right")

        self._reset_axes()

        self._attach_advanced_tooltips()

    def _attach_advanced_tooltips(self) -> None:
        """Attach tooltips to the main controls in this window."""
        tooltip_texts = {'Plot Parametric Curve': 'Plot x(t) and y(t) across the selected t-range.', 'Clear': 'Clear the current parametric graph.'}

        def visit(widget: tk.Widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Button):
                    label = str(child.cget("text"))

                    if label in tooltip_texts:
                        self._attach_tooltip(
                            child,
                            tooltip_texts[label],
                        )

                visit(child)

        visit(self.window)

    def _bind_events(self) -> None:
        """Bind entry changes and mouse movement."""
        for variable in (
            self.x_expression_variable,
            self.y_expression_variable,
            self.t_min_variable,
            self.t_max_variable,
            self.point_count_variable,
        ):
            variable.trace_add(
                "write",
                self._schedule_live_update,
            )

        self.canvas.mpl_connect(
            "motion_notify_event",
            self._update_coordinates,
        )

    def _schedule_live_update(
        self,
        *_args: object,
    ) -> None:
        """Debounce live updates."""
        if not self.live_update_enabled.get():
            return

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(
                    self.live_update_job
                )
            except (ValueError, tk.TclError):
                pass

        self.live_update_job = self.window.after(
            LIVE_UPDATE_DELAY_MS,
            self._perform_live_update,
        )

    def _perform_live_update(self) -> None:
        """Run a quiet live update."""
        self.live_update_job = None
        self.plot_parametric(show_errors=False)

    def _handle_live_toggle(self) -> None:
        """Handle live-update checkbox changes."""
        if self.live_update_enabled.get():
            self._schedule_live_update()
            return

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(
                    self.live_update_job
                )
            except (ValueError, tk.TclError):
                pass

            self.live_update_job = None

    def plot_parametric(
        self,
        *,
        show_errors: bool = True,
    ) -> None:
        """Evaluate and draw the parametric curve."""
        settings = self._read_settings(
            show_errors=show_errors,
        )

        if settings is None:
            return

        (
            x_expression,
            y_expression,
            t_min,
            t_max,
            point_count,
        ) = settings

        t_values = self._generate_values(
            t_min,
            t_max,
            point_count,
        )

        x_values: list[float] = []
        y_values: list[float] = []
        valid_count = 0

        for t_value in t_values:
            try:
                x_value = self._evaluate_t_expression(
                    x_expression,
                    t_value,
                )
                y_value = self._evaluate_t_expression(
                    y_expression,
                    t_value,
                )

                if (
                    not math.isfinite(x_value)
                    or not math.isfinite(y_value)
                    or abs(x_value) > MAX_ABSOLUTE_Y
                    or abs(y_value) > MAX_ABSOLUTE_Y
                ):
                    raise ValueError(
                        "Invalid parametric point."
                    )

                x_values.append(x_value)
                y_values.append(y_value)
                valid_count += 1

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                x_values.append(float("nan"))
                y_values.append(float("nan"))

        if valid_count == 0:
            if show_errors:
                messagebox.showerror(
                    "Parametric Plot Error",
                    "The expressions produced no valid points.",
                    parent=self.window,
                )
            return

        self.t_values = t_values
        self.x_values = x_values
        self.y_values = y_values

        self.axes.clear()
        self._reset_axes()

        self.axes.plot(
            x_values,
            y_values,
            linewidth=2,
            label=(
                f"x(t) = {x_expression}, "
                f"y(t) = {y_expression}"
            ),
        )

        self.axes.set_aspect(
            "equal",
            adjustable="datalim",
        )

        legend = self.axes.legend()
        self._style_legend(legend)

        self.figure.tight_layout()
        self.canvas.draw_idle()

        self.status_variable.set(
            f"Plotted {valid_count} valid parametric points "
            f"for t from {t_min:.8g} to {t_max:.8g}."
        )

    def clear_graph(self) -> None:
        """Clear the parametric graph."""
        self.t_values.clear()
        self.x_values.clear()
        self.y_values.clear()

        self.axes.clear()
        self._reset_axes()
        self.canvas.draw_idle()

        self.coordinate_variable.set(
            "x: —    y: —    t: —",
        )
        self.status_variable.set(
            "Parametric graph cleared.",
        )

    def _read_settings(
        self,
        *,
        show_errors: bool,
    ) -> tuple[str, str, float, float, int] | None:
        """Read and validate parametric settings."""
        x_expression = (
            self.x_expression_variable.get().strip()
        )
        y_expression = (
            self.y_expression_variable.get().strip()
        )

        if not x_expression or not y_expression:
            if show_errors:
                messagebox.showerror(
                    "Missing Expressions",
                    "Both x(t) and y(t) are required.",
                    parent=self.window,
                )
            return None

        try:
            t_min = self._evaluate_constant(
                self.t_min_variable.get(),
            )
            t_max = self._evaluate_constant(
                self.t_max_variable.get(),
            )
            point_count = int(
                self.point_count_variable.get()
            )

        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            if show_errors:
                messagebox.showerror(
                    "Invalid Parametric Settings",
                    "The t-range and sample count are invalid.",
                    parent=self.window,
                )
            return None

        if t_min >= t_max:
            if show_errors:
                messagebox.showerror(
                    "Invalid t Range",
                    "t minimum must be smaller than t maximum.",
                    parent=self.window,
                )
            return None

        if not (
            MIN_PARAMETRIC_POINTS
            <= point_count
            <= MAX_PARAMETRIC_POINTS
        ):
            if show_errors:
                messagebox.showerror(
                    "Invalid Sample Count",
                    f"Sample points must be between "
                    f"{MIN_PARAMETRIC_POINTS} and "
                    f"{MAX_PARAMETRIC_POINTS}.",
                    parent=self.window,
                )
            return None

        return (
            x_expression,
            y_expression,
            t_min,
            t_max,
            point_count,
        )

    @staticmethod
    def _replace_parameter(
        expression: str,
    ) -> str:
        """Convert standalone t symbols into the evaluator's x variable."""
        return re.sub(
            r"\bt\b",
            "x",
            expression,
        )

    def _evaluate_t_expression(
        self,
        expression: str,
        t_value: float,
    ) -> float:
        """Evaluate an expression using t as the parameter."""
        converted_expression = self._replace_parameter(
            expression,
        )

        return evaluate_graph_expression(
            converted_expression,
            t_value,
        )

    @staticmethod
    def _evaluate_constant(
        expression: str,
    ) -> float:
        """Evaluate a numeric constant such as 2*pi."""
        cleaned = expression.strip()

        if not cleaned:
            raise ValueError(
                "A numeric value is required."
            )

        # The graph evaluator requires an x value, but constant
        # expressions do not depend on it.
        value = evaluate_graph_expression(
            cleaned,
            0.0,
        )

        if not math.isfinite(value):
            raise ValueError(
                "The numeric value is not finite."
            )

        return value

    @staticmethod
    def _generate_values(
        minimum: float,
        maximum: float,
        point_count: int,
    ) -> list[float]:
        """Generate evenly spaced parameter values."""
        step = (
            maximum - minimum
        ) / (
            point_count - 1
        )

        return [
            minimum + index * step
            for index in range(point_count)
        ]

    def _reset_axes(self) -> None:
        """Restore axes and apply the inherited theme."""
        theme = GRAPH_THEMES.get(
            self.theme_name,
            GRAPH_THEMES["Light"],
        )

        self.figure.set_facecolor(
            theme["figure_facecolor"]
        )
        self.axes.set_facecolor(
            theme["axes_facecolor"]
        )

        self.axes.set_title(
            "Parametric Graph",
            color=theme["text_color"],
        )
        self.axes.set_xlabel(
            "x(t)",
            color=theme["text_color"],
        )
        self.axes.set_ylabel(
            "y(t)",
            color=theme["text_color"],
        )

        self.axes.tick_params(
            axis="both",
            colors=theme["text_color"],
        )

        for spine in self.axes.spines.values():
            spine.set_color(
                theme["axis_color"]
            )

        self.axes.grid(
            True,
            color=theme["grid_color"],
            linestyle="--",
            linewidth=0.7,
            alpha=0.65,
        )

        self.axes.axhline(
            0,
            linewidth=0.8,
            color=theme["axis_color"],
        )
        self.axes.axvline(
            0,
            linewidth=0.8,
            color=theme["axis_color"],
        )

    def _style_legend(self, legend: Any) -> None:
        """Style the legend using the inherited graph theme."""
        theme = GRAPH_THEMES.get(
            self.theme_name,
            GRAPH_THEMES["Light"],
        )

        legend.get_frame().set_facecolor(
            theme["axes_facecolor"]
        )
        legend.get_frame().set_edgecolor(
            theme["axis_color"]
        )

        for text_item in legend.get_texts():
            text_item.set_color(
                theme["text_color"]
            )

    def _update_coordinates(self, event: Any) -> None:
        """Show the nearest parametric point under the cursor."""
        if (
            event.inaxes is not self.axes
            or event.xdata is None
            or event.ydata is None
            or not self.t_values
        ):
            self.coordinate_variable.set(
                "x: —    y: —    t: —",
            )
            return

        x_min, x_max = self.axes.get_xlim()
        y_min, y_max = self.axes.get_ylim()

        x_range = x_max - x_min
        y_range = y_max - y_min

        if x_range == 0 or y_range == 0:
            return

        nearest_index: int | None = None
        nearest_distance: float | None = None

        for index, (x_value, y_value) in enumerate(
            zip(self.x_values, self.y_values)
        ):
            if (
                not math.isfinite(x_value)
                or not math.isfinite(y_value)
            ):
                continue

            distance = math.hypot(
                (x_value - event.xdata) / x_range,
                (y_value - event.ydata) / y_range,
            )

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                nearest_distance = distance
                nearest_index = index

        if nearest_index is None:
            return

        self.coordinate_variable.set(
            f"x: {self.x_values[nearest_index]:.6g}    "
            f"y: {self.y_values[nearest_index]:.6g}    "
            f"t: {self.t_values[nearest_index]:.6g}"
        )

    def export_graph(self, file_format: str) -> None:
        """Export the parametric graph."""
        supported_formats = {
            "png": ("PNG image", "*.png"),
            "svg": ("SVG vector image", "*.svg"),
            "pdf": ("PDF document", "*.pdf"),
        }

        if file_format not in supported_formats:
            return

        description, pattern = supported_formats[file_format]

        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title=(
                f"Export Parametric Graph as "
                f"{file_format.upper()}"
            ),
            defaultextension=f".{file_format}",
            initialfile=f"parametric_graph.{file_format}",
            filetypes=[
                (description, pattern),
                ("All files", "*.*"),
            ],
        )

        if not filepath:
            return

        try:
            self.figure.savefig(
                filepath,
                format=file_format,
                bbox_inches="tight",
                facecolor=self.figure.get_facecolor(),
            )

        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Export Error",
                f"Could not export the graph:\n\n{error}",
                parent=self.window,
            )
            return

        self.status_variable.set(
            f"Exported parametric graph to {filepath}"
        )


# --------------------------------------------------
# POLAR GRAPH WINDOW
# --------------------------------------------------

class PolarGraphWindow:
    """Interactive window for plotting r(theta)."""

    def __init__(
        self,
        parent: tk.Misc,
        theme_name: str = "Light",
    ) -> None:
        """Create the polar graph window."""
        self.window = tk.Toplevel(parent)
        self.window.title("Polar Graph")
        self.window.geometry("1000x700")
        self.window.minsize(760, 520)

        self.theme_name = (
            theme_name
            if theme_name in GRAPH_THEMES
            else "Light"
        )

        self.r_expression_variable = tk.StringVar(
            value="sin(5*theta)",
        )
        self.theta_min_variable = tk.StringVar(
            value=str(DEFAULT_POLAR_THETA_MIN),
        )
        self.theta_max_variable = tk.StringVar(
            value=str(DEFAULT_POLAR_THETA_MAX),
        )
        self.point_count_variable = tk.StringVar(
            value=str(DEFAULT_POLAR_POINTS),
        )
        self.live_update_enabled = tk.BooleanVar(
            value=True,
        )
        self.status_variable = tk.StringVar(
            value="Enter r(theta), then click Plot.",
        )
        self.coordinate_variable = tk.StringVar(
            value="r: —    θ: —    x: —    y: —",
        )

        self.live_update_job: str | None = None

        self.theta_values: list[float] = []
        self.r_values: list[float] = []
        self.x_values: list[float] = []
        self.y_values: list[float] = []

        self._create_layout()
        self._bind_events()
        self.plot_polar(show_errors=False)

    def _attach_tooltip(
        self,
        widget: tk.Widget,
        text: str,
    ) -> tk.Widget:
        """Attach a tooltip and return the widget."""
        Tooltip(
            widget,
            text,
        )

        return widget

    def _create_layout(self) -> None:
        """Create the polar plotter layout."""
        main_frame = tk.Frame(self.window)
        main_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10,
        )

        controls = tk.LabelFrame(
            main_frame,
            text="Polar Function",
            padx=8,
            pady=8,
        )
        controls.pack(
            side="left",
            fill="y",
            padx=(0, 10),
        )

        graph_frame = tk.Frame(main_frame)
        graph_frame.pack(
            side="right",
            fill="both",
            expand=True,
        )

        fields = (
            ("r(θ) =", self.r_expression_variable),
            ("θ minimum:", self.theta_min_variable),
            ("θ maximum:", self.theta_max_variable),
            ("Sample points:", self.point_count_variable),
        )

        for row, (label_text, variable) in enumerate(fields):
            tk.Label(
                controls,
                text=label_text,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 5),
                pady=4,
            )

            tk.Entry(
                controls,
                textvariable=variable,
                width=24,
            ).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=4,
            )

        tk.Checkbutton(
            controls,
            text="Live update",
            variable=self.live_update_enabled,
            command=self._handle_live_toggle,
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 2),
        )

        tk.Button(
            controls,
            text="Plot Polar Curve",
            command=self.plot_polar,
        ).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Clear",
            command=self.clear_graph,
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        tk.Button(
            controls,
            text="Export PNG",
            command=lambda: self.export_graph("png"),
        ).grid(
            row=7,
            column=0,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Export SVG",
            command=lambda: self.export_graph("svg"),
        ).grid(
            row=7,
            column=1,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Export PDF",
            command=lambda: self.export_graph("pdf"),
        ).grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        examples = (
            "Examples:\n\n"
            "Rose curve:\n"
            "r(θ) = sin(5*theta)\n\n"
            "Cardioid:\n"
            "r(θ) = 1 + cos(theta)\n\n"
            "Spiral:\n"
            "r(θ) = theta\n"
            "θ = 0 to 6*pi\n\n"
            "Lemniscate-like:\n"
            "r(θ) = sqrt(abs(cos(2*theta)))"
        )

        tk.Label(
            controls,
            text=examples,
            justify="left",
            anchor="nw",
        ).grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
        )

        controls.columnconfigure(1, weight=1)

        self.figure = Figure(
            figsize=(7, 6),
            dpi=100,
        )

        self.axes = self.figure.add_subplot(
            111,
            projection="polar",
        )

        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=graph_frame,
        )
        self.canvas.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

        self.toolbar = NavigationToolbar2Tk(
            self.canvas,
            graph_frame,
            pack_toolbar=False,
        )
        self.toolbar.update()
        self.toolbar.pack(fill="x")

        status_frame = tk.Frame(self.window)
        status_frame.pack(
            side="bottom",
            fill="x",
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
            width=46,
        ).pack(side="right")

        self._reset_axes()

        self._attach_advanced_tooltips()

    def _attach_advanced_tooltips(self) -> None:
        """Attach tooltips to the main controls in this window."""
        tooltip_texts = {'Plot Polar Curve': 'Plot r(theta) across the selected angular range.', 'Clear': 'Clear the current polar graph.'}

        def visit(widget: tk.Widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Button):
                    label = str(child.cget("text"))

                    if label in tooltip_texts:
                        self._attach_tooltip(
                            child,
                            tooltip_texts[label],
                        )

                visit(child)

        visit(self.window)

    def _bind_events(self) -> None:
        """Bind entry changes and mouse movement."""
        for variable in (
            self.r_expression_variable,
            self.theta_min_variable,
            self.theta_max_variable,
            self.point_count_variable,
        ):
            variable.trace_add(
                "write",
                self._schedule_live_update,
            )

        self.canvas.mpl_connect(
            "motion_notify_event",
            self._update_coordinates,
        )

    def _schedule_live_update(
        self,
        *_args: object,
    ) -> None:
        """Debounce live updates."""
        if not self.live_update_enabled.get():
            return

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(
                    self.live_update_job
                )
            except (ValueError, tk.TclError):
                pass

        self.live_update_job = self.window.after(
            LIVE_UPDATE_DELAY_MS,
            self._perform_live_update,
        )

    def _perform_live_update(self) -> None:
        """Run a quiet live update."""
        self.live_update_job = None
        self.plot_polar(show_errors=False)

    def _handle_live_toggle(self) -> None:
        """Handle live-update checkbox changes."""
        if self.live_update_enabled.get():
            self._schedule_live_update()
            return

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(
                    self.live_update_job
                )
            except (ValueError, tk.TclError):
                pass

            self.live_update_job = None

    def plot_polar(
        self,
        *,
        show_errors: bool = True,
    ) -> None:
        """Evaluate and draw the polar curve."""
        settings = self._read_settings(
            show_errors=show_errors,
        )

        if settings is None:
            return

        (
            expression,
            theta_min,
            theta_max,
            point_count,
        ) = settings

        theta_values = self._generate_values(
            theta_min,
            theta_max,
            point_count,
        )

        r_values: list[float] = []
        x_values: list[float] = []
        y_values: list[float] = []
        valid_count = 0

        for theta_value in theta_values:
            try:
                radius = self._evaluate_theta_expression(
                    expression,
                    theta_value,
                )

                if (
                    not math.isfinite(radius)
                    or abs(radius) > MAX_ABSOLUTE_Y
                ):
                    raise ValueError(
                        "Invalid polar radius."
                    )

                x_value = radius * math.cos(theta_value)
                y_value = radius * math.sin(theta_value)

                r_values.append(radius)
                x_values.append(x_value)
                y_values.append(y_value)
                valid_count += 1

            except (
                ArithmeticError,
                TypeError,
                ValueError,
                OverflowError,
            ):
                r_values.append(float("nan"))
                x_values.append(float("nan"))
                y_values.append(float("nan"))

        if valid_count == 0:
            if show_errors:
                messagebox.showerror(
                    "Polar Plot Error",
                    "The expression produced no valid points.",
                    parent=self.window,
                )
            return

        self.theta_values = theta_values
        self.r_values = r_values
        self.x_values = x_values
        self.y_values = y_values

        self.axes.clear()
        self._reset_axes()

        self.axes.plot(
            theta_values,
            r_values,
            linewidth=2,
            label=f"r(θ) = {expression}",
        )

        legend = self.axes.legend(
            loc="upper right",
            bbox_to_anchor=(1.2, 1.1),
        )
        self._style_legend(legend)

        self.figure.tight_layout()
        self.canvas.draw_idle()

        self.status_variable.set(
            f"Plotted {valid_count} valid polar points "
            f"for θ from {theta_min:.8g} to {theta_max:.8g}."
        )

    def clear_graph(self) -> None:
        """Clear the polar graph."""
        self.theta_values.clear()
        self.r_values.clear()
        self.x_values.clear()
        self.y_values.clear()

        self.axes.clear()
        self._reset_axes()
        self.canvas.draw_idle()

        self.coordinate_variable.set(
            "r: —    θ: —    x: —    y: —",
        )
        self.status_variable.set(
            "Polar graph cleared.",
        )

    def _read_settings(
        self,
        *,
        show_errors: bool,
    ) -> tuple[str, float, float, int] | None:
        """Read and validate polar settings."""
        expression = (
            self.r_expression_variable.get().strip()
        )

        if not expression:
            if show_errors:
                messagebox.showerror(
                    "Missing Expression",
                    "A polar expression r(theta) is required.",
                    parent=self.window,
                )
            return None

        try:
            theta_min = self._evaluate_constant(
                self.theta_min_variable.get(),
            )
            theta_max = self._evaluate_constant(
                self.theta_max_variable.get(),
            )
            point_count = int(
                self.point_count_variable.get()
            )

        except (
            ArithmeticError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            if show_errors:
                messagebox.showerror(
                    "Invalid Polar Settings",
                    "The theta range or sample count is invalid.",
                    parent=self.window,
                )
            return None

        if theta_min >= theta_max:
            if show_errors:
                messagebox.showerror(
                    "Invalid Theta Range",
                    "Theta minimum must be smaller than theta maximum.",
                    parent=self.window,
                )
            return None

        if not (
            MIN_POLAR_POINTS
            <= point_count
            <= MAX_POLAR_POINTS
        ):
            if show_errors:
                messagebox.showerror(
                    "Invalid Sample Count",
                    f"Sample points must be between "
                    f"{MIN_POLAR_POINTS} and "
                    f"{MAX_POLAR_POINTS}.",
                    parent=self.window,
                )
            return None

        return (
            expression,
            theta_min,
            theta_max,
            point_count,
        )

    @staticmethod
    def _replace_theta(
        expression: str,
    ) -> str:
        """Convert theta symbols into the evaluator's x variable."""
        converted = expression.replace("θ", "theta")

        return re.sub(
            r"\btheta\b",
            "x",
            converted,
        )

    def _evaluate_theta_expression(
        self,
        expression: str,
        theta_value: float,
    ) -> float:
        """Evaluate a radius expression using theta."""
        converted_expression = self._replace_theta(
            expression,
        )

        return evaluate_graph_expression(
            converted_expression,
            theta_value,
        )

    @staticmethod
    def _evaluate_constant(
        expression: str,
    ) -> float:
        """Evaluate a numeric constant such as 2*pi."""
        cleaned = expression.strip()

        if not cleaned:
            raise ValueError(
                "A numeric value is required."
            )

        value = evaluate_graph_expression(
            cleaned,
            0.0,
        )

        if not math.isfinite(value):
            raise ValueError(
                "The numeric value is not finite."
            )

        return value

    @staticmethod
    def _generate_values(
        minimum: float,
        maximum: float,
        point_count: int,
    ) -> list[float]:
        """Generate evenly spaced theta values."""
        step = (
            maximum - minimum
        ) / (
            point_count - 1
        )

        return [
            minimum + index * step
            for index in range(point_count)
        ]

    def _reset_axes(self) -> None:
        """Restore the polar axes and inherited theme."""
        theme = GRAPH_THEMES.get(
            self.theme_name,
            GRAPH_THEMES["Light"],
        )

        self.figure.set_facecolor(
            theme["figure_facecolor"]
        )
        self.axes.set_facecolor(
            theme["axes_facecolor"]
        )

        self.axes.set_title(
            "Polar Graph",
            color=theme["text_color"],
        )

        self.axes.tick_params(
            axis="both",
            colors=theme["text_color"],
        )

        self.axes.grid(
            True,
            color=theme["grid_color"],
            linestyle="--",
            linewidth=0.7,
            alpha=0.65,
        )

        self.axes.spines["polar"].set_color(
            theme["axis_color"]
        )

    def _style_legend(self, legend: Any) -> None:
        """Style the legend using the inherited theme."""
        theme = GRAPH_THEMES.get(
            self.theme_name,
            GRAPH_THEMES["Light"],
        )

        legend.get_frame().set_facecolor(
            theme["axes_facecolor"]
        )
        legend.get_frame().set_edgecolor(
            theme["axis_color"]
        )

        for text_item in legend.get_texts():
            text_item.set_color(
                theme["text_color"]
            )

    def _update_coordinates(self, event: Any) -> None:
        """Show the nearest polar point under the cursor."""
        if (
            event.inaxes is not self.axes
            or event.xdata is None
            or event.ydata is None
            or not self.theta_values
        ):
            self.coordinate_variable.set(
                "r: —    θ: —    x: —    y: —",
            )
            return

        # In a polar axes, event.xdata is theta and event.ydata is radius.
        theta_cursor = float(event.xdata)
        radius_cursor = float(event.ydata)

        nearest_index: int | None = None
        nearest_distance: float | None = None

        maximum_radius = max(
            (
                abs(value)
                for value in self.r_values
                if math.isfinite(value)
            ),
            default=1.0,
        )

        if maximum_radius == 0:
            maximum_radius = 1.0

        for index, (theta_value, radius) in enumerate(
            zip(self.theta_values, self.r_values)
        ):
            if not math.isfinite(radius):
                continue

            angular_distance = abs(
                math.atan2(
                    math.sin(theta_value - theta_cursor),
                    math.cos(theta_value - theta_cursor),
                )
            ) / math.pi

            radial_distance = abs(
                radius - radius_cursor
            ) / maximum_radius

            distance = math.hypot(
                angular_distance,
                radial_distance,
            )

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                nearest_distance = distance
                nearest_index = index

        if nearest_index is None:
            return

        self.coordinate_variable.set(
            f"r: {self.r_values[nearest_index]:.6g}    "
            f"θ: {self.theta_values[nearest_index]:.6g}    "
            f"x: {self.x_values[nearest_index]:.6g}    "
            f"y: {self.y_values[nearest_index]:.6g}"
        )

    def export_graph(self, file_format: str) -> None:
        """Export the polar graph."""
        supported_formats = {
            "png": ("PNG image", "*.png"),
            "svg": ("SVG vector image", "*.svg"),
            "pdf": ("PDF document", "*.pdf"),
        }

        if file_format not in supported_formats:
            return

        description, pattern = supported_formats[file_format]

        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title=(
                f"Export Polar Graph as "
                f"{file_format.upper()}"
            ),
            defaultextension=f".{file_format}",
            initialfile=f"polar_graph.{file_format}",
            filetypes=[
                (description, pattern),
                ("All files", "*.*"),
            ],
        )

        if not filepath:
            return

        try:
            self.figure.savefig(
                filepath,
                format=file_format,
                bbox_inches="tight",
                facecolor=self.figure.get_facecolor(),
            )

        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Export Error",
                f"Could not export the graph:\n\n{error}",
                parent=self.window,
            )
            return

        self.status_variable.set(
            f"Exported polar graph to {filepath}"
        )


# --------------------------------------------------
# PIECEWISE GRAPH WINDOW
# --------------------------------------------------

class PiecewiseGraphWindow:
    """Interactive window for plotting piecewise functions."""

    def __init__(
        self,
        parent: tk.Misc,
        theme_name: str = "Light",
    ) -> None:
        """Create the piecewise graph window."""
        self.window = tk.Toplevel(parent)
        self.window.title("Piecewise Function Graph")
        self.window.geometry("1050x720")
        self.window.minsize(800, 560)

        self.theme_name = (
            theme_name
            if theme_name in GRAPH_THEMES
            else "Light"
        )

        self.x_min_variable = tk.StringVar(
            value=str(DEFAULT_PIECEWISE_X_MIN),
        )
        self.x_max_variable = tk.StringVar(
            value=str(DEFAULT_PIECEWISE_X_MAX),
        )
        self.point_count_variable = tk.StringVar(
            value=str(DEFAULT_PIECEWISE_POINTS),
        )
        self.live_update_enabled = tk.BooleanVar(
            value=True,
        )
        self.status_variable = tk.StringVar(
            value="Enter one condition : expression rule per line.",
        )
        self.coordinate_variable = tk.StringVar(
            value="x: —    y: —",
        )

        self.live_update_job: str | None = None
        self.x_values: list[float] = []
        self.y_values: list[float] = []

        self._create_layout()
        self._bind_events()

        self.rules_text.insert(
            "1.0",
            "x < 0 : x^2\n"
            "x >= 0 : sqrt(x)",
        )

        self.plot_piecewise(show_errors=False)

    def _attach_tooltip(
        self,
        widget: tk.Widget,
        text: str,
    ) -> tk.Widget:
        """Attach a tooltip and return the widget."""
        Tooltip(
            widget,
            text,
        )

        return widget

    def _create_layout(self) -> None:
        """Create the piecewise plotter layout."""
        main_frame = tk.Frame(self.window)
        main_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10,
        )

        controls = tk.LabelFrame(
            main_frame,
            text="Piecewise Rules",
            padx=8,
            pady=8,
        )
        controls.pack(
            side="left",
            fill="y",
            padx=(0, 10),
        )

        graph_frame = tk.Frame(main_frame)
        graph_frame.pack(
            side="right",
            fill="both",
            expand=True,
        )

        tk.Label(
            controls,
            text=(
                "One rule per line:\n"
                "condition : expression"
            ),
            justify="left",
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6),
        )

        self.rules_text = tk.Text(
            controls,
            width=34,
            height=12,
            wrap="none",
            undo=True,
        )
        self.rules_text.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(0, 8),
        )

        fields = (
            ("x minimum:", self.x_min_variable),
            ("x maximum:", self.x_max_variable),
            ("Sample points:", self.point_count_variable),
        )

        for offset, (label_text, variable) in enumerate(
            fields,
            start=2,
        ):
            tk.Label(
                controls,
                text=label_text,
            ).grid(
                row=offset,
                column=0,
                sticky="w",
                padx=(0, 5),
                pady=4,
            )

            tk.Entry(
                controls,
                textvariable=variable,
                width=14,
            ).grid(
                row=offset,
                column=1,
                sticky="ew",
                pady=4,
            )

        tk.Checkbutton(
            controls,
            text="Live update",
            variable=self.live_update_enabled,
            command=self._handle_live_toggle,
        ).grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 2),
        )

        tk.Button(
            controls,
            text="Plot Piecewise Function",
            command=self.plot_piecewise,
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Clear",
            command=self.clear_graph,
        ).grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        tk.Button(
            controls,
            text="Export PNG",
            command=lambda: self.export_graph("png"),
        ).grid(
            row=8,
            column=0,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Export SVG",
            command=lambda: self.export_graph("svg"),
        ).grid(
            row=8,
            column=1,
            sticky="ew",
            pady=(8, 2),
        )

        tk.Button(
            controls,
            text="Export PDF",
            command=lambda: self.export_graph("pdf"),
        ).grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        examples = (
            "Examples:\n\n"
            "x < 0 : x^2\n"
            "x >= 0 : sqrt(x)\n\n"
            "x < -2 : -1\n"
            "-2 <= x and x <= 2 : x^2\n"
            "x > 2 : 1\n\n"
            "Conditions support:\n"
            "<  <=  >  >=  ==  !=\n"
            "and  or  not"
        )

        tk.Label(
            controls,
            text=examples,
            justify="left",
            anchor="nw",
        ).grid(
            row=10,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 0),
        )

        controls.columnconfigure(1, weight=1)
        controls.rowconfigure(1, weight=1)

        self.figure = Figure(
            figsize=(7, 6),
            dpi=100,
        )
        self.axes = self.figure.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=graph_frame,
        )
        self.canvas.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

        self.toolbar = NavigationToolbar2Tk(
            self.canvas,
            graph_frame,
            pack_toolbar=False,
        )
        self.toolbar.update()
        self.toolbar.pack(fill="x")

        status_frame = tk.Frame(self.window)
        status_frame.pack(
            side="bottom",
            fill="x",
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
            width=30,
        ).pack(side="right")

        self._reset_axes()

        self._attach_advanced_tooltips()

    def _attach_advanced_tooltips(self) -> None:
        """Attach tooltips to the main controls in this window."""
        tooltip_texts = {'Plot Piecewise Function': 'Evaluate the rules from top to bottom and plot the first match.', 'Clear': 'Clear the current piecewise graph.'}

        def visit(widget: tk.Widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Button):
                    label = str(child.cget("text"))

                    if label in tooltip_texts:
                        self._attach_tooltip(
                            child,
                            tooltip_texts[label],
                        )

                visit(child)

        visit(self.window)

    def _bind_events(self) -> None:
        """Bind live updates and coordinate tracking."""
        self.rules_text.bind(
            "<KeyRelease>",
            self._schedule_live_update_from_event,
        )

        for variable in (
            self.x_min_variable,
            self.x_max_variable,
            self.point_count_variable,
        ):
            variable.trace_add(
                "write",
                self._schedule_live_update,
            )

        self.canvas.mpl_connect(
            "motion_notify_event",
            self._update_coordinates,
        )

    def _schedule_live_update_from_event(
        self,
        _event: tk.Event,
    ) -> None:
        """Schedule an update after editing the rules."""
        self._schedule_live_update()

    def _schedule_live_update(
        self,
        *_args: object,
    ) -> None:
        """Debounce live updates."""
        if not self.live_update_enabled.get():
            return

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(
                    self.live_update_job
                )
            except (ValueError, tk.TclError):
                pass

        self.live_update_job = self.window.after(
            LIVE_UPDATE_DELAY_MS,
            self._perform_live_update,
        )

    def _perform_live_update(self) -> None:
        """Run a quiet live update."""
        self.live_update_job = None
        self.plot_piecewise(show_errors=False)

    def _handle_live_toggle(self) -> None:
        """Handle live-update checkbox changes."""
        if self.live_update_enabled.get():
            self._schedule_live_update()
            return

        if self.live_update_job is not None:
            try:
                self.window.after_cancel(
                    self.live_update_job
                )
            except (ValueError, tk.TclError):
                pass

            self.live_update_job = None

    def plot_piecewise(
        self,
        *,
        show_errors: bool = True,
    ) -> None:
        """Parse, evaluate, and draw the piecewise function."""
        settings = self._read_settings(
            show_errors=show_errors,
        )

        if settings is None:
            return

        rules, x_min, x_max, point_count = settings

        x_values = self._generate_values(
            x_min,
            x_max,
            point_count,
        )

        y_values: list[float] = []
        valid_count = 0

        for x_value in x_values:
            y_value = float("nan")

            for condition, expression in rules:
                try:
                    matches = self._evaluate_condition(
                        condition,
                        x_value,
                    )
                except (
                    SyntaxError,
                    TypeError,
                    ValueError,
                ):
                    matches = False

                if not matches:
                    continue

                try:
                    candidate = evaluate_graph_expression(
                        expression,
                        x_value,
                    )

                    if (
                        not math.isfinite(candidate)
                        or abs(candidate) > MAX_ABSOLUTE_Y
                    ):
                        raise ValueError(
                            "Invalid function value."
                        )

                    y_value = candidate
                    valid_count += 1

                except (
                    ArithmeticError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    y_value = float("nan")

                # The first matching rule wins.
                break

            y_values.append(y_value)

        if valid_count == 0:
            if show_errors:
                messagebox.showerror(
                    "Piecewise Plot Error",
                    "The rules produced no valid graph points.",
                    parent=self.window,
                )
            return

        self.x_values = x_values
        self.y_values = y_values

        self.axes.clear()
        self._reset_axes()

        self.axes.plot(
            x_values,
            y_values,
            linewidth=2,
            label="Piecewise function",
        )

        # Mark finite segment endpoints to make boundaries easier to see.
        self._draw_segment_endpoints(
            x_values,
            y_values,
        )

        legend = self.axes.legend()
        self._style_legend(legend)

        self.axes.set_xlim(
            x_min,
            x_max,
        )

        self.axes.relim()
        self.axes.autoscale_view(
            scalex=False,
            scaley=True,
        )

        self.figure.tight_layout()
        self.canvas.draw_idle()

        self.status_variable.set(
            f"Plotted {valid_count} valid piecewise points "
            f"across {len(rules)} rule(s)."
        )

    def _draw_segment_endpoints(
        self,
        x_values: list[float],
        y_values: list[float],
    ) -> None:
        """Mark starts and ends of finite graph segments."""
        for index, y_value in enumerate(y_values):
            if not math.isfinite(y_value):
                continue

            previous_valid = (
                index > 0
                and math.isfinite(y_values[index - 1])
            )
            next_valid = (
                index < len(y_values) - 1
                and math.isfinite(y_values[index + 1])
            )

            if not previous_valid or not next_valid:
                self.axes.scatter(
                    [x_values[index]],
                    [y_value],
                    s=28,
                    zorder=8,
                    label="_nolegend_",
                )

    def clear_graph(self) -> None:
        """Clear the piecewise graph."""
        self.x_values.clear()
        self.y_values.clear()

        self.axes.clear()
        self._reset_axes()
        self.canvas.draw_idle()

        self.coordinate_variable.set(
            "x: —    y: —",
        )
        self.status_variable.set(
            "Piecewise graph cleared.",
        )

    def _read_settings(
        self,
        *,
        show_errors: bool,
    ) -> tuple[
        list[tuple[str, str]],
        float,
        float,
        int,
    ] | None:
        """Read and validate piecewise rules and graph settings."""
        raw_rules = self.rules_text.get(
            "1.0",
            tk.END,
        )

        try:
            rules = self._parse_rules(raw_rules)
            x_min = self._evaluate_constant(
                self.x_min_variable.get(),
            )
            x_max = self._evaluate_constant(
                self.x_max_variable.get(),
            )
            point_count = int(
                self.point_count_variable.get()
            )

        except (
            ArithmeticError,
            SyntaxError,
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            if show_errors:
                messagebox.showerror(
                    "Invalid Piecewise Settings",
                    str(error),
                    parent=self.window,
                )
            return None

        if x_min >= x_max:
            if show_errors:
                messagebox.showerror(
                    "Invalid x Range",
                    "x minimum must be smaller than x maximum.",
                    parent=self.window,
                )
            return None

        if not (
            MIN_PIECEWISE_POINTS
            <= point_count
            <= MAX_PIECEWISE_POINTS
        ):
            if show_errors:
                messagebox.showerror(
                    "Invalid Sample Count",
                    f"Sample points must be between "
                    f"{MIN_PIECEWISE_POINTS} and "
                    f"{MAX_PIECEWISE_POINTS}.",
                    parent=self.window,
                )
            return None

        return rules, x_min, x_max, point_count

    def _parse_rules(
        self,
        raw_rules: str,
    ) -> list[tuple[str, str]]:
        """Parse condition : expression rules."""
        parsed_rules: list[tuple[str, str]] = []

        for line_number, raw_line in enumerate(
            raw_rules.splitlines(),
            start=1,
        ):
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if ":" not in line:
                raise ValueError(
                    f"Line {line_number} must contain ':' "
                    "between its condition and expression."
                )

            condition, expression = line.split(
                ":",
                maxsplit=1,
            )

            condition = condition.strip()
            expression = expression.strip()

            if not condition or not expression:
                raise ValueError(
                    f"Line {line_number} has an empty "
                    "condition or expression."
                )

            # Validate condition syntax before plotting.
            condition_tree = ast.parse(
                condition,
                mode="eval",
            )
            self._validate_condition_tree(
                condition_tree,
            )

            parsed_rules.append(
                (condition, expression)
            )

        if not parsed_rules:
            raise ValueError(
                "Enter at least one piecewise rule."
            )

        return parsed_rules

    def _evaluate_condition(
        self,
        condition: str,
        x_value: float,
    ) -> bool:
        """Safely evaluate a condition using only x and comparisons."""
        tree = ast.parse(
            condition,
            mode="eval",
        )
        self._validate_condition_tree(tree)

        return bool(
            self._evaluate_condition_node(
                tree.body,
                x_value,
            )
        )

    def _validate_condition_tree(
        self,
        tree: ast.AST,
    ) -> None:
        """Reject unsafe or unsupported condition syntax."""
        allowed_nodes = (
            ast.Expression,
            ast.BoolOp,
            ast.UnaryOp,
            ast.Compare,
            ast.Name,
            ast.Constant,
            ast.And,
            ast.Or,
            ast.Not,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,
            ast.Eq,
            ast.NotEq,
            ast.USub,
            ast.UAdd,
        )

        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                raise ValueError(
                    "Conditions may only contain x, numbers, "
                    "comparisons, and/or/not."
                )

            if isinstance(node, ast.Name) and node.id != "x":
                raise ValueError(
                    "Only the variable x is allowed in conditions."
                )

    def _evaluate_condition_node(
        self,
        node: ast.AST,
        x_value: float,
    ) -> bool | float:
        """Evaluate one validated condition AST node."""
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, bool)):
                raise ValueError(
                    "Only numeric and boolean constants are allowed."
                )
            return node.value

        if isinstance(node, ast.Name):
            if node.id != "x":
                raise ValueError(
                    "Only x is allowed."
                )
            return x_value

        if isinstance(node, ast.UnaryOp):
            value = self._evaluate_condition_node(
                node.operand,
                x_value,
            )

            if isinstance(node.op, ast.Not):
                return not bool(value)

            if isinstance(node.op, ast.USub):
                return -float(value)

            if isinstance(node.op, ast.UAdd):
                return float(value)

        if isinstance(node, ast.BoolOp):
            values = [
                bool(
                    self._evaluate_condition_node(
                        value_node,
                        x_value,
                    )
                )
                for value_node in node.values
            ]

            if isinstance(node.op, ast.And):
                return all(values)

            if isinstance(node.op, ast.Or):
                return any(values)

        if isinstance(node, ast.Compare):
            left = self._evaluate_condition_node(
                node.left,
                x_value,
            )

            for operator, comparator_node in zip(
                node.ops,
                node.comparators,
            ):
                right = self._evaluate_condition_node(
                    comparator_node,
                    x_value,
                )

                if isinstance(operator, ast.Lt):
                    comparison = left < right
                elif isinstance(operator, ast.LtE):
                    comparison = left <= right
                elif isinstance(operator, ast.Gt):
                    comparison = left > right
                elif isinstance(operator, ast.GtE):
                    comparison = left >= right
                elif isinstance(operator, ast.Eq):
                    comparison = left == right
                elif isinstance(operator, ast.NotEq):
                    comparison = left != right
                else:
                    raise ValueError(
                        "Unsupported comparison operator."
                    )

                if not comparison:
                    return False

                left = right

            return True

        raise ValueError(
            "Unsupported condition."
        )

    @staticmethod
    def _evaluate_constant(
        expression: str,
    ) -> float:
        """Evaluate a numeric constant such as 2*pi."""
        cleaned = expression.strip()

        if not cleaned:
            raise ValueError(
                "A numeric value is required."
            )

        value = evaluate_graph_expression(
            cleaned,
            0.0,
        )

        if not math.isfinite(value):
            raise ValueError(
                "The numeric value is not finite."
            )

        return value

    @staticmethod
    def _generate_values(
        minimum: float,
        maximum: float,
        point_count: int,
    ) -> list[float]:
        """Generate evenly spaced x-values."""
        step = (
            maximum - minimum
        ) / (
            point_count - 1
        )

        return [
            minimum + index * step
            for index in range(point_count)
        ]

    def _reset_axes(self) -> None:
        """Restore axes and inherited theme."""
        theme = GRAPH_THEMES.get(
            self.theme_name,
            GRAPH_THEMES["Light"],
        )

        self.figure.set_facecolor(
            theme["figure_facecolor"]
        )
        self.axes.set_facecolor(
            theme["axes_facecolor"]
        )

        self.axes.set_title(
            "Piecewise Function",
            color=theme["text_color"],
        )
        self.axes.set_xlabel(
            "x",
            color=theme["text_color"],
        )
        self.axes.set_ylabel(
            "y",
            color=theme["text_color"],
        )

        self.axes.tick_params(
            axis="both",
            colors=theme["text_color"],
        )

        for spine in self.axes.spines.values():
            spine.set_color(
                theme["axis_color"]
            )

        self.axes.grid(
            True,
            color=theme["grid_color"],
            linestyle="--",
            linewidth=0.7,
            alpha=0.65,
        )

        self.axes.axhline(
            0,
            linewidth=0.8,
            color=theme["axis_color"],
        )
        self.axes.axvline(
            0,
            linewidth=0.8,
            color=theme["axis_color"],
        )

    def _style_legend(self, legend: Any) -> None:
        """Style the legend using the inherited theme."""
        theme = GRAPH_THEMES.get(
            self.theme_name,
            GRAPH_THEMES["Light"],
        )

        legend.get_frame().set_facecolor(
            theme["axes_facecolor"]
        )
        legend.get_frame().set_edgecolor(
            theme["axis_color"]
        )

        for text_item in legend.get_texts():
            text_item.set_color(
                theme["text_color"]
            )

    def _update_coordinates(self, event: Any) -> None:
        """Show the nearest finite piecewise point."""
        if (
            event.inaxes is not self.axes
            or event.xdata is None
            or event.ydata is None
            or not self.x_values
        ):
            self.coordinate_variable.set(
                "x: —    y: —",
            )
            return

        x_min, x_max = self.axes.get_xlim()
        y_min, y_max = self.axes.get_ylim()

        x_range = x_max - x_min
        y_range = y_max - y_min

        if x_range == 0 or y_range == 0:
            return

        nearest_index: int | None = None
        nearest_distance: float | None = None

        for index, (x_value, y_value) in enumerate(
            zip(self.x_values, self.y_values)
        ):
            if not math.isfinite(y_value):
                continue

            distance = math.hypot(
                (x_value - event.xdata) / x_range,
                (y_value - event.ydata) / y_range,
            )

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                nearest_distance = distance
                nearest_index = index

        if nearest_index is None:
            return

        self.coordinate_variable.set(
            f"x: {self.x_values[nearest_index]:.6g}    "
            f"y: {self.y_values[nearest_index]:.6g}"
        )

    def export_graph(self, file_format: str) -> None:
        """Export the piecewise graph."""
        supported_formats = {
            "png": ("PNG image", "*.png"),
            "svg": ("SVG vector image", "*.svg"),
            "pdf": ("PDF document", "*.pdf"),
        }

        if file_format not in supported_formats:
            return

        description, pattern = supported_formats[file_format]

        filepath = filedialog.asksaveasfilename(
            parent=self.window,
            title=(
                f"Export Piecewise Graph as "
                f"{file_format.upper()}"
            ),
            defaultextension=f".{file_format}",
            initialfile=f"piecewise_graph.{file_format}",
            filetypes=[
                (description, pattern),
                ("All files", "*.*"),
            ],
        )

        if not filepath:
            return

        try:
            self.figure.savefig(
                filepath,
                format=file_format,
                bbox_inches="tight",
                facecolor=self.figure.get_facecolor(),
            )

        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Export Error",
                f"Could not export the graph:\n\n{error}",
                parent=self.window,
            )
            return

        self.status_variable.set(
            f"Exported piecewise graph to {filepath}"
        )


# --------------------------------------------------
# PUBLIC FUNCTION
# --------------------------------------------------

def open_graph_window(
    parent: tk.Misc,
    initial_expression: str = "",
) -> GraphWindow:
    """Open and return a graphing window."""
    return GraphWindow(
        parent=parent,
        initial_expression=initial_expression,
    )