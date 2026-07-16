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

import csv
import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from matplotlib.artist import Artist
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


# --------------------------------------------------
# DATA MODELS
# --------------------------------------------------

@dataclass
class GraphExpression:
    """Store one graph expression and its visibility state."""

    expression: str
    visible: bool = True


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
        self.riemann_method_variable = tk.StringVar(
            value="Midpoint",
        )
        self.riemann_intervals_variable = tk.IntVar(
            value=DEFAULT_RIEMANN_INTERVALS,
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

        if initial_expression.strip():
            self.add_expression()

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
        self._create_analysis_controls()
        self._create_calculus_controls()
        self._create_extrema_controls()
        self._create_inflection_controls()
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

        tk.Button(
            frame,
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
            frame,
            text="Update Selected",
            command=self.update_selected_expression,
        ).grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=2,
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

        tk.Button(
            frame,
            text="Show / Hide Selected",
            command=self.toggle_selected_expression,
        ).pack(
            fill="x",
            pady=(8, 2),
        )

        tk.Button(
            frame,
            text="Remove Selected",
            command=self.remove_selected_expression,
        ).pack(
            fill="x",
            pady=2,
        )

        tk.Button(
            frame,
            text="Open Table of Values",
            command=self.open_values_table,
        ).pack(
            fill="x",
            pady=2,
        )

        tk.Button(
            frame,
            text="Clear All",
            command=self.clear_all_expressions,
        ).pack(
            fill="x",
            pady=2,
        )

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

        tk.Button(
            frame,
            text="Find Roots and Intersections",
            command=self.find_roots_and_intersections,
        ).pack(
            fill="x",
            pady=(8, 2),
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
        """Create derivative, integration, and Riemann-sum controls."""
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
        # Derivative controls
        # ------------------------------------------

        tk.Label(
            frame,
            text="Derivative at x:",
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

        tk.Button(
            frame,
            text="Derivative + Tangent",
            command=self.show_derivative_and_tangent,
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )

        tk.Button(
            frame,
            text="Clear Tangent",
            command=self.clear_calculus_artists,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
        )

        ttk.Separator(
            frame,
            orient="horizontal",
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=8,
        )

        # ------------------------------------------
        # Integration controls
        # ------------------------------------------

        tk.Label(
            frame,
            text="Integral start a:",
        ).grid(
            row=4,
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
            row=4,
            column=1,
            pady=3,
        )

        tk.Label(
            frame,
            text="Integral end b:",
        ).grid(
            row=5,
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
            row=5,
            column=1,
            pady=3,
        )

        tk.Button(
            frame,
            text="Integrate + Shade Area",
            command=self.show_integral_area,
        ).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )

        ttk.Separator(
            frame,
            orient="horizontal",
        ).grid(
            row=7,
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
            row=8,
            column=0,
            sticky="w",
            padx=(0, 5),
            pady=3,
        )

        method_menu = ttk.Combobox(
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
        )
        method_menu.grid(
            row=8,
            column=1,
            pady=3,
        )

        tk.Label(
            frame,
            text="Intervals n:",
        ).grid(
            row=9,
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
            row=9,
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
            row=10,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=3,
        )

        tk.Button(
            frame,
            text="Show Riemann Sum",
            command=self.show_riemann_sum,
        ).grid(
            row=11,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 2),
        )

        tk.Button(
            frame,
            text="Clear Calculus Overlays",
            command=self.clear_calculus_artists,
        ).grid(
            row=12,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=2,
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

        tk.Button(
            frame,
            text="Find Local Extrema",
            command=self.find_local_extrema,
        ).pack(
            fill="x",
            pady=(8, 2),
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

        tk.Button(
            frame,
            text="Find Inflection Points",
            command=self.find_inflection_points,
        ).pack(
            fill="x",
            pady=(8, 2),
        )

        tk.Button(
            frame,
            text="Show Concavity",
            command=self.show_concavity,
        ).pack(
            fill="x",
            pady=2,
        )

        tk.Button(
            frame,
            text="Clear Inflection Overlays",
            command=self.clear_inflection_markers,
        ).pack(
            fill="x",
            pady=2,
        )

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
                label=f"y = {graph_expression.expression}",
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
            self.axes.legend()
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

        if not self._validate_expression(expression):
            return

        for stored in self.expressions:
            if stored.expression == expression:
                stored.visible = True
                self.expression_variable.set("")
                self._refresh_expression_list()
                self.plot_all_expressions()
                return

        self.expressions.append(
            GraphExpression(expression),
        )

        self.expression_variable.set("")
        self._refresh_expression_list()
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

        if not self._validate_expression(expression):
            return

        self.expressions[selected_index].expression = expression
        self.expressions[selected_index].visible = True

        self.expression_variable.set("")
        self._refresh_expression_list(selected_index)
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
        self.plot_all_expressions()

    def clear_all_expressions(self) -> None:
        """Remove all functions and markers."""
        self.expressions.clear()
        self.plotted_series.clear()

        self.expression_listbox.delete(0, tk.END)

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

            self.expression_listbox.insert(
                tk.END,
                f"{symbol}  y = {graph_expression.expression}",
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
                label=f"y = {graph_expression.expression}",
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
            self.axes.legend()
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
                y_value = evaluate_graph_expression(
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
            y_value = evaluate_graph_expression(
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

        self.axes.legend()
        self.canvas.draw_idle()

        self.coordinate_variable.set(
            f"x: {x_value:.8g}    y: {y_value:.8g}"
        )
        self.status_variable.set(
            f"Derivative of y = {expression} at x = "
            f"{x_value:.8g} is approximately {slope:.8g}."
        )

    @staticmethod
    def _numerical_derivative(
        expression: str,
        x_value: float,
    ) -> float:
        """Estimate f'(x) with a central difference formula."""
        step = DERIVATIVE_STEP * max(1.0, abs(x_value))

        left_value = evaluate_graph_expression(
            expression,
            x_value - step,
        )
        right_value = evaluate_graph_expression(
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
                y_value = evaluate_graph_expression(
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
            midpoint_y = evaluate_graph_expression(
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

        self.axes.legend()
        self.canvas.draw_idle()

        original_a = float(self.integral_a_variable.get())
        original_b = float(self.integral_b_variable.get())

        self.status_variable.set(
            f"Integral of y = {expression} from "
            f"{original_a:.8g} to {original_b:.8g} "
            f"is approximately {integral_value:.10g}."
        )

    @staticmethod
    def _simpson_integral(
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

        first_value = evaluate_graph_expression(
            expression,
            lower_bound,
        )
        final_value = evaluate_graph_expression(
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
            y_value = evaluate_graph_expression(
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
            midpoint_y = evaluate_graph_expression(
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

        self.axes.legend()
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

                y_left = evaluate_graph_expression(
                    expression,
                    x_left,
                )
                y_right = evaluate_graph_expression(
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

            sample_y = evaluate_graph_expression(
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
                extremum_y = evaluate_graph_expression(
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
                inflection_y = evaluate_graph_expression(
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
                y_value = evaluate_graph_expression(
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

        self.axes.legend()
        self.canvas.draw_idle()

        self.status_variable.set(
            f"Displayed concavity regions for y = {expression}."
        )

    @staticmethod
    def _numerical_second_derivative(
        expression: str,
        x_value: float,
    ) -> float:
        """Estimate f''(x) with a central second-difference formula."""
        step = SECOND_DERIVATIVE_STEP * max(1.0, abs(x_value))

        left_value = evaluate_graph_expression(
            expression,
            x_value - step,
        )
        center_value = evaluate_graph_expression(
            expression,
            x_value,
        )
        right_value = evaluate_graph_expression(
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
                    root_y = evaluate_graph_expression(
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
                first_result = evaluate_graph_expression(
                    first_expression.expression,
                    intersection_x,
                )
                second_result = evaluate_graph_expression(
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
                result = evaluate_graph_expression(
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
                result = evaluate_graph_expression(
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