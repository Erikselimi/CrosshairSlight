"""Reusable widgets for the main window."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk
from typing import Callable

import theme
from crosshair_data import Crosshair
from crosshair_render import draw_on_canvas, fit_scale


class ToolTip:
    """A small hint that appears after the pointer rests on a widget."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.pending: str | None = None
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._destroy, add="+")

    def _schedule(self, _event=None) -> None:
        if self.pending is None:
            self.pending = self.widget.after(500, self._show)

    def _show(self) -> None:
        self.pending = None
        try:
            if self.window is not None or not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
            self.window = tk.Toplevel(self.widget)
            self.window.wm_overrideredirect(True)
            self.window.wm_geometry(f"+{x}+{y}")
            tk.Label(self.window, text=self.text, bg=theme.TEXT_STRONG, fg=theme.PANEL, padx=9, pady=6,
                     font=(theme.FONT, 9), wraplength=280, justify="left").pack()
        except tk.TclError:
            self.window = None

    def _hide(self, _event=None) -> None:
        if self.pending is not None:
            try:
                self.widget.after_cancel(self.pending)
            except tk.TclError:
                pass
            self.pending = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None

    def _destroy(self, event) -> None:
        if event.widget is self.widget:
            self._hide()


class RoundedPanel(tk.Canvas):
    """A rounded card with a regular ttk frame inside for its contents."""

    def __init__(self, parent: tk.Widget, padding: int | tuple[int, ...] = 0, radius: int = 16) -> None:
        super().__init__(parent, bg=theme.BG, highlightthickness=0, bd=0)
        self.radius = radius
        self.body = ttk.Frame(self, style="Panel.TFrame", padding=padding)
        self._window = self.create_window(radius, radius, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)

    def _resize(self, event) -> None:
        radius = min(self.radius, event.width // 2, event.height // 2)
        self.coords(self._window, radius, radius)
        self.itemconfigure(self._window, width=max(1, event.width - 2 * radius),
                           height=max(1, event.height - 2 * radius))
        self.delete("rounded-panel")
        color = theme.PANEL
        if radius == 0:
            self.create_rectangle(0, 0, event.width, event.height, fill=color, outline=color,
                                  tags="rounded-panel")
        else:
            self.create_rectangle(radius, 0, event.width - radius, event.height,
                                  fill=color, outline=color, tags="rounded-panel")
            self.create_rectangle(0, radius, event.width, event.height - radius,
                                  fill=color, outline=color, tags="rounded-panel")
            for x, y in (
                (0, 0), (event.width - 2 * radius, 0),
                (0, event.height - 2 * radius), (event.width - 2 * radius, event.height - 2 * radius),
            ):
                self.create_oval(x, y, x + 2 * radius, y + 2 * radius,
                                 fill=color, outline=color, tags="rounded-panel")
        self.tag_lower("rounded-panel")


class ScrollFrame(ttk.Frame):
    """A vertically scrolling container; the scrollbar only appears when the content is taller."""

    def __init__(self, parent: tk.Widget, padding: int = 0) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.canvas = tk.Canvas(self, bg=theme.PANEL, highlightthickness=0, bd=0, yscrollincrement=24)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, style="Panel.TFrame", padding=padding)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._scrollbar_shown = False
        self.inner.bind("<Configure>", lambda _event: self._update())
        self.canvas.bind("<Configure>", self._on_canvas)

    def _on_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._update()

    def _update(self) -> None:
        content = self.inner.winfo_reqheight()
        visible = self.canvas.winfo_height()
        self.canvas.configure(scrollregion=(0, 0, 1, max(content, visible)))
        needed = content > visible > 1
        if needed and not self._scrollbar_shown:
            self.scrollbar.pack(side="right", fill="y")
            self._scrollbar_shown = True
        elif not needed and self._scrollbar_shown:
            self.scrollbar.pack_forget()
            self._scrollbar_shown = False
            self.canvas.yview_moveto(0)

    def scroll_by(self, steps: int) -> None:
        if self._scrollbar_shown:
            self.canvas.yview_scroll(steps, "units")


def install_wheel_scrolling(root: tk.Misc) -> None:
    """Scroll whichever ScrollFrame is under the pointer when the mouse wheel turns."""

    def on_wheel(event) -> None:
        try:
            widget = root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        while widget is not None:
            if isinstance(widget, ScrollFrame):
                steps = int(-event.delta / 120) or (-1 if event.delta > 0 else 1)
                widget.scroll_by(steps)
                return
            widget = getattr(widget, "master", None)

    root.bind_all("<MouseWheel>", on_wheel, add="+")


class StepSlider(ttk.Frame):
    """Label + value, a slider, and -/+ buttons for exact one-pixel steps."""

    def __init__(self, parent: tk.Widget, label: str, variable: tk.IntVar, low: int, high: int,
                 suffix: str = "", hint: str = "", command: Callable[[], None] | None = None,
                 on_reset: Callable[[], None] | None = None) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.variable = variable
        self.low = low
        self.high = high
        self.suffix = suffix
        self.command = command
        self.on_reset = on_reset
        self._busy = False
        self._enabled = True

        top = ttk.Frame(self, style="Panel.TFrame")
        top.pack(fill="x")
        self.label = ttk.Label(top, text=label, style="Panel.TLabel")
        self.label.pack(side="left")
        self.value_label = ttk.Label(top, text="", style="Value.TLabel")
        self.value_label.pack(side="right")

        row = ttk.Frame(self, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        self.minus = ttk.Button(row, text="−", style="Step.TButton", width=2, takefocus=False,
                                command=lambda: self.nudge(-1))
        self.minus.pack(side="left")
        self.plus = ttk.Button(row, text="+", style="Step.TButton", width=2, takefocus=False,
                               command=lambda: self.nudge(1))
        self.plus.pack(side="right")
        self.scale = ttk.Scale(row, from_=low, to=high, variable=variable, command=self._scale_moved)
        self.scale.pack(side="left", fill="x", expand=True, padx=8)
        self.scale.bind("<Double-Button-1>", self._reset)
        if hint:
            ToolTip(self.label, hint + " Double-click the slider to reset it.")
        self.refresh()

    def _scale_moved(self, value: str) -> None:
        if self._busy:
            return
        number = max(self.low, min(self.high, int(round(float(value)))))
        self._busy = True
        try:
            if self.variable.get() != number:
                self.variable.set(number)
        finally:
            self._busy = False
        self.refresh()
        if self.command:
            self.command()

    def nudge(self, amount: int) -> None:
        number = max(self.low, min(self.high, int(round(float(self.variable.get()))) + amount))
        self.variable.set(number)
        self.refresh()
        if self.command:
            self.command()

    def _reset(self, _event=None) -> str:
        if self.on_reset and self._enabled:
            self.on_reset()
        return "break"

    def refresh(self) -> None:
        self.value_label.configure(text=f"{int(round(float(self.variable.get())))}{self.suffix}")

    def set_label(self, text: str) -> None:
        if self.label.cget("text") != text:
            self.label.configure(text=text)

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (self.scale, self.minus, self.plus):
            widget.state(state)
        self.label.configure(style="Panel.TLabel" if enabled else "Dim.TLabel")
        self.value_label.configure(style="Value.TLabel" if enabled else "DimValue.TLabel")


class SwatchRow(ttk.Frame):
    """A row of circular color swatches; clicking one calls ``command(hex_color)``."""

    def __init__(self, parent: tk.Widget, colors: list[tuple[str, str]], command: Callable[[str], None],
                 size: int = 22, gap: int = 6) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self._cells: dict[str, tuple[tk.Canvas, int]] = {}
        self._command = command
        self._enabled = True
        for name, value in colors:
            cell = tk.Canvas(self, width=size, height=size, bg=theme.PANEL, cursor="hand2",
                             highlightthickness=0, bd=0)
            cell.pack(side="left", padx=(0, gap))
            inset = 2
            dot = cell.create_oval(inset, inset, size - inset, size - inset,
                                   fill=value, outline=theme.BORDER, width=1)
            cell.bind("<Button-1>", lambda _event, color=value: self._choose(color))
            ToolTip(cell, name)
            self._cells[value.upper()] = (cell, dot)

    def _choose(self, color: str) -> None:
        if self._enabled:
            self._command(color)

    def select(self, color: str | None) -> None:
        chosen = (color or "").upper()
        for value, (cell, dot) in self._cells.items():
            cell.itemconfigure(dot, outline=theme.ACCENT if value == chosen else theme.BORDER,
                               width=2 if value == chosen else 1)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        for cell, _ in self._cells.values():
            cell.configure(cursor="hand2" if enabled else "")


class ColorField(ttk.Frame):
    """A complete color editor: swatches, a HEX box, a color picker and a copy button."""

    def __init__(self, parent: tk.Widget, color: str, on_change: Callable[[str], None],
                 colors: list[tuple[str, str]] | None = None, *,
                 on_invalid: Callable[[str], None] | None = None,
                 on_status: Callable[[str], None] | None = None,
                 title: str = "Choose a color", size: int = 24, gap: int = 7,
                 pick_text: str = "Pick color…", show_copy: bool = True) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self._on_change = on_change
        self._on_invalid = on_invalid
        self._on_status = on_status
        self._title = title
        self.color = color
        self.pick_button: ttk.Button | None = None
        self.copy_button: ttk.Button | None = None

        self.swatches: SwatchRow | None = None
        if colors:
            self.swatches = SwatchRow(self, colors, self._picked, size=size, gap=gap)
            self.swatches.pack(anchor="w")
            self.swatches.select(color)

        row = ttk.Frame(self, style="Panel.TFrame")
        row.pack(fill="x", pady=(9, 0))
        ttk.Label(row, text="HEX", style="PanelMuted.TLabel").pack(side="left", padx=(0, 8))
        self.hex_var = tk.StringVar(value=color)
        self.entry = ttk.Entry(row, textvariable=self.hex_var, width=9)
        self.entry.pack(side="left")
        self.entry.bind("<Return>", self._commit)
        self.entry.bind("<FocusOut>", self._commit)
        self.pick_button = ttk.Button(row, text=pick_text, style="Small.TButton", command=self.pick)
        self.pick_button.pack(side="left", padx=(8, 0))
        if show_copy:
            self.copy_button = ttk.Button(row, text="Copy", style="Small.TButton", command=self.copy)
            self.copy_button.pack(side="left", padx=(6, 0))

    def _picked(self, color: str) -> None:
        self.hex_var.set(color.upper())
        self._on_change(color)

    def _commit(self, _event=None) -> None:
        text = self.hex_var.get().strip().lstrip("#")
        if len(text) == 6 and all(character in "0123456789abcdefABCDEF" for character in text):
            clean = "#" + text.upper()
            self.hex_var.set(clean)
            self._on_change(clean)
        else:
            self.hex_var.set(self.color)
            if text and self._on_invalid is not None:
                self._on_invalid("Enter a color like #00FFFF")

    def pick(self) -> None:
        chosen = colorchooser.askcolor(color=self.color, title=self._title, parent=self.winfo_toplevel())[1]
        if chosen:
            self._picked(chosen.upper())

    def copy(self) -> None:
        top = self.winfo_toplevel()
        top.clipboard_clear()
        top.clipboard_append(self.color)
        if self._on_status is not None:
            self._on_status(f"Copied {self.color}")

    def set_color(self, color: str) -> None:
        self.color = color
        if self.swatches is not None:
            self.swatches.select(color)
        if self.focus_get() is not self.entry:
            self.hex_var.set(color)

    def set_enabled(self, enabled: bool) -> None:
        self.entry.configure(state="normal" if enabled else "disabled")
        for button in (self.pick_button, self.copy_button):
            if button is not None:
                button.state(["!disabled"] if enabled else ["disabled"])
        if self.swatches is not None:
            self.swatches.set_enabled(enabled)


class PresetGrid(ttk.Frame):
    """Clickable thumbnails of every preset, drawn by the same renderer as the preview."""

    CELL_W = 84
    CELL_H = 84
    HALF_EXTENT = 21

    def __init__(self, parent: tk.Widget, presets: dict[str, Crosshair], command: Callable[[str], None],
                 columns: int = 4) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self._cells: dict[str, tk.Canvas] = {}
        for index, (name, preset) in enumerate(presets.items()):
            cell = tk.Canvas(self, width=self.CELL_W, height=self.CELL_H, bg=theme.RAISED, cursor="hand2",
                             highlightthickness=2, highlightbackground=theme.PANEL, highlightcolor=theme.PANEL, bd=0)
            cell.grid(row=index // columns, column=index % columns, padx=3, pady=3)
            self._draw(cell, name, preset)
            cell.bind("<Button-1>", lambda _event, key=name: command(key))
            cell.bind("<Enter>", lambda _event, c=cell: c.configure(bg=theme.RAISED_HOVER))
            cell.bind("<Leave>", lambda _event, c=cell: c.configure(bg=theme.RAISED))
            ToolTip(cell, name.title())
            self._cells[name] = cell

    def _draw(self, cell: tk.Canvas, name: str, preset: Crosshair) -> None:
        scale = fit_scale(preset, self.HALF_EXTENT)
        draw_on_canvas(cell, preset, self.CELL_W // 2, 30, scale, background=theme.RAISED)
        cell.create_text(self.CELL_W // 2, self.CELL_H - 20, text=name.title(), fill=theme.MUTED,
                         font=(theme.FONT, 8), width=self.CELL_W - 8, justify="center")

    def select(self, name: str | None) -> None:
        for key, cell in self._cells.items():
            ring = theme.ACCENT if key == name else theme.PANEL
            cell.configure(highlightbackground=ring, highlightcolor=ring)