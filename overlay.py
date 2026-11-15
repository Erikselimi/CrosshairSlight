"""The click-through crosshair overlay window and the small Windows helpers it needs.

Everything that touches Win32 lives here, so the rest of the app stays portable and testable.
"""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from ctypes import wintypes
from typing import Callable

from crosshair_render import OUTLINE_COLOR, draw_on_canvas, overlay_extent

KEEP_ALIVE_MS = 1000

# Windows makes every pixel of exactly this color see-through. It must never equal a color the
# crosshair is drawn in (fill or outline), or that part of the crosshair would vanish.
KEY_COLORS = ("#FF00FE", "#010203", "#00FE01", "#FE0102", "#02FE03", "#FD00FC")

_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008
_WS_EX_TRANSPARENT = 0x00000020  # clicks go through
_WS_EX_TOOLWINDOW = 0x00000080  # no taskbar button
_WS_EX_LAYERED = 0x00080000
_WS_EX_NOACTIVATE = 0x08000000  # never takes focus from the game
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010


class OverlayError(RuntimeError):
    """The overlay could not be created."""


def pick_key_color(crosshair_color: str, outline_color: str = OUTLINE_COLOR) -> str:
    """A see-through color that differs from both the fill and the outline colors."""
    in_use = {crosshair_color.upper(), outline_color.upper()}
    for candidate in KEY_COLORS:
        if candidate.upper() not in in_use:
            return candidate
    return KEY_COLORS[-1]


def enable_dpi_awareness() -> None:
    """Without this, Windows scales the whole app bitmap-style on 125%/150% displays.

    That would blur the crosshair and make its pixel sizes wrong, so it is switched off.
    """
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def screen_size(root: tk.Misc) -> tuple[int, int]:
    """Size of the primary display in real pixels."""
    try:
        user32 = ctypes.windll.user32
        width, height = int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except (AttributeError, OSError):
        width = height = 0
    return width or root.winfo_screenwidth(), height or root.winfo_screenheight()


def _user32():
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    return user32


class OverlayWindow:
    """A small transparent window that sits on top of everything, centered on the primary display."""

    def __init__(self, root: tk.Misc, get_settings: Callable, get_stretch: Callable[[], tuple[float, float]],
                 get_screen_size: Callable[[], tuple[int, int]],
                 on_display_change: Callable[[], None] | None = None) -> None:
        self.root = root
        self.get_settings = get_settings
        self.get_stretch = get_stretch
        self.get_screen_size = get_screen_size
        self.on_display_change = on_display_change
        self.window: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.bounds: tuple[int, int, int, int] | None = None
        self.hwnd: int | None = None
        self.key: str | None = None
        self._after_id: str | None = None

    @property
    def visible(self) -> bool:
        return self.window is not None

    def show(self) -> None:
        if self.window is not None:
            return
        try:
            self._create()
        except (tk.TclError, OSError, AttributeError, ctypes.ArgumentError) as error:
            self.hide()
            raise OverlayError(str(error)) from error

    def hide(self) -> None:
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None
        self.canvas = None
        self.bounds = None
        self.hwnd = None
        self.key = None

    def refresh(self) -> None:
        """Redraw after the design, position or stretch changed."""
        if self.window is None:
            return
        try:
            self._apply_key_color()
            self._sync_geometry()
            self._paint()
            self._apply_alpha()
        except (tk.TclError, OSError, AttributeError):
            self.hide()

    # -- internals ---------------------------------------------------------------------------------

    def _compute_bounds(self) -> tuple[int, int, int, int]:
        """Left, top, width and height. The crosshair center is the window's (width//2, height//2)
        pixel, which lands on the screen's (width//2, height//2) pixel plus the offset - the same
        integer center rule the preview uses, so both agree to the pixel."""
        screen_width, screen_height = self.get_screen_size()
        width, height = overlay_extent(self.get_stretch())
        settings = self.get_settings()
        x = screen_width // 2 + settings.offset_x - width // 2
        y = screen_height // 2 + settings.offset_y - height // 2
        return x, y, width, height

    def _create(self) -> None:
        if os.name != "nt":
            raise OSError("The click-through overlay is available on Windows only.")
        settings = self.get_settings()
        self.key = pick_key_color(settings.color, settings.outline_color)
        window = tk.Toplevel(self.root)
        self.window = window
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg=self.key)
        window.attributes("-topmost", True)
        window.attributes("-transparentcolor", self.key)
        x, y, width, height = self._compute_bounds()
        self.bounds = (x, y, width, height)
        window.geometry(f"{width}x{height}{x:+d}{y:+d}")
        self.canvas = tk.Canvas(window, width=width, height=height, bg=self.key, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._paint()
        window.update_idletasks()
        self._make_click_through()
        self._apply_alpha()
        window.deiconify()
        window.lift()
        self._raise()
        self._after_id = self.root.after(KEEP_ALIVE_MS, self._tick)

    def _paint(self) -> None:
        if self.canvas is None or self.bounds is None:
            return
        width, height = self.bounds[2:]
        draw_on_canvas(self.canvas, self.get_settings(), width // 2, height // 2, 1.0, None,
                       stretch=self.get_stretch())

    def _apply_key_color(self) -> None:
        """Keep the see-through color different from the crosshair color as the color changes."""
        if self.window is None or self.canvas is None:
            return
        settings = self.get_settings()
        key = pick_key_color(settings.color, settings.outline_color)
        if key != self.key:
            self.key = key
            self.window.configure(bg=key)
            self.canvas.configure(bg=key)
            self.window.attributes("-transparentcolor", key)

    def _apply_alpha(self) -> None:
        if self.window is not None:
            opacity = int(self.get_settings().opacity)
            self.window.attributes("-alpha", max(0.0, min(1.0, opacity / 100)))

    def _sync_geometry(self) -> bool:
        """Move or resize the window when the offset, stretch or display size changed."""
        if self.window is None:
            return False
        bounds = self._compute_bounds()
        if bounds == self.bounds:
            return False
        resized = self.bounds is None or bounds[2:] != self.bounds[2:]
        self.bounds = bounds
        x, y, width, height = bounds
        self.window.geometry(f"{width}x{height}{x:+d}{y:+d}")
        if resized and self.canvas is not None:
            self.canvas.configure(width=width, height=height)
        return True

    def _make_click_through(self) -> None:
        if self.window is None:
            return
        user32 = _user32()
        hwnd = self.window.winfo_id()
        hwnd = user32.GetParent(hwnd) or hwnd
        self.hwnd = int(hwnd)
        style = user32.GetWindowLongW(self.hwnd, _GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, _GWL_EXSTYLE,
                              style | _WS_EX_TRANSPARENT | _WS_EX_LAYERED | _WS_EX_TOOLWINDOW
                              | _WS_EX_TOPMOST | _WS_EX_NOACTIVATE)

    def _raise(self) -> None:
        """Put the overlay back on top without taking focus from the game."""
        if self.hwnd is None:
            return
        try:
            _user32().SetWindowPos(self.hwnd, wintypes.HWND(-1), 0, 0, 0, 0,
                                   _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE)
        except (OSError, AttributeError, ctypes.ArgumentError):
            pass

    def _tick(self) -> None:
        self._after_id = None
        if self.window is None:
            return
        try:
            if self._sync_geometry():
                # The display changed (for example the game switched resolution): redraw to match.
                self._paint()
                if self.on_display_change is not None:
                    self.on_display_change()
            self._raise()
            self._after_id = self.root.after(KEEP_ALIVE_MS, self._tick)
        except (tk.TclError, OSError, AttributeError):
            self.hide()