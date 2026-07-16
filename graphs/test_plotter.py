# test_plotter.py

import tkinter as tk

from plotter import open_graph_window


root = tk.Tk()
root.title("Graph Test")
root.geometry("300x150")


def open_test_graph() -> None:
    """Open a graph window with an initial expression."""
    open_graph_window(
        parent=root,
        initial_expression="sin(x)",
    )


tk.Button(
    root,
    text="Open Graph",
    command=open_test_graph,
).pack(
    expand=True,
)

root.mainloop()