"""
graphs/plotter.py

Creates a Tkinter graphing window with an embedded Matplotlib plot.

The graph window accepts expressions containing x, such as:

    sin(x)
    x^2
    x^3 - 2*x + 1
    sqrt(abs(x))

Expression evaluation is handled safely by graphs/evaluator.py.
"""

import math
import tkinter as tk
from tkinter import messagebox

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


# --------------------------------------------------
# GRAPH WINDOW
# --------------------------------------------------

class GraphWindow:
    """
    A separate Tkinter window for plotting mathematical expressions.
    """

    def __init__(
        self,
        parent: tk.Misc,
        initial_expression: str = "",
    ) -> None:
        """
        Create the graphing window.

        Args:
            parent:
                The calculator's main Tkinter window.

            initial_expression:
                Optional expression inserted into the graph input field.
        """
        self.window = tk.Toplevel(parent)
        self.window.title("Function Graph")
        self.window.geometry("900x650")
        self.window.minsize(700, 500)

        # Store the graph expression in a Tkinter variable.
        self.expression_variable = tk.StringVar(
            value=initial_expression,
        )

        self.x_min_variable = tk.StringVar(
            value=str(DEFAULT_X_MIN),
        )

        self.x_max_variable = tk.StringVar(
            value=str(DEFAULT_X_MAX),
        )

        self.status_variable = tk.StringVar(
            value="Enter an expression and press Plot.",
        )

        # Build the interface.
        self._create_controls()
        self._create_graph()
        self._create_status_bar()

        # Allow Enter to trigger plotting.
        self.window.bind("<Return>", self._plot_from_event)

        # Focus the expression field when the window opens.
        self.expression_entry.focus_set()

        # Plot immediately when an initial expression was provided.
        if initial_expression.strip():
            self.plot_expression()

    # --------------------------------------------------
    # UI CREATION
    # --------------------------------------------------

    def _create_controls(self) -> None:
        """Create the expression and graph-range controls."""
        controls_frame = tk.Frame(self.window)
        controls_frame.pack(
            fill="x",
            padx=10,
            pady=10,
        )

        # Expression label and input.
        tk.Label(
            controls_frame,
            text="y =",
            font=("Arial", 12, "bold"),
        ).grid(
            row=0,
            column=0,
            padx=(0, 5),
            pady=5,
        )

        self.expression_entry = tk.Entry(
            controls_frame,
            textvariable=self.expression_variable,
            font=("Arial", 12),
        )

        self.expression_entry.grid(
            row=0,
            column=1,
            columnspan=5,
            sticky="ew",
            padx=(0, 10),
            pady=5,
        )

        # X minimum input.
        tk.Label(
            controls_frame,
            text="x min:",
        ).grid(
            row=1,
            column=0,
            padx=(0, 5),
            pady=5,
        )

        tk.Entry(
            controls_frame,
            textvariable=self.x_min_variable,
            width=10,
        ).grid(
            row=1,
            column=1,
            sticky="w",
            pady=5,
        )

        # X maximum input.
        tk.Label(
            controls_frame,
            text="x max:",
        ).grid(
            row=1,
            column=2,
            padx=(10, 5),
            pady=5,
        )

        tk.Entry(
            controls_frame,
            textvariable=self.x_max_variable,
            width=10,
        ).grid(
            row=1,
            column=3,
            sticky="w",
            pady=5,
        )

        # Plot button.
        tk.Button(
            controls_frame,
            text="Plot",
            command=self.plot_expression,
            width=10,
        ).grid(
            row=1,
            column=4,
            padx=(10, 5),
            pady=5,
        )

        # Clear graph button.
        tk.Button(
            controls_frame,
            text="Clear",
            command=self.clear_graph,
            width=10,
        ).grid(
            row=1,
            column=5,
            padx=5,
            pady=5,
        )

        # Allow the expression input to expand horizontally.
        controls_frame.columnconfigure(1, weight=1)

    def _create_graph(self) -> None:
        """Create and embed the Matplotlib graph."""
        graph_frame = tk.Frame(self.window)
        graph_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10),
        )

        # Create a Matplotlib figure.
        self.figure = Figure(
            figsize=(8, 5),
            dpi=100,
        )

        # Add one plotting area.
        self.axes = self.figure.add_subplot(111)

        # Apply initial labels and grid.
        self._reset_axes()

        # Embed the figure inside Tkinter.
        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=graph_frame,
        )

        self.canvas.draw()

        self.canvas.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

        # Add Matplotlib's built-in navigation toolbar.
        # This provides zoom, pan, reset, and save controls.
        self.toolbar = NavigationToolbar2Tk(
            self.canvas,
            graph_frame,
            pack_toolbar=False,
        )

        self.toolbar.update()
        self.toolbar.pack(
            fill="x",
        )

    def _create_status_bar(self) -> None:
        """Create the graph window's status bar."""
        status_label = tk.Label(
            self.window,
            textvariable=self.status_variable,
            anchor="w",
            relief="sunken",
        )

        status_label.pack(
            fill="x",
            side="bottom",
        )

    # --------------------------------------------------
    # GRAPH OPERATIONS
    # --------------------------------------------------

    def plot_expression(self) -> None:
        """Evaluate and plot the current mathematical expression."""
        expression = self.expression_variable.get().strip()

        if not expression:
            messagebox.showwarning(
                "Missing Expression",
                "Enter an expression containing x.",
                parent=self.window,
            )
            return

        try:
            x_min = float(self.x_min_variable.get())
            x_max = float(self.x_max_variable.get())

        except ValueError:
            messagebox.showerror(
                "Invalid Range",
                "The x minimum and maximum must be valid numbers.",
                parent=self.window,
            )
            return

        if x_min >= x_max:
            messagebox.showerror(
                "Invalid Range",
                "The x minimum must be smaller than the x maximum.",
                parent=self.window,
            )
            return

        # Generate evenly spaced x-values without requiring NumPy.
        x_values = self._generate_x_values(
            x_min=x_min,
            x_max=x_max,
            point_count=DEFAULT_POINT_COUNT,
        )

        y_values: list[float] = []
        valid_point_count = 0

        try:
            for x_value in x_values:
                try:
                    y_value = evaluate_graph_expression(
                        expression,
                        x_value,
                    )

                    # Reject infinite and NaN values.
                    if not math.isfinite(y_value):
                        y_values.append(float("nan"))
                        continue

                    y_values.append(y_value)
                    valid_point_count += 1

                except (
                    ArithmeticError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    # Undefined points become gaps in the graph.
                    #
                    # Example:
                    # sqrt(x) for negative x-values.
                    y_values.append(float("nan"))

        except SyntaxError as error:
            messagebox.showerror(
                "Invalid Expression",
                f"The expression contains invalid syntax:\n\n{error}",
                parent=self.window,
            )
            return

        if valid_point_count == 0:
            messagebox.showerror(
                "No Valid Points",
                "The expression did not produce any valid graph points.",
                parent=self.window,
            )
            return

        # Clear the previous graph.
        self.axes.clear()

        # Plot the new expression.
        self.axes.plot(
            x_values,
            y_values,
            label=f"y = {expression}",
        )

        # Draw x-axis and y-axis reference lines.
        self.axes.axhline(
            y=0,
            linewidth=0.8,
        )

        self.axes.axvline(
            x=0,
            linewidth=0.8,
        )

        self.axes.set_title(
            f"y = {expression}",
        )

        self.axes.set_xlabel("x")
        self.axes.set_ylabel("y")
        self.axes.grid(True)
        self.axes.legend()

        # Keep the requested x-range visible.
        self.axes.set_xlim(x_min, x_max)

        # Improve layout so labels are not clipped.
        self.figure.tight_layout()

        # Redraw the embedded canvas.
        self.canvas.draw()

        self.status_variable.set(
            f"Plotted {valid_point_count} valid points "
            f"from x={x_min:g} to x={x_max:g}."
        )

    def clear_graph(self) -> None:
        """Clear the graph and reset its labels."""
        self.axes.clear()
        self._reset_axes()
        self.canvas.draw()

        self.status_variable.set("Graph cleared.")

    def _reset_axes(self) -> None:
        """Restore the default graph appearance."""
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

    def _plot_from_event(
        self,
        _event: tk.Event,
    ) -> str:
        """Plot when Enter is pressed inside the graph window."""
        self.plot_expression()
        return "break"

    @staticmethod
    def _generate_x_values(
        x_min: float,
        x_max: float,
        point_count: int,
    ) -> list[float]:
        """
        Generate evenly spaced x-values.

        This avoids requiring NumPy for the first graphing version.
        """
        if point_count < 2:
            raise ValueError("At least two graph points are required.")

        step = (x_max - x_min) / (point_count - 1)

        return [
            x_min + index * step
            for index in range(point_count)
        ]


# --------------------------------------------------
# PUBLIC FUNCTION
# --------------------------------------------------

def open_graph_window(
    parent: tk.Misc,
    initial_expression: str = "",
) -> GraphWindow:
    """
    Open and return a graphing window.

    Args:
        parent:
            The calculator's main Tkinter window.

        initial_expression:
            Optional expression to graph immediately.
    """
    return GraphWindow(
        parent=parent,
        initial_expression=initial_expression,
    )