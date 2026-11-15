"""A small pixel-art editor for custom crosshair images."""

from __future__ import annotations

import uuid
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk
from typing import Callable

import theme

PIXEL_COLORS = (
    "#FFFFFF", "#000000", "#FF3B30", "#FF8A00", "#FFE600",
    "#39FF14", "#00FFFF", "#2E7BFF", "#6558F5", "#FF00E6",
)
GRID_SIZE = 32
CELL_SIZE = 16


class PixelArtDocument:
    def __init__(self, size: int = GRID_SIZE) -> None:
        from PIL import Image

        if size < 1:
            raise ValueError("Pixel art dimensions must be positive.")
        self.image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    @property
    def size(self) -> int:
        return self.image.width

    def set_pixel(self, x: int, y: int, color: str | None) -> None:
        if not 0 <= x < self.size or not 0 <= y < self.size:
            raise IndexError("Pixel coordinates are outside the artboard.")
        if color is None:
            self.image.putpixel((x, y), (0, 0, 0, 0))
            return
        self.image.putpixel((x, y), (*bytes.fromhex(color.removeprefix("#")), 255))

    def clear(self) -> None:
        self.image.putdata([(0, 0, 0, 0)] * (self.size * self.size))

    def save(self, path: Path) -> None:
        self.image.save(path, format="PNG")


class PixelEditorWindow:
    def __init__(self, parent: tk.Misc, output_directory: Path, on_save: Callable[[Path], None]) -> None:
        self.parent = parent
        self.output_directory = output_directory
        self.on_save = on_save
        self.document = PixelArtDocument()
        self.selected_color: str | None = PIXEL_COLORS[2]
        self.cells: dict[tuple[int, int], int] = {}
        self.window = tk.Toplevel(parent)
        self.window.title("Draw a Crosshair")
        self.window.geometry("780x700")
        self.window.minsize(760, 660)
        self.window.configure(bg=theme.BG)
        self._build_ui()
        self._draw_grid()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.window, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="PIXEL CROSSHAIR", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer, text="Paint or erase individual pixels. Drag to draw.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 14))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            body,
            width=GRID_SIZE * CELL_SIZE,
            height=GRID_SIZE * CELL_SIZE,
            bg="#FFFFFF",
            highlightthickness=1,
            highlightbackground=theme.BORDER,
        )
        self.canvas.pack(side="left", padx=(0, 18))
        self.canvas.bind("<Button-1>", self._paint_at)
        self.canvas.bind("<B1-Motion>", self._paint_at)

        tools = ttk.Frame(body)
        tools.pack(side="left", fill="y")
        ttk.Label(tools, text="COLOR", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 8))
        palette = ttk.Frame(tools)
        palette.pack(anchor="w")
        for index, color in enumerate(PIXEL_COLORS):
            button = tk.Button(
                palette,
                bg=color,
                activebackground=color,
                width=2,
                height=1,
                relief="solid",
                bd=1,
                command=lambda selected=color: self._select_color(selected),
            )
            button.grid(row=index // 5, column=index % 5, padx=2, pady=2)
        ttk.Button(tools, text="Choose color…", command=self._choose_color).pack(anchor="w", pady=(10, 4))
        ttk.Button(tools, text="Eraser", command=lambda: self._select_color(None)).pack(anchor="w", pady=4)
        ttk.Button(tools, text="Clear canvas", command=self._clear).pack(anchor="w", pady=4)
        self.color_status = ttk.Label(tools, text="", style="Muted.TLabel")
        self.color_status.pack(anchor="w", pady=(10, 0))
        ttk.Label(
            tools, text=f"{GRID_SIZE} × {GRID_SIZE} pixels",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(18, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right")
        ttk.Button(actions, text="Use crosshair", style="Accent.TButton", command=self._save).pack(
            side="right", padx=(0, 8))

    def _draw_grid(self) -> None:
        for y in range(GRID_SIZE):
            for x in range(GRID_SIZE):
                shade = "#FFFFFF" if (x + y) % 2 == 0 else "#E9EAF2"
                item = self.canvas.create_rectangle(
                    x * CELL_SIZE, y * CELL_SIZE,
                    (x + 1) * CELL_SIZE, (y + 1) * CELL_SIZE,
                    fill=shade, outline=theme.BORDER, width=1,
                )
                self.cells[(x, y)] = item
        self._refresh_status()

    def _paint_at(self, event) -> None:
        x, y = event.x // CELL_SIZE, event.y // CELL_SIZE
        if not 0 <= x < GRID_SIZE or not 0 <= y < GRID_SIZE:
            return
        self.document.set_pixel(x, y, self.selected_color)
        self._refresh_cell(x, y)

    def _refresh_cell(self, x: int, y: int) -> None:
        pixel = self.document.image.getpixel((x, y))
        shade = "#FFFFFF" if (x + y) % 2 == 0 else "#E9EAF2"
        color = f"#{pixel[0]:02X}{pixel[1]:02X}{pixel[2]:02X}" if pixel[3] else shade
        self.canvas.itemconfigure(self.cells[(x, y)], fill=color)

    def _select_color(self, color: str | None) -> None:
        self.selected_color = color
        self._refresh_status()

    def _choose_color(self) -> None:
        chosen = colorchooser.askcolor(parent=self.window, title="Pixel color")
        if chosen[1]:
            self._select_color(chosen[1].upper())

    def _clear(self) -> None:
        self.document.clear()
        for x, y in self.cells:
            self._refresh_cell(x, y)

    def _refresh_status(self) -> None:
        selected = self.selected_color or "Transparent"
        self.color_status.configure(text=f"Selected: {selected}")

    def _save(self) -> None:
        destination = self.output_directory / "custom_crosshairs" / f"pixel_{uuid.uuid4().hex}.png"
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.document.save(destination)
        except OSError as error:
            messagebox.showerror("Save pixel crosshair", str(error), parent=self.window)
            return
        self.on_save(destination)
        self.window.destroy()
