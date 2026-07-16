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
- Matplotlib navigation toolbar
- Safe expression evaluation through graphs.evaluator
"""

import math
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox
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

# Values beyond this magnitude are treated as invalid graph points.
MAX_ABSOLUTE_Y = 1_000_000.0

# Maximum normalized distance allowed when clicking near a curve.
POINT_SELECTION_THRESHOLD = 0.05

# Delay before live preview updates after typing.
LIVE_UPDATE_DELAY_MS = 350

# Values with a magnitude below this number may be considered zero.
ROOT_Y_TOLERANCE = 1e-7

# Used when removing duplicate roots and intersections.
POINT_DUPLICATE_TOLERANCE = 1e-5


# --------------------------------------------------
# DATA MODELS
# --------------------------------------------------

@dataclass
class GraphExpression:
    """Store one expression and whether it is currently visible."""

    expression: str
    visible: bool = True


@dataclass
class SelectedPoint:
    """Store the nearest sampled point selected by the user."""

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
# GRAPH WINDOW
# --------------------------------------------------

class GraphWindow:
    """Interactive graph window for one or more mathematical functions."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_expression: str = "",
    ) -> None:
        """Create the graphing window."""
        self.window = tk.Toplevel(parent)
        self.window.title("Function Graph")
        self.window.geometry("1150x750")
        self.window.minsize(850, 600)

        # Stored graph expressions.
        self.expressions: list[GraphExpression] = []

        # Visible plotted data:
        # (GraphExpression, x values, y values)
        self.plotted_series: list[
            tuple[GraphExpression, list[float], list[float]]
        ] = []

        # Detected roots and intersections.
        self.special_points: list[SpecialPoint] = []

        # Matplotlib artists for detected roots and intersections.
        self.special_point_artists: list[Artist] = []

        # Matplotlib objects for a manually selected point.
        self.point_marker: Artist | None = None
        self.point_annotation: Artist | None = None

        # Tkinter after() identifier used by live preview.
        self.live_update_job: str | None = None

        # Tkinter variables.
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
        """Create the graph window layout."""
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
        self._create_analysis_controls()
        self._create_range_controls()
        self._create_graph()
        self._create_status_bar()

    def _create_expression_controls(self) -> None:
        """Create expression input widgets."""
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

        tk.Checkbutton(
            expression_frame,
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

        expression_frame.columnconfigure(1, weight=1)

    def _create_expression_list(self) -> None:
        """Create the stored-functions list."""
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
            width=34,
            height=9,
            exportselection=False,
        )
        self.expression_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        expression_scrollbar = tk.Scrollbar(
            list_container,
            orient="vertical",
            command=self.expression_listbox.yview,
        )
        expression_scrollbar.pack(
            side="right",
            fill="y",
        )

        self.expression_listbox.configure(
            yscrollcommand=expression_scrollbar.set,
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

    def _create_analysis_controls(self) -> None:
        """Create root and intersection analysis controls."""
        analysis_frame = tk.LabelFrame(
            self.controls_frame,
            text="Roots and Intersections",
            padx=8,
            pady=8,
        )
        analysis_frame.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        analysis_container = tk.Frame(analysis_frame)
        analysis_container.pack(
            fill="both",
            expand=True,
        )

        self.analysis_listbox = tk.Listbox(
            analysis_container,
            width=34,
            height=8,
            exportselection=False,
        )
        self.analysis_listbox.pack(
            side="left",
            fill="both",
            expand=True,
        )

        analysis_scrollbar = tk.Scrollbar(
            analysis_container,
            orient="vertical",
            command=self.analysis_listbox.yview,
        )
        analysis_scrollbar.pack(
            side="right",
            fill="y",
        )

        self.analysis_listbox.configure(
            yscrollcommand=analysis_scrollbar.set,
        )

        tk.Button(
            analysis_frame,
            text="Find Roots and Intersections",
            command=self.find_roots_and_intersections,
        ).pack(
            fill="x",
            pady=(8, 2),
        )

        tk.Button(
            analysis_frame,
            text="Clear Analysis Markers",
            command=self.clear_analysis_markers,
        ).pack(
            fill="x",
            pady=2,
        )

    def _create_range_controls(self) -> None:
        """Create graph-range and sample-count inputs."""
        range_frame = tk.LabelFrame(
            self.controls_frame,
            text="Graph Settings",
            padx=8,
            pady=8,
        )
        range_frame.pack(fill="x")

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

        tk.Button(
            range_frame,
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
    # LIVE PREVIEW
    # --------------------------------------------------

    def _schedule_live_update(
        self,
        *_args: object,
    ) -> None:
        """Schedule a live preview after typing stops briefly."""
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
        """Add a new stored graph expression."""
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

        for stored_expression in self.expressions:
            if stored_expression.expression == expression:
                stored_expression.visible = True
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
        """Replace the selected graph expression."""
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

        selected_expression = self.expressions[selected_index]
        selected_expression.visible = not selected_expression.visible

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
        """Remove every function and graph marker."""
        self.expressions.clear()
        self.plotted_series.clear()

        self.expression_listbox.delete(0, tk.END)

        self._clear_point_marker(redraw=False)
        self.clear_analysis_markers(redraw=False)

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
        """Refresh the function listbox."""
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
        """Evaluate one function across the sampled x-values."""
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
    # ROOTS AND INTERSECTIONS
    # --------------------------------------------------

    def find_roots_and_intersections(self) -> None:
        """Find and display roots and pairwise intersections."""
        if not self.plotted_series:
            messagebox.showinfo(
                "No Functions",
                "Plot at least one visible function first.",
                parent=self.window,
            )
            return

        self.clear_analysis_markers(redraw=False)

        detected_points: list[SpecialPoint] = []

        # Find roots for every visible function.
        for graph_expression, x_values, y_values in self.plotted_series:
            roots = self._find_roots_for_series(
                graph_expression.expression,
                x_values,
                y_values,
            )
            detected_points.extend(roots)

        # Find pairwise intersections.
        series_count = len(self.plotted_series)

        for first_index in range(series_count):
            for second_index in range(
                first_index + 1,
                series_count,
            ):
                first_series = self.plotted_series[first_index]
                second_series = self.plotted_series[second_index]

                intersections = self._find_intersections_between_series(
                    first_series,
                    second_series,
                )

                detected_points.extend(intersections)

        self.special_points = self._deduplicate_special_points(
            detected_points,
        )

        self._refresh_analysis_list()
        self._draw_analysis_markers()

        root_count = sum(
            point.point_type == "root"
            for point in self.special_points
        )
        intersection_count = sum(
            point.point_type == "intersection"
            for point in self.special_points
        )

        self.status_variable.set(
            f"Found {root_count} root(s) and "
            f"{intersection_count} intersection(s)."
        )

    def _find_roots_for_series(
        self,
        expression: str,
        x_values: list[float],
        y_values: list[float],
    ) -> list[SpecialPoint]:
        """Find approximate roots from sampled function data."""
        roots: list[SpecialPoint] = []

        for index in range(len(x_values) - 1):
            x1 = x_values[index]
            x2 = x_values[index + 1]
            y1 = y_values[index]
            y2 = y_values[index + 1]

            if not math.isfinite(y1) or not math.isfinite(y2):
                continue

            # Sampled point is already very close to zero.
            if abs(y1) <= ROOT_Y_TOLERANCE:
                roots.append(
                    SpecialPoint(
                        point_type="root",
                        x=x1,
                        y=0.0,
                        first_expression=expression,
                    )
                )
                continue

            # A sign change indicates a root between the samples.
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
                        point_type="root",
                        x=root_x,
                        y=root_y,
                        first_expression=expression,
                    )
                )

        # Check the final sampled point.
        if x_values and y_values:
            final_y = y_values[-1]

            if (
                math.isfinite(final_y)
                and abs(final_y) <= ROOT_Y_TOLERANCE
            ):
                roots.append(
                    SpecialPoint(
                        point_type="root",
                        x=x_values[-1],
                        y=0.0,
                        first_expression=expression,
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
        """Find intersections between two sampled functions."""
        first_expression, first_x, first_y = first_series
        second_expression, second_x, second_y = second_series

        point_count = min(
            len(first_x),
            len(second_x),
            len(first_y),
            len(second_y),
        )

        intersections: list[SpecialPoint] = []

        for index in range(point_count - 1):
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
                    point_type="intersection",
                    x=intersection_x,
                    y=intersection_y,
                    first_expression=first_expression.expression,
                    second_expression=second_expression.expression,
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
        """Estimate where a line segment crosses y=0."""
        denominator = y2 - y1

        if denominator == 0:
            return (x1 + x2) / 2

        return x1 - y1 * (x2 - x1) / denominator

    def _deduplicate_special_points(
        self,
        points: list[SpecialPoint],
    ) -> list[SpecialPoint]:
        """Remove duplicate or near-duplicate analysis points."""
        unique_points: list[SpecialPoint] = []

        for point in sorted(
            points,
            key=lambda item: (
                item.point_type,
                item.x,
                item.y,
            ),
        ):
            duplicate_found = False

            for existing_point in unique_points:
                same_type = (
                    point.point_type
                    == existing_point.point_type
                )

                same_first_expression = (
                    point.first_expression
                    == existing_point.first_expression
                )

                same_second_expression = (
                    point.second_expression
                    == existing_point.second_expression
                )

                close_x = math.isclose(
                    point.x,
                    existing_point.x,
                    abs_tol=POINT_DUPLICATE_TOLERANCE,
                )

                close_y = math.isclose(
                    point.y,
                    existing_point.y,
                    abs_tol=POINT_DUPLICATE_TOLERANCE,
                )

                if (
                    same_type
                    and same_first_expression
                    and same_second_expression
                    and close_x
                    and close_y
                ):
                    duplicate_found = True
                    break

            if not duplicate_found:
                unique_points.append(point)

        return unique_points

    def _refresh_analysis_list(self) -> None:
        """Display detected roots and intersections."""
        self.analysis_listbox.delete(0, tk.END)

        for special_point in self.special_points:
            self.analysis_listbox.insert(
                tk.END,
                special_point.description(),
            )

        if not self.special_points:
            self.analysis_listbox.insert(
                tk.END,
                "No roots or intersections detected.",
            )

    def _draw_analysis_markers(self) -> None:
        """Draw root and intersection markers."""
        self._clear_analysis_artists(redraw=False)

        for point in self.special_points:
            if point.point_type == "root":
                marker = self.axes.scatter(
                    [point.x],
                    [point.y],
                    marker="o",
                    s=55,
                    zorder=9,
                    label="_nolegend_",
                )
            else:
                marker = self.axes.scatter(
                    [point.x],
                    [point.y],
                    marker="X",
                    s=75,
                    zorder=9,
                    label="_nolegend_",
                )

            self.special_point_artists.append(marker)

        self.canvas.draw_idle()

    def _select_analysis_result(
        self,
        _event: tk.Event,
    ) -> None:
        """Highlight the selected root or intersection."""
        selection = self.analysis_listbox.curselection()

        if not selection:
            return

        index = int(selection[0])

        if index >= len(self.special_points):
            return

        point = self.special_points[index]

        expression_name = point.first_expression

        if point.second_expression is not None:
            expression_name = (
                f"{point.first_expression} ∩ "
                f"{point.second_expression}"
            )

        selected_point = SelectedPoint(
            expression=expression_name,
            x=point.x,
            y=point.y,
            distance=0.0,
        )

        self._show_point_marker(selected_point)

    def clear_analysis_markers(
        self,
        redraw: bool = True,
    ) -> None:
        """Clear detected roots, intersections, and their list."""
        self.special_points.clear()
        self.analysis_listbox.delete(0, tk.END)

        self._clear_analysis_artists(
            redraw=redraw,
        )

    def _clear_analysis_artists(
        self,
        redraw: bool = True,
    ) -> None:
        """Safely remove Matplotlib analysis markers."""
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

        selected_point = self._find_nearest_plotted_point(
            float(event.xdata),
            float(event.ydata),
        )

        if selected_point is None:
            self._clear_point_marker()

            self.status_variable.set(
                "No curve was close enough to the selected point."
            )
            return

        self._show_point_marker(selected_point)

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

        nearest_point: SelectedPoint | None = None

        for graph_expression, x_values, y_values in self.plotted_series:
            for x_value, y_value in zip(
                x_values,
                y_values,
            ):
                if not math.isfinite(y_value):
                    continue

                x_distance = (
                    x_value - click_x
                ) / x_range

                y_distance = (
                    y_value - click_y
                ) / y_range

                distance = math.hypot(
                    x_distance,
                    y_distance,
                )

                if (
                    nearest_point is None
                    or distance < nearest_point.distance
                ):
                    nearest_point = SelectedPoint(
                        expression=graph_expression.expression,
                        x=x_value,
                        y=y_value,
                        distance=distance,
                    )

        if nearest_point is None:
            return None

        if nearest_point.distance > POINT_SELECTION_THRESHOLD:
            return None

        return nearest_point

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

        annotation_text = (
            f"y = {point.expression}\n"
            f"x = {point.x:.8g}\n"
            f"y = {point.y:.8g}"
        )

        self.point_annotation = self.axes.annotate(
            annotation_text,
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
        """Safely remove the manual point marker."""
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
    # GRAPH SETTINGS
    # --------------------------------------------------

    def _read_graph_settings(
        self,
        *,
        show_errors: bool = True,
    ) -> tuple[float, float, int] | None:
        """Read and validate the graph settings."""
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
        """Restore the configured range and automatic y-range."""
        self.plot_all_expressions()

    # --------------------------------------------------
    # EXPRESSION VALIDATION
    # --------------------------------------------------

    def _validate_expression(self, expression: str) -> bool:
        """Validate an expression before permanently adding it."""
        test_values = (-2.0, -1.0, 0.0, 1.0, 2.0)
        last_error: Exception | None = None

        for x_value in test_values:
            try:
                result = evaluate_graph_expression(
                    expression,
                    x_value,
                )

                if math.isfinite(result):
                    return True

            except Exception as error:
                last_error = error

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
        """Restore graph labels, axes, and grid."""
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
        """Toggle visibility when a function is double-clicked."""
        self.toggle_selected_expression()
        return "break"


# --------------------------------------------------
# PUBLIC FUNCTION
# --------------------------------------------------

def open_graph_window(
    parent: tk.Misc,
    initial_expression: str = "",
) -> GraphWindow:
    """Open and return a new graphing window."""
    return GraphWindow(
        parent=parent,
        initial_expression=initial_expression,
    )