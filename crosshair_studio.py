"""Sightline - crosshair studio (main window)."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import tkinter as tk
import threading
import traceback
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

import theme
from crosshair_data import PRESETS, Crosshair, ProfileStore, validate_settings
from crosshair_render import blend_color, contrast_ratio, draw_on_canvas, parse_resolution, stretch_factors
from import_export import ImportExportWindow
from overlay import OverlayError, OverlayWindow, enable_dpi_awareness, screen_size
from pixel_editor import PixelEditorWindow
from profile_manager import ProfileManagerWindow
from update_manager import UpdateError, UpdateInfo, check_for_update, download_update, launch_update_installer
from widgets import ColorField, PresetGrid, RoundedPanel, ScrollFrame, StepSlider, SwatchRow, ToolTip, install_wheel_scrolling

APP_NAME = "Sightline"
APP_DATA = Path(os.environ.get("APPDATA", Path.home())) / "Sightline"
CONFIG_PATH = APP_DATA / "profile.json"
PROFILE_PATH = APP_DATA / "profiles.json"
LOG_PATH = APP_DATA / "sightline.log"

HOTKEYS = ("Ctrl+Shift+F8", "Alt+F8", "F8")
RESOLUTION_CHOICES = ("Off", "1728x1080", "1720x1080", "1680x1050", "1440x1080", "1280x1024", "1280x960", "1024x768")
SETTING_KEYS = ("shape", "size", "vertical_size", "gap", "thickness", "outline", "dot_size", "opacity",
                "center_dot", "offset_x", "offset_y", "image_path", "image_scale",
                "remove_background", "bg_tolerance", "glow_enabled", "glow_color", "glow_size", "glow_strength")

COLOR_SWATCHES = [
    ("Ice cyan", "#00F5FF"), ("Electric blue", "#168CFF"), ("Ultraviolet", "#8B5CFF"),
    ("Laser magenta", "#F000FF"), ("Hot pink", "#FF2D95"), ("Red", "#FF3B55"),
    ("Plasma orange", "#FF6D00"), ("Neon yellow", "#FFE600"), ("Toxic lime", "#B6FF00"),
    ("Neon green", "#39FF14"), ("Mint", "#65E6D2"), ("White", "#FFFFFF"),
]
# Dark outlines stay readable on bright fill colors; neon tones are available for double-color designs.
OUTLINE_SWATCHES = [
    ("Midnight", "#080D15"), ("Charcoal", "#17202D"), ("White", "#FFFFFF"),
    ("Ice cyan", "#00F5FF"), ("Electric blue", "#168CFF"), ("Ultraviolet", "#8B5CFF"),
    ("Laser magenta", "#F000FF"), ("Hot pink", "#FF2D95"), ("Toxic lime", "#B6FF00"),
    ("Neon green", "#39FF14"),
]
GLOW_SWATCHES = [
    ("Ice cyan", "#00F5FF"), ("Electric blue", "#168CFF"), ("Ultraviolet", "#8B5CFF"),
    ("Laser magenta", "#F000FF"), ("Hot pink", "#FF2D95"), ("Toxic lime", "#B6FF00"),
]
# Sample backgrounds for checking how visible the crosshair is.
BACKDROPS = [
    ("Dark", theme.PREVIEW_BG), ("Grass", "#4F7A3A"), ("Sky", "#6FA8DC"),
    ("Sand", "#C9B27C"), ("Snow", "#E8EEF2"), ("Stone", "#7B7F85"),
]

# What each setting means for each shape, so the sliders say what they really do.
SHAPE_LABELS = {
    "Cross": {"size": "Horizontal arm", "vertical_size": "Vertical arm"},
    "T": {"size": "Horizontal arm", "vertical_size": "Stem length"},
    "Dot": {"size": "Diameter"},
    "Circle": {"size": "Ring width", "vertical_size": "Ring height", "thickness": "Ring thickness"},
    "Image": {},
}
SHAPE_ACTIVE = {
    "Cross": {"size", "vertical_size", "gap", "thickness", "outline", "dot_size", "opacity", "offset_x", "offset_y",
              "glow_size", "glow_strength"},
    "T": {"size", "vertical_size", "gap", "thickness", "outline", "opacity", "offset_x", "offset_y",
          "glow_size", "glow_strength"},
    "Dot": {"size", "outline", "opacity", "offset_x", "offset_y", "glow_size", "glow_strength"},
    "Circle": {"size", "vertical_size", "thickness", "outline", "opacity", "offset_x", "offset_y",
               "glow_size", "glow_strength"},
    "Image": {"opacity", "offset_x", "offset_y", "image_scale", "bg_tolerance"},
}
DEFAULT_LABELS = {
    "size": "Horizontal arm", "vertical_size": "Vertical arm", "gap": "Center gap", "thickness": "Thickness",
    "outline": "Outline", "dot_size": "Center dot size", "opacity": "Opacity",
    "offset_x": "Left / right", "offset_y": "Up / down", "image_scale": "Image size",
    "bg_tolerance": "Color tolerance",
    "glow_size": "Halo size", "glow_strength": "Glow intensity",
}
# key: (low, high, suffix, hint)
SLIDER_SPECS = {
    "size": (1, 80, "", "Length of each horizontal arm, not counting the center gap, in pixels."),
    "vertical_size": (1, 80, "", "Length of each vertical arm, not counting the center gap."),
    "gap": (0, 40, "", "Empty space between the center point and the inner end of each arm."),
    "thickness": (1, 12, "", "Width of vertical arms and height of horizontal arms, in pixels."),
    "outline": (0, 6, "", "Border around the crosshair. Its color is set under Color; zero turns the outline off."),
    "dot_size": (1, 20, "", "Diameter of the dot in the middle of a Cross."),
    "opacity": (0, 100, "%", "How see-through the crosshair is, in the preview and on the overlay."),
    "offset_x": (-200, 200, "px", "Move the crosshair left (negative) or right (positive) of the screen center."),
    "offset_y": (-200, 200, "px", "Move the crosshair up (negative) or down (positive) from the screen center."),
    "image_scale": (10, 400, "%", "Scale the selected image relative to its original dimensions."),
    "bg_tolerance": (0, 100, "", "Maximum per-channel color difference from the image's top-left pixel to remove."),
    "glow_size": (1, 16, "px", "How far the neon halo spreads beyond the crosshair."),
    "glow_strength": (0, 100, "%", "Strength of the outer-to-inner neon halo."),
}


def log_error(message: str) -> None:
    """Append to the log file so crashes are visible even when the app has no console."""
    try:
        APP_DATA.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except OSError:
        pass


class SightlineApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.ui_scale = max(1.0, root.winfo_fpixels("1i") / 96)
        self.first_launch = not CONFIG_PATH.exists()
        self.preferences = self._load_preferences()
        try:
            self.settings = validate_settings(self.preferences.get("settings", {}))
        except ValueError:
            self.settings = Crosshair()
        self.profile_store = ProfileStore(PROFILE_PATH)

        self.preview_zoom = self._saved_int("preview_zoom", 100, 50, 400)
        grid = self.preferences.get("preview_grid", True)
        self.preview_grid = grid if isinstance(grid, bool) else True
        try:
            self.preview_background = validate_settings(
                {"color": self.preferences.get("preview_background", theme.PREVIEW_BG)}).color
        except ValueError:
            self.preview_background = theme.PREVIEW_BG
        hotkey = self.preferences.get("hotkey", HOTKEYS[0])
        self.hotkey = hotkey if hotkey in HOTKEYS else HOTKEYS[0]
        # The resolution the game renders at when it is stretched to the screen (None = not stretched).
        self.game_resolution: tuple[int, int] | None = None
        saved_resolution = self.preferences.get("game_resolution")
        if isinstance(saved_resolution, str):
            try:
                self.game_resolution = parse_resolution(saved_resolution)
            except ValueError:
                self.game_resolution = None
        linked = self.preferences.get("link_arms", True)
        self.link_arms_default = linked if isinstance(linked, bool) else True

        self.variables: dict[str, tk.Variable] = {}
        self.sliders: dict[str, StepSlider] = {}
        self.profile_window: ProfileManagerWindow | None = None
        self.import_export_window: ImportExportWindow | None = None
        self.settings_window: tk.Toplevel | None = None
        self.quick_settings_window: tk.Toplevel | None = None
        self.quick_settings_sliders: dict[str, StepSlider] = {}
        self.quick_shape_var: tk.StringVar | None = None
        self.quick_fill_field: ColorField | None = None
        self.quick_outline_field: ColorField | None = None
        self.quick_center_dot_var: tk.BooleanVar | None = None
        self.quick_center_dot: ttk.Checkbutton | None = None
        self.history: list[dict[str, object]] = [asdict(self.settings)]
        self.history_index = 0
        self.history_after_id: str | None = None
        self.preferences_after_id: str | None = None
        self.render_after_id: str | None = None
        self.hotkey_after_id: str | None = None
        self.flash_after_id: str | None = None
        self.history_suspended = False
        self.render_pending = False
        self.hotkey_pressed = False
        self.quick_settings_pressed = False
        self._drag: tuple[int, int, int, int] | None = None
        self._error_shown = False
        self._base_status = "Overlay off"
        self.pending_update: UpdateInfo | None = None
        self.update_check_running = False

        self.overlay = OverlayWindow(
            root,
            get_settings=lambda: self.settings,
            get_stretch=self._stretch_factors,
            get_screen_size=self._screen_size,
            on_display_change=self._display_changed,
        )

        root.title(APP_NAME)
        width, height = self._window_size()
        root.geometry(f"{width}x{height}")
        root.minsize(min(self._px(1040), width), min(self._px(680), height))
        root.configure(bg=theme.BG)
        theme.configure_styles(root)
        install_wheel_scrolling(root)
        self._build_ui()
        self._sync_controls()
        self._changed()
        self._update_overlay_ui()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-z>", lambda _event: self.undo())
        root.bind("<Control-y>", lambda _event: self.redo())
        root.bind("<Control-s>", lambda _event: self._save_preferences(announce=True))
        self.hotkey_after_id = root.after(80, self._poll_hotkey)
        if getattr(sys, "frozen", False):
            root.after(1500, self._start_update_check)
        if self.first_launch:
            root.after_idle(self._show_welcome)

    # -- small helpers -----------------------------------------------------------------------------

    def _px(self, value: int) -> int:
        return int(round(value * self.ui_scale))

    def _window_size(self) -> tuple[int, int]:
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        return (min(self._px(1180), max(900, screen_width - 80)),
                min(self._px(760), max(640, screen_height - 120)))

    def _saved_int(self, key: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(self.preferences.get(key, default))))
        except (TypeError, ValueError):
            return default

    def _screen_size(self) -> tuple[int, int]:
        return screen_size(self.root)

    def _stretch_factors(self) -> tuple[float, float]:
        return stretch_factors(self._screen_size(), self.game_resolution)

    def _resolution_text(self) -> str:
        return "Off" if self.game_resolution is None else f"{self.game_resolution[0]}x{self.game_resolution[1]}"

    # -- layout ------------------------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=(28, 22, 28, 20))
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer, style="Header.TFrame")
        top.pack(fill="x", pady=(0, 20))
        brand = ttk.Frame(top)
        brand.pack(side="left")
        ttk.Label(brand, text="SIGHTLINE", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text="CROSSHAIR STUDIO  /  DESIGN YOUR SIGHTLINE", style="Muted.TLabel").pack(anchor="w", pady=(1, 0))
        self.overlay_button = ttk.Button(top, text="Show overlay", style="Accent.TButton", command=self.toggle_overlay)
        self.overlay_button.pack(side="right")
        ToolTip(self.overlay_button, "Show or hide the crosshair on top of your game.")
        self.update_button = ttk.Button(top, text="Update", style="Accent.TButton", command=self._install_pending_update)
        self.update_button.pack(side="right", padx=(0, 8))
        self.update_button.pack_forget()
        self.hotkey_chip = ttk.Label(top, text="", style="Chip.TLabel")
        self.hotkey_chip.pack(side="right", padx=(0, 14))
        status = ttk.Frame(top, style="Header.TFrame")
        status.pack(side="right", padx=(0, 16))
        self.status_dot = tk.Label(status, text="●", bg=theme.BG, fg=theme.FAINT, font=(theme.FONT, 10))
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = ttk.Label(status, text="Overlay off", style="Status.TLabel")
        self.status_label.pack(side="left")

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0, minsize=410)
        content.rowconfigure(0, weight=1)
        self._build_preview(content).grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        self._build_sidebar(content).grid(row=0, column=1, sticky="nsew")

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(18, 0))
        for text, command, tip in (
            ("Undo", self.undo, "Ctrl+Z"), ("Redo", self.redo, "Ctrl+Y"), ("Reset", self.reset, "Back to the default design"),
        ):
            button = ttk.Button(footer, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            ToolTip(button, tip)
        for text, command in (
            ("Quick edit (F2)", self.toggle_quick_settings), ("Settings", self.open_settings),
            ("Import / Export", self.open_import_export),
            ("Profiles", self.open_profiles), ("Save profile", self.save_profile),
        ):
            ttk.Button(footer, text=text, command=command).pack(side="right", padx=(6, 0))

    def _build_preview(self, parent: ttk.Frame) -> RoundedPanel:
        card = RoundedPanel(parent, padding=4)
        body = card.body
        header = ttk.Frame(body, style="Panel.TFrame")
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="LIVE PREVIEW", style="Section.TLabel").pack(side="left")
        ttk.Button(header, text="+", style="Step.TButton", width=2, takefocus=False,
                   command=lambda: self.change_zoom(25)).pack(side="right")
        self.zoom_label = ttk.Label(header, text="100%", style="Panel.TLabel", width=5, anchor="center")
        self.zoom_label.pack(side="right")
        ttk.Button(header, text="−", style="Step.TButton", width=2, takefocus=False,
                   command=lambda: self.change_zoom(-25)).pack(side="right")
        ttk.Label(header, text="Zoom", style="PanelMuted.TLabel").pack(side="right", padx=(0, 8))
        self.grid_var = tk.BooleanVar(value=self.preview_grid)
        ttk.Checkbutton(header, text="Grid", variable=self.grid_var, style="Panel.TCheckbutton",
                        command=self._view_changed).pack(side="right", padx=(0, 18))

        self.preview = tk.Canvas(body, bg=self.preview_background, highlightthickness=0, bd=0, height=360,
                                 takefocus=True, cursor="fleur")
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda _event: self._draw_preview())
        self.preview.bind("<ButtonPress-1>", self._drag_start)
        self.preview.bind("<B1-Motion>", self._drag_move)
        self.preview.bind("<ButtonRelease-1>", lambda _event: setattr(self, "_drag", None))
        self.preview.bind("<Double-Button-1>", lambda _event: self._center_crosshair())
        for key, (dx, dy) in {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.items():
            self.preview.bind(f"<{key}>", lambda event, x=dx, y=dy: self._nudge(x, y, event))

        self.summary_label = ttk.Label(body, text="", style="Panel.TLabel", justify="left")
        self.summary_label.pack(anchor="w", pady=(12, 0))
        footer = ttk.Frame(body, style="Panel.TFrame")
        footer.pack(fill="x", pady=(8, 0))
        ttk.Label(footer, text="Backdrop", style="PanelMuted.TLabel").pack(side="left", padx=(0, 8))
        self.backdrop_row = SwatchRow(footer, BACKDROPS, self._set_backdrop, size=20, gap=5)
        self.backdrop_row.pack(side="left")
        ttk.Button(footer, text="Custom", style="Small.TButton", command=self.choose_backdrop).pack(side="left", padx=(2, 0))
        ttk.Label(footer, text="Drag to move  ·  arrow keys nudge  ·  double-click to center",
                  style="PanelMuted.TLabel").pack(side="right")
        return card

    def _build_sidebar(self, parent: ttk.Frame) -> RoundedPanel:
        card = RoundedPanel(parent, padding=2)
        body = card.body
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        bar = ttk.Frame(body, style="Panel.TFrame")
        bar.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 12))
        saved_tab = self.preferences.get("tab")
        self.tab_var = tk.StringVar(value=saved_tab if saved_tab in ("presets", "design", "position") else "design")
        for column, (value, text) in enumerate((("presets", "PRESETS"), ("design", "DESIGN"), ("position", "POSITION"))):
            bar.columnconfigure(column, weight=1, uniform="tab")
            ttk.Radiobutton(bar, text=text, value=value, variable=self.tab_var, style="Segment.TRadiobutton",
                            command=self._show_tab, takefocus=False).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 2, 0))

        stack = ttk.Frame(body, style="Panel.TFrame")
        stack.grid(row=1, column=0, sticky="nsew")
        stack.rowconfigure(0, weight=1)
        stack.columnconfigure(0, weight=1)
        self.tabs: dict[str, ScrollFrame] = {}
        for name, builder in (("presets", self._build_presets_tab), ("design", self._build_design_tab),
                              ("position", self._build_position_tab)):
            frame = ScrollFrame(stack)
            frame.grid(row=0, column=0, sticky="nsew")
            builder(frame.inner)
            self.tabs[name] = frame
        self._show_tab()
        return card

    def _show_tab(self) -> None:
        self.tabs[self.tab_var.get()].tkraise()
        if hasattr(self, "grid_var"):
            self._schedule_preferences_save()

    def _section(self, parent: tk.Widget, text: str, top: int = 14) -> None:
        ttk.Label(parent, text=text, style="Eyebrow.TLabel").pack(anchor="w", pady=(top, 8), padx=(0, 6))

    def _add_slider(self, parent: tk.Widget, key: str) -> None:
        low, high, suffix, hint = SLIDER_SPECS[key]
        variable = self.variables.setdefault(key, tk.IntVar(value=getattr(self.settings, key)))
        slider = StepSlider(parent, DEFAULT_LABELS[key], variable, low, high, suffix, hint,
                            command=lambda k=key: self._slider_changed(k),
                            on_reset=lambda k=key: self.reset_setting(k))
        slider.pack(fill="x", pady=(0, 10), padx=(0, 6))
        self.sliders[key] = slider

    def _build_presets_tab(self, parent: ttk.Frame) -> None:
        self._section(parent, "CHOOSE A STARTING POINT", top=0)
        self.preset_grid = PresetGrid(parent, PRESETS, self.apply_preset)
        self.preset_grid.pack(anchor="w")
        ttk.Label(parent, text="Pick one, then fine-tune it in Design. Your position on screen is kept when you switch presets.",
                  style="PanelMuted.TLabel", wraplength=340, justify="left").pack(anchor="w", pady=(10, 0))
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=(14, 0))
        ttk.Button(row, text="Save as profile…", command=self.save_profile).pack(side="left")
        ttk.Button(row, text="Open profiles", command=self.open_profiles).pack(side="left", padx=(8, 0))

    def _build_design_tab(self, parent: ttk.Frame) -> None:
        self._section(parent, "STYLE", top=0)
        shape = self.variables.setdefault("shape", tk.StringVar(value=self.settings.shape))
        segments = ttk.Frame(parent, style="Panel.TFrame")
        segments.pack(fill="x", padx=(0, 6))
        for column, name in enumerate(("Cross", "T", "Dot", "Circle", "Image")):
            segments.columnconfigure(column, weight=1, uniform="shape")
            ttk.Radiobutton(segments, text=name.upper(), value=name, variable=shape, style="Segment.TRadiobutton",
                            command=lambda selected=name: self._select_shape(selected),
                            takefocus=False).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 2, 0))

        self._section(parent, "CUSTOM IMAGE", top=16)
        image_path = self.variables.setdefault("image_path", tk.StringVar(value=self.settings.image_path))
        image_row = ttk.Frame(parent, style="Panel.TFrame")
        image_row.pack(fill="x", padx=(0, 6))
        image_actions = ttk.Frame(image_row, style="Panel.TFrame")
        image_actions.pack(fill="x")
        ttk.Button(image_actions, text="Browse PNG / JPG…", command=self.choose_image).pack(side="left")
        ttk.Button(image_actions, text="Draw pixel by pixel…", command=self.open_pixel_editor).pack(
            side="left", padx=(6, 0))
        self.image_path_label = ttk.Label(image_row, textvariable=image_path, style="PanelMuted.TLabel",
                                          wraplength=230, justify="left")
        self.image_path_label.pack(side="left", fill="x", expand=True, pady=(6, 0))
        self._add_slider(parent, "image_scale")
        remove_background = self.variables.setdefault(
            "remove_background", tk.BooleanVar(value=self.settings.remove_background))
        self.remove_background_check = ttk.Checkbutton(
            parent, text="Remove background color", variable=remove_background,
            style="Panel.TCheckbutton", command=self._changed)
        self.remove_background_check.pack(anchor="w", pady=(0, 8))
        self._add_slider(parent, "bg_tolerance")

        self._section(parent, "FILL COLOR")
        self.fill_color_field = ColorField(
            parent, self.settings.color, self._set_color, COLOR_SWATCHES,
            on_invalid=self._invalid_color, on_status=self.flash,
            title="Crosshair color", size=18, gap=4,
        )
        self.fill_color_field.pack(fill="x", padx=(0, 6))

        self._section(parent, "OUTLINE COLOR", top=16)
        self.outline_color_field = ColorField(
            parent, self.settings.outline_color, self._set_outline_color, OUTLINE_SWATCHES,
            on_invalid=self._invalid_color, on_status=self.flash,
            title="Outline color", size=18, gap=4,
        )
        self.outline_color_field.pack(fill="x", padx=(0, 6))
        outline_tools = ttk.Frame(parent, style="Panel.TFrame")
        outline_tools.pack(fill="x", padx=(0, 6), pady=(8, 0))
        match_button = ttk.Button(outline_tools, text="Match fill", style="Small.TButton",
                                  command=self._match_outline_to_fill)
        match_button.pack(side="left")
        swap_button = ttk.Button(outline_tools, text="Swap fill / outline", style="Small.TButton",
                                 command=self._swap_colors)
        swap_button.pack(side="left", padx=(6, 0))
        ToolTip(match_button, "Use the same color for the outline as for the arms.")
        ToolTip(swap_button, "Exchange the fill and outline colors.")
        self.outline_hint = ttk.Label(parent, text="", style="Warn.TLabel", wraplength=340, justify="left")
        self.outline_hint.pack(anchor="w", pady=(6, 0))

        self._section(parent, "NEON GLOW", top=18)
        glow_enabled = self.variables.setdefault(
            "glow_enabled", tk.BooleanVar(value=self.settings.glow_enabled))
        self.glow_check = ttk.Checkbutton(
            parent, text="Enable layered neon halo", variable=glow_enabled,
            style="Panel.TCheckbutton", command=self._changed,
        )
        self.glow_check.pack(anchor="w", pady=(0, 4))
        ttk.Label(parent, text="Add a layered neon halo to Cross, T, Dot, or Circle shapes.",
                  style="PanelMuted.TLabel", wraplength=330, justify="left").pack(anchor="w", pady=(0, 8))
        self.variables.setdefault("glow_color", tk.StringVar(value=self.settings.glow_color))
        self.glow_color_field = ColorField(
            parent, self.settings.glow_color, self._set_glow_color, GLOW_SWATCHES,
            on_invalid=self._invalid_color, on_status=self.flash,
            title="Neon glow color", size=18, gap=4, pick_text="Pick…",
        )
        self.glow_color_field.pack(fill="x", padx=(0, 6))
        self._add_slider(parent, "glow_size")
        self._add_slider(parent, "glow_strength")

        self._section(parent, "SHAPE", top=18)
        self._add_slider(parent, "size")
        self._add_slider(parent, "vertical_size")
        self.link_arms = tk.BooleanVar(value=self.link_arms_default and self.settings.size == self.settings.vertical_size)
        self.link_check = ttk.Checkbutton(parent, text="Keep both arms the same length", variable=self.link_arms,
                                          style="Panel.TCheckbutton", command=self._link_toggled)
        self.link_check.pack(anchor="w", pady=(0, 10))
        self._add_slider(parent, "gap")
        self._add_slider(parent, "thickness")

        self._section(parent, "DETAILS", top=10)
        self._add_slider(parent, "outline")
        center_dot = self.variables.setdefault("center_dot", tk.BooleanVar(value=self.settings.center_dot))
        self.dot_check = ttk.Checkbutton(parent, text="Show a dot in the center", variable=center_dot,
                                         style="Panel.TCheckbutton", command=self._changed)
        self.dot_check.pack(anchor="w", pady=(0, 8))
        self._add_slider(parent, "dot_size")
        self._add_slider(parent, "opacity")

    def _build_position_tab(self, parent: ttk.Frame) -> None:
        self._section(parent, "POSITION ON SCREEN", top=0)
        self._add_slider(parent, "offset_x")
        self._add_slider(parent, "offset_y")
        ttk.Button(parent, text="Center on screen", command=self._center_crosshair).pack(anchor="w", pady=(0, 6))
        ttk.Label(parent, text="0 means the exact middle of your main display. You can also drag the crosshair in the preview.",
                  style="PanelMuted.TLabel", wraplength=340, justify="left").pack(anchor="w")

        self._section(parent, "STRETCHED RESOLUTION", top=22)
        self.resolution_var = tk.StringVar(value=self._resolution_text())
        self.resolution_box = ttk.Combobox(parent, textvariable=self.resolution_var, values=RESOLUTION_CHOICES, width=16)
        self.resolution_box.pack(anchor="w")
        self.resolution_box.bind("<<ComboboxSelected>>", lambda _event: self._apply_resolution())
        self.resolution_box.bind("<Return>", lambda _event: self._apply_resolution())
        self.resolution_box.bind("<FocusOut>", lambda _event: self._apply_resolution())
        self.resolution_box.bind("<MouseWheel>", lambda _event: "break")
        self.resolution_message = ttk.Label(parent, text="", style="Warn.TLabel", wraplength=340, justify="left")
        self.resolution_message.pack(anchor="w", pady=(6, 0))
        self.stretch_info = ttk.Label(parent, text="", style="PanelMuted.TLabel", wraplength=340, justify="left")
        self.stretch_info.pack(anchor="w", pady=(4, 0))
        ttk.Label(parent,
                  text="Playing at a stretched resolution such as 1720x1080 on a 1920x1080 screen? Enter the resolution the game renders at and the crosshair is widened to match.\n\n"
                       "If you made a custom resolution in the NVIDIA or AMD control panel and Windows itself runs at it, leave this on Off: the graphics card already stretches the overlay.",
                  style="PanelMuted.TLabel", wraplength=340, justify="left").pack(anchor="w", pady=(10, 0))
        self._update_stretch_info()

    # -- reacting to changes -----------------------------------------------------------------------

    def _slider_changed(self, key: str) -> None:
        if key in ("size", "vertical_size") and self.link_arms.get():
            other = "vertical_size" if key == "size" else "size"
            self.variables[other].set(self.variables[key].get())
        self._changed()

    def _link_toggled(self) -> None:
        if self.link_arms.get():
            self.variables["vertical_size"].set(self.variables["size"].get())
        self._changed()

    def _changed(self) -> None:
        for key in SETTING_KEYS:
            setattr(self.settings, key, self.variables[key].get())
        self._sync_controls()
        self._update_summary()
        if not self.render_pending:
            self.render_pending = True
            self.render_after_id = self.root.after_idle(self._render_crosshair)
        if not self.history_suspended:
            if self.history_after_id is not None:
                self.root.after_cancel(self.history_after_id)
            self.history_after_id = self.root.after(300, self._record_history)
        self._schedule_preferences_save()

    def _sync_controls(self) -> None:
        """Make every control agree with the current settings."""
        settings = self.settings
        for slider in self.sliders.values():
            slider.refresh()
        for slider in self.quick_settings_sliders.values():
            slider.refresh()
        labels = SHAPE_LABELS[settings.shape]
        active = SHAPE_ACTIVE[settings.shape]
        for key, slider in self.sliders.items():
            slider.set_label(labels.get(key, DEFAULT_LABELS[key]))
            enabled = key in active
            if key == "dot_size":
                enabled = enabled and settings.center_dot
            if key == "bg_tolerance":
                enabled = enabled and settings.remove_background
            if key in ("glow_size", "glow_strength"):
                enabled = enabled and settings.glow_enabled
            slider.set_enabled(enabled)
        self.dot_check.state(["!disabled"] if settings.shape == "Cross" else ["disabled"])
        self.remove_background_check.state(["!disabled"] if settings.shape == "Image" else ["disabled"])
        self.glow_check.state(["!disabled"] if settings.shape != "Image" else ["disabled"])
        self.glow_color_field.set_enabled(settings.shape != "Image")
        self.link_check.state(["!disabled"] if "vertical_size" in active else ["disabled"])
        match = next((name for name, preset in PRESETS.items()
                      if {**asdict(settings), "offset_x": 0, "offset_y": 0} == {**asdict(preset), "offset_x": 0, "offset_y": 0}), None)
        self.preset_grid.select(match)
        self.fill_color_field.set_color(settings.color)
        self.outline_color_field.set_color(settings.outline_color)
        self.glow_color_field.set_color(settings.glow_color)
        self._update_outline_hint()
        self.backdrop_row.select(self.preview_background)
        self.zoom_label.configure(text=f"{self.preview_zoom}%")
        if self.quick_shape_var is not None:
            self.quick_shape_var.set(settings.shape)
        if self.quick_center_dot is not None:
            self.quick_center_dot.state(["!disabled"] if settings.shape == "Cross" else ["disabled"])
        if self.quick_center_dot_var is not None:
            self.quick_center_dot_var.set(settings.center_dot)
        if self.quick_fill_field is not None:
            self.quick_fill_field.set_color(settings.color)
        if self.quick_outline_field is not None:
            self.quick_outline_field.set_color(settings.outline_color)
        for key, slider in self.quick_settings_sliders.items():
            slider.set_label(labels.get(key, DEFAULT_LABELS[key]))
            enabled = key in active
            if key == "dot_size":
                enabled = enabled and settings.center_dot
            if key in ("glow_size", "glow_strength"):
                enabled = enabled and settings.glow_enabled
            slider.set_enabled(enabled)

    def _update_summary(self) -> None:
        s = self.settings
        colors = f"FILL {s.color}"
        if s.outline:
            colors += f"   ·   OUTLINE {s.outline_color}"
        if s.glow_enabled and s.shape != "Image":
            colors += f"   ·   GLOW {s.glow_color} ({s.glow_size}px / {s.glow_strength}%)"
        lines = [f"{s.shape.upper()}   ·   {colors}   ·   OPACITY {s.opacity}%"]
        if s.shape in ("Cross", "T"):
            lines.append(f"ARMS {s.size} × {s.vertical_size}   ·   GAP {s.gap}   ·   THICKNESS {s.thickness}   ·   OUTLINE {s.outline}")
        elif s.shape == "Circle":
            lines.append(f"RING {s.size} × {s.vertical_size}   ·   THICKNESS {s.thickness}   ·   OUTLINE {s.outline}")
        elif s.shape == "Image":
            image_name = Path(s.image_path).name if s.image_path else "no image selected"
            lines.append(f"{image_name}   ·   SIZE {s.image_scale}%"
                         + ("   ·   BACKGROUND REMOVAL ON" if s.remove_background else ""))
        else:
            lines.append(f"DIAMETER {s.size}   ·   OUTLINE {s.outline}")
        extras = []
        if s.offset_x or s.offset_y:
            extras.append(f"OFFSET {s.offset_x:+d}, {s.offset_y:+d}")
        if self.game_resolution is not None:
            factor_x, factor_y = self._stretch_factors()
            extras.append(f"STRETCHED {self._resolution_text()}  ×{factor_x:.2f} wide")
        if extras:
            lines.append("   ·   ".join(extras))
        self.summary_label.configure(text="\n".join(lines))

    def _render_crosshair(self) -> None:
        self.render_after_id = None
        self.render_pending = False
        self._draw_preview()
        self.overlay.refresh()

    def _draw_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        canvas = self.preview
        width, height = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        background = self.preview_background
        canvas.configure(bg=background)
        canvas.delete("grid")
        canvas.delete("center_mark")
        center_x, center_y = width // 2, height // 2
        red, green, blue = (int(background[i:i + 2], 16) for i in (1, 3, 5))
        tint = "#FFFFFF" if (0.299 * red + 0.587 * green + 0.114 * blue) < 150 else "#000000"
        if self.grid_var.get():
            line = blend_color(tint, background, 9)
            axis = blend_color(tint, background, 20)
            for x in range(center_x % 32, width, 32):
                canvas.create_line(x, 0, x, height, fill=axis if x == center_x else line, tags="grid")
            for y in range(center_y % 32, height, 32):
                canvas.create_line(0, y, width, y, fill=axis if y == center_y else line, tags="grid")
        scale = self.preview_zoom / 100
        if self.settings.offset_x or self.settings.offset_y:
            # A faint mark at the true screen center, so the offset is easy to judge.
            mark = blend_color(tint, background, 45)
            canvas.create_line(center_x - 6, center_y, center_x + 7, center_y, fill=mark, tags="center_mark")
            canvas.create_line(center_x, center_y - 6, center_x, center_y + 7, fill=mark, tags="center_mark")
        draw_on_canvas(canvas, self.settings,
                       center_x + round(self.settings.offset_x * scale),
                       center_y + round(self.settings.offset_y * scale),
                       scale, background, stretch=self._stretch_factors())

    # -- preview interaction -----------------------------------------------------------------------

    def _drag_start(self, event) -> None:
        self.preview.focus_set()
        self._drag = (event.x, event.y, self.settings.offset_x, self.settings.offset_y)

    def _drag_move(self, event) -> None:
        if self._drag is None:
            return
        x0, y0, start_x, start_y = self._drag
        scale = self.preview_zoom / 100
        self._set_offset(start_x + round((event.x - x0) / scale), start_y + round((event.y - y0) / scale))

    def _set_offset(self, x: int, y: int) -> None:
        self.variables["offset_x"].set(max(-200, min(200, x)))
        self.variables["offset_y"].set(max(-200, min(200, y)))
        self._changed()

    def _nudge(self, dx: int, dy: int, event=None) -> str:
        step = 10 if event is not None and event.state & 0x0001 else 1
        self._set_offset(self.settings.offset_x + dx * step, self.settings.offset_y + dy * step)
        return "break"

    def _center_crosshair(self) -> None:
        self._set_offset(0, 0)

    def change_zoom(self, amount: int) -> None:
        self.preview_zoom = max(50, min(400, self.preview_zoom + amount))
        self.zoom_label.configure(text=f"{self.preview_zoom}%")
        self._draw_preview()
        self._schedule_preferences_save()

    def _view_changed(self) -> None:
        self.preview_grid = self.grid_var.get()
        self._draw_preview()
        self._schedule_preferences_save()

    def _set_backdrop(self, color: str) -> None:
        self.preview_background = color
        self.backdrop_row.select(color)
        self._draw_preview()
        self._schedule_preferences_save()

    def choose_backdrop(self) -> None:
        chosen = colorchooser.askcolor(color=self.preview_background, title="Preview backdrop", parent=self.root)[1]
        if chosen:
            self._set_backdrop(chosen.upper())

    # -- color -------------------------------------------------------------------------------------

    def _select_shape(self, shape: str) -> None:
        if shape == "Image" and not self.settings.image_path:
            self.choose_image()
            return
        self.variables["shape"].set(shape)
        self._changed()

    def choose_image(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a custom crosshair image",
            filetypes=(("PNG and JPG images", "*.png *.jpg"),),
        )
        if not selected:
            return
        if Path(selected).suffix.casefold() not in (".png", ".jpg"):
            messagebox.showerror("Custom image", "Choose a PNG or JPG image.", parent=self.root)
            return
        try:
            from PIL import Image

            with Image.open(selected) as image:
                image.verify()
        except ImportError:
            messagebox.showerror(
                "Custom image",
                "Pillow is required to use custom image crosshairs. Install it with: python -m pip install Pillow",
                parent=self.root,
            )
            return
        except (OSError, SyntaxError, ValueError) as error:
            messagebox.showerror("Custom image", f"Could not open this image:\n{error}", parent=self.root)
            return
        self.variables["image_path"].set(selected)
        self.variables["shape"].set("Image")
        self._changed()

    def open_pixel_editor(self) -> None:
        try:
            PixelEditorWindow(self.root, APP_DATA, self._apply_pixel_art)
        except ImportError:
            messagebox.showerror(
                "Pixel editor",
                "Pillow is required to draw custom crosshairs. Install it with: python -m pip install Pillow",
                parent=self.root,
            )

    def _apply_pixel_art(self, image_path: Path) -> None:
        self.variables["image_path"].set(str(image_path))
        self.variables["shape"].set("Image")
        self.variables["remove_background"].set(False)
        self._changed()

    def _set_color(self, color: str) -> None:
        try:
            self.settings.color = validate_settings({"color": color}).color
        except ValueError:
            return
        self._changed()

    def _set_outline_color(self, color: str) -> None:
        try:
            self.settings.outline_color = validate_settings({"outline_color": color}).outline_color
        except ValueError:
            return
        self._changed()

    def _set_glow_color(self, color: str) -> None:
        try:
            clean = validate_settings({"glow_color": color}).glow_color
        except ValueError:
            return
        self.variables["glow_color"].set(clean)
        self.settings.glow_color = clean
        self._changed()

    def _invalid_color(self, message: str) -> None:
        self.flash(message)

    def _match_outline_to_fill(self) -> None:
        self._set_outline_color(self.settings.color)

    def _swap_colors(self) -> None:
        fill, outline = self.settings.color, self.settings.outline_color
        self.settings.color = validate_settings({"color": outline}).color
        self.settings.outline_color = validate_settings({"outline_color": fill}).outline_color
        self._changed()

    def _update_outline_hint(self) -> None:
        if not hasattr(self, "outline_hint"):
            return
        settings = self.settings
        if not settings.outline:
            message = "Outline thickness is 0, so the outline color is not shown."
        elif contrast_ratio(settings.color, settings.outline_color) < 1.5:
            message = "This outline is very close to the fill color, so the edge will be hard to see."
        else:
            message = ""
        self.outline_hint.configure(text=message)

    # -- presets, undo, reset ----------------------------------------------------------------------

    def apply_preset(self, name: str) -> None:
        if name in PRESETS:
            preset = validate_settings(PRESETS[name])
            preset.offset_x = self.settings.offset_x
            preset.offset_y = self.settings.offset_y
            self._apply_settings(preset)

    def reset_setting(self, key: str) -> None:
        self.variables[key].set(getattr(Crosshair(), key))
        self._slider_changed(key)

    def reset(self) -> None:
        self._apply_settings(Crosshair())

    def _apply_settings(self, settings: Crosshair | dict[str, object]) -> None:
        self.settings = validate_settings(settings)
        for key in SETTING_KEYS:
            self.variables[key].set(getattr(self.settings, key))
        if self.settings.size != self.settings.vertical_size:
            self.link_arms.set(False)
        self._changed()

    def _record_history(self) -> None:
        self.history_after_id = None
        snapshot = asdict(self.settings)
        if snapshot == self.history[self.history_index]:
            return
        self.history = self.history[: self.history_index + 1]
        self.history.append(snapshot)
        if len(self.history) > 60:
            self.history.pop(0)
        self.history_index = len(self.history) - 1

    def undo(self) -> None:
        self._step_history(-1)

    def redo(self) -> None:
        self._step_history(1)

    def _step_history(self, direction: int) -> None:
        if self.history_after_id is not None:  # commit the change in progress first
            self.root.after_cancel(self.history_after_id)
            self._record_history()
        target = self.history_index + direction
        if not 0 <= target < len(self.history):
            return
        self.history_index = target
        self.history_suspended = True
        try:
            self._apply_settings(self.history[target])
        finally:
            self.history_suspended = False

    # -- stretched resolution ----------------------------------------------------------------------

    def _apply_resolution(self) -> None:
        try:
            resolution = parse_resolution(self.resolution_var.get())
        except ValueError as error:
            self.resolution_message.configure(text=str(error))
            return
        self.resolution_message.configure(text="")
        if resolution == self.game_resolution:
            return
        self.game_resolution = resolution
        self.resolution_var.set(self._resolution_text())
        self._update_stretch_info()
        self._changed()
        self._update_overlay_ui()

    def _update_stretch_info(self) -> None:
        screen = self._screen_size()
        if self.game_resolution is None:
            self.stretch_info.configure(text=f"Screen {screen[0]}×{screen[1]}  ·  not stretched")
        else:
            factor_x, factor_y = self._stretch_factors()
            self.stretch_info.configure(
                text=f"Screen {screen[0]}×{screen[1]}  ·  crosshair ×{factor_x:.2f} wider, ×{factor_y:.2f} taller")

    # -- overlay -----------------------------------------------------------------------------------

    def _start_update_check(self) -> None:
        if self.update_check_running:
            return
        self.update_check_running = True
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def _check_update_worker(self) -> None:
        try:
            update = check_for_update()
        except UpdateError as error:
            log_error(f"update check: {error}")
            try:
                self.root.after(0, self._update_check_failed)
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._update_check_complete, update)
        except tk.TclError:
            pass

    def _update_check_failed(self) -> None:
        self.update_check_running = False
        self.flash("Update check failed; details were logged.")

    def _update_check_complete(self, update: UpdateInfo | None) -> None:
        self.update_check_running = False
        if update is None:
            return
        self.pending_update = update
        install_now = messagebox.askyesno(
            "Update found",
            f"Sightline {update.version} is available. Install it now?",
            parent=self.root,
        )
        if install_now:
            self._install_pending_update()
        else:
            self.update_button.pack(side="right", padx=(0, 8))

    def _install_pending_update(self) -> None:
        update = self.pending_update
        if update is None:
            return
        self.update_button.configure(text="Downloading…", state="disabled")
        threading.Thread(target=self._download_update_worker, args=(update,), daemon=True).start()

    def _download_update_worker(self, update: UpdateInfo) -> None:
        try:
            staged = download_update(update, APP_DATA / "updates")
        except UpdateError as error:
            log_error(f"update download: {error}")
            try:
                self.root.after(0, self._update_download_failed, str(error))
            except tk.TclError:
                pass
            return
        try:
            self.root.after(0, self._launch_update, staged)
        except tk.TclError:
            pass

    def _update_download_failed(self, error: str) -> None:
        self.update_button.configure(text="Update", state="normal")
        messagebox.showerror("Update failed", error, parent=self.root)

    def _launch_update(self, staged_executable: Path) -> None:
        try:
            launch_update_installer(staged_executable, Path(sys.executable), LOG_PATH.with_name("update.log"))
        except UpdateError as error:
            self.update_button.configure(text="Update", state="normal")
            messagebox.showerror("Update failed", str(error), parent=self.root)
            return
        self.update_button.configure(text="Applying update…")
        self.root.after(800, self.close)

    def toggle_overlay(self) -> None:
        if self.overlay.visible:
            self.overlay.hide()
        else:
            try:
                self.overlay.show()
            except OverlayError as error:
                log_error(f"overlay: {error}")
                messagebox.showerror("Overlay unavailable", f"Could not create the Windows overlay.\n\n{error}", parent=self.root)
        self._update_overlay_ui()

    def _display_changed(self) -> None:
        self._draw_preview()
        self._update_stretch_info()
        self._update_summary()
        self._update_overlay_ui()

    def _update_overlay_ui(self) -> None:
        on = self.overlay.visible
        self.overlay_button.configure(text="Hide overlay" if on else "Show overlay")
        self.status_dot.configure(fg=theme.OK if on else theme.FAINT)
        if not on:
            self._base_status = "Overlay off"
        elif self.game_resolution is None:
            self._base_status = "Overlay on"
        else:
            self._base_status = f"Overlay on  ·  stretched {self._resolution_text()}"
        self.status_label.configure(text=self._base_status)
        self.hotkey_chip.configure(text=f"{self.hotkey}  toggles")

    def flash(self, text: str) -> None:
        """Show a short message in the status area, then go back to the overlay status."""
        self.status_label.configure(text=text)
        if self.flash_after_id is not None:
            self.root.after_cancel(self.flash_after_id)
        self.flash_after_id = self.root.after(2500, self._end_flash)

    def _end_flash(self) -> None:
        self.flash_after_id = None
        self.status_label.configure(text=self._base_status)

    def _poll_hotkey(self) -> None:
        self.hotkey_after_id = None
        try:
            user32 = ctypes.windll.user32
            keys = {"Ctrl+Shift+F8": (0x11, 0x10, 0x77), "Alt+F8": (0x12, 0x77), "F8": (0x77,)}.get(self.hotkey, (0x11, 0x10, 0x77))
            keys_down = all(user32.GetAsyncKeyState(key) & 0x8000 for key in keys)
            if keys_down and not self.hotkey_pressed:
                self.toggle_overlay()
            self.hotkey_pressed = bool(keys_down)
            quick_settings_down = bool(user32.GetAsyncKeyState(0x71) & 0x8000)
            if quick_settings_down and not self.quick_settings_pressed:
                self.toggle_quick_settings()
            self.quick_settings_pressed = quick_settings_down
            self.hotkey_after_id = self.root.after(80, self._poll_hotkey)
        except (tk.TclError, AttributeError):
            return

    # -- other windows -----------------------------------------------------------------------------

    def toggle_quick_settings(self) -> None:
        if self.quick_settings_window is not None and self.quick_settings_window.winfo_exists():
            self.close_quick_settings()
        else:
            self.open_quick_settings()

    def close_quick_settings(self) -> None:
        if self.quick_settings_window is not None:
            try:
                self.quick_settings_window.destroy()
            except tk.TclError:
                pass
        self.quick_settings_window = None
        self.quick_settings_sliders.clear()
        self.quick_shape_var = None
        self.quick_fill_field = None
        self.quick_outline_field = None
        self.quick_center_dot_var = None
        self.quick_center_dot = None

    def open_quick_settings(self) -> None:
        if self.quick_settings_window is not None and self.quick_settings_window.winfo_exists():
            self.quick_settings_window.deiconify()
            self.quick_settings_window.lift()
            self.quick_settings_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.quick_settings_window = window
        window.title("Sightline Quick Settings")
        window.configure(bg=theme.BG)
        window.attributes("-topmost", True)
        width, height = self._px(390), self._px(660)
        x = max(0, self.root.winfo_screenwidth() - width - self._px(24))
        y = self._px(48)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.minsize(self._px(340), self._px(420))
        window.protocol("WM_DELETE_WINDOW", self.close_quick_settings)
        window.bind("<Escape>", lambda _event: self.close_quick_settings())

        header = ttk.Frame(window, padding=(16, 12, 12, 10))
        header.pack(fill="x")
        title_block = ttk.Frame(header)
        title_block.pack(side="left")
        ttk.Label(title_block, text="QUICK SETTINGS", style="Section.TLabel").pack(anchor="w")
        ttk.Label(title_block, text="Changes apply live  ·  F2 to close", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Button(header, text="×", width=3, command=self.close_quick_settings).pack(side="right")

        content = ScrollFrame(window, padding=14)
        content.pack(fill="both", expand=True)
        self._section(content.inner, "SHAPE", top=0)
        self.quick_shape_var = tk.StringVar(value=self.settings.shape)
        shape_row = ttk.Frame(content.inner, style="Panel.TFrame")
        shape_row.pack(fill="x", pady=(0, 6))
        for column, shape in enumerate(("Cross", "T", "Dot", "Circle")):
            shape_row.columnconfigure(column, weight=1, uniform="quick-shape")
            ttk.Radiobutton(
                shape_row, text=shape.upper(), value=shape, variable=self.quick_shape_var,
                style="Segment.TRadiobutton", takefocus=False,
                command=self._quick_shape_changed,
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 2, 0))

        self._section(content.inner, "FILL COLOR")
        self.quick_fill_field = ColorField(
            content.inner, self.settings.color, self._set_color, COLOR_SWATCHES,
            on_invalid=self._invalid_color, on_status=self.flash,
            title="Crosshair color", size=20, gap=4, pick_text="Pick…",
        )
        self.quick_fill_field.pack(fill="x")

        self._section(content.inner, "OUTLINE COLOR", top=14)
        self.quick_outline_field = ColorField(
            content.inner, self.settings.outline_color, self._set_outline_color, OUTLINE_SWATCHES,
            on_invalid=self._invalid_color, on_status=self.flash,
            title="Outline color", size=20, gap=4, pick_text="Pick…",
        )
        self.quick_outline_field.pack(fill="x")

        self._section(content.inner, "SIZE & DETAILS", top=16)
        for key in ("size", "vertical_size", "gap", "thickness", "outline"):
            self._add_quick_slider(content.inner, key)
        self.quick_center_dot_var = tk.BooleanVar(value=self.settings.center_dot)
        self.quick_center_dot = ttk.Checkbutton(
            content.inner, text="Show a dot in the center", variable=self.quick_center_dot_var,
            style="Panel.TCheckbutton", command=self._quick_center_dot_changed,
        )
        self.quick_center_dot.pack(anchor="w", pady=(0, 8))
        for key in ("dot_size", "opacity", "offset_x", "offset_y"):
            self._add_quick_slider(content.inner, key)
        ttk.Button(content.inner, text="Center on screen", command=self._center_crosshair).pack(anchor="w", pady=(0, 8))
        self._sync_controls()
        window.deiconify()
        window.lift()
        window.focus_force()

    def _add_quick_slider(self, parent: ttk.Frame, key: str) -> None:
        low, high, suffix, hint = SLIDER_SPECS[key]
        variable = self.variables[key]
        slider = StepSlider(
            parent, DEFAULT_LABELS[key], variable, low, high, suffix, hint,
            command=lambda selected=key: self._slider_changed(selected),
            on_reset=lambda selected=key: self.reset_setting(selected),
        )
        slider.pack(fill="x", pady=(0, 8))
        self.quick_settings_sliders[key] = slider

    def _quick_shape_changed(self) -> None:
        if self.quick_shape_var is not None:
            self.variables["shape"].set(self.quick_shape_var.get())
            self._changed()

    def _quick_center_dot_changed(self) -> None:
        self.variables["center_dot"].set(self.quick_center_dot_var.get())
        self._changed()

    def open_profiles(self) -> ProfileManagerWindow:
        if self.profile_window is not None and self.profile_window.window.winfo_exists():
            self.profile_window.window.deiconify()
            self.profile_window.window.lift()
            self.profile_window.refresh()
            return self.profile_window
        self.profile_window = ProfileManagerWindow(self.root, self.profile_store, lambda: self.settings, self._apply_settings)
        return self.profile_window

    def open_import_export(self) -> ImportExportWindow:
        if self.import_export_window is not None and self.import_export_window.window.winfo_exists():
            self.import_export_window.window.deiconify()
            self.import_export_window.window.lift()
            self.import_export_window.refresh_export()
            return self.import_export_window
        self.import_export_window = ImportExportWindow(self.root, lambda: self.settings, self._apply_settings)
        return self.import_export_window

    def save_profile(self) -> None:
        self.open_profiles().save_current()

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("Sightline Settings")
        window.geometry("540x380")
        window.configure(bg=theme.BG)
        panel = ttk.Frame(window, padding=24)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="SETTINGS", style="Title.TLabel").pack(anchor="w", pady=(0, 16))
        ttk.Label(panel, text="Overlay shortcut", style="TLabel").pack(anchor="w")
        hotkey = tk.StringVar(value=self.hotkey)
        selector = ttk.Combobox(panel, textvariable=hotkey, values=HOTKEYS, state="readonly", width=22)
        selector.pack(anchor="w", pady=(8, 5))
        selector.bind("<MouseWheel>", lambda _event: "break")
        ttk.Label(panel, text="Works while a game is in front. Sightline only checks whether the keys are pressed; it does not install a keyboard hook.",
                  style="Muted.TLabel", wraplength=480, justify="left").pack(anchor="w")
        ttk.Label(panel, text=f"Your profiles and preferences are stored in\n{APP_DATA}", style="Muted.TLabel",
                  wraplength=480, justify="left").pack(anchor="w", pady=(20, 8))
        actions = ttk.Frame(panel)
        actions.pack(fill="x")
        ttk.Button(actions, text="Open data folder", command=self.open_data_folder).pack(side="left")
        ttk.Button(actions, text="Export all profiles", command=self.export_profiles_archive).pack(side="left", padx=(8, 0))

        def save() -> None:
            self.hotkey = hotkey.get()
            self.hotkey_pressed = False
            self._update_overlay_ui()
            self._save_preferences(announce=True)
            window.destroy()

        ttk.Button(panel, text="Save", style="Accent.TButton", command=save).pack(anchor="e", pady=(24, 0))

    def open_data_folder(self) -> None:
        try:
            APP_DATA.mkdir(parents=True, exist_ok=True)
            os.startfile(APP_DATA)  # type: ignore[attr-defined]
        except (OSError, AttributeError) as error:
            messagebox.showerror("Open data folder", str(error), parent=self.root)

    def export_profiles_archive(self) -> None:
        destination = filedialog.asksaveasfilename(parent=self.root, defaultextension=".zip",
                                                   filetypes=(("Sightline profile archive", "*.zip"),))
        if not destination:
            return
        try:
            self.profile_store.export_archive(destination)
            messagebox.showinfo("Export profiles", "All profiles were exported.", parent=self.root)
        except (OSError, ValueError) as error:
            messagebox.showerror("Export profiles", str(error), parent=self.root)

    def _show_welcome(self) -> None:
        welcome = tk.Toplevel(self.root)
        welcome.title("Welcome to Sightline")
        welcome.geometry("520x340")
        welcome.configure(bg=theme.BG)
        welcome.transient(self.root)
        panel = ttk.Frame(welcome, padding=26)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="WELCOME", style="Title.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(
            panel,
            text="1. Pick a preset, then tune it in Design.\n"
                 "2. Check it on different backdrops under the preview.\n"
                 "3. Press Show overlay (or your shortcut) to put it on screen.\n\n"
                 "For Fortnite use Windowed Fullscreen. The overlay is a separate window; it does not touch the game, "
                 "and it may not appear in exclusive fullscreen.",
            style="Muted.TLabel", wraplength=470, justify="left").pack(anchor="w")
        ttk.Button(panel, text="Get started", style="Accent.TButton", command=welcome.destroy).pack(anchor="e", pady=(24, 0))

    # -- saving and closing ------------------------------------------------------------------------

    @staticmethod
    def _load_preferences() -> dict[str, object]:
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                return saved if "settings" in saved else {"settings": saved}
        except (OSError, json.JSONDecodeError):
            pass
        return {"settings": asdict(Crosshair())}

    def _schedule_preferences_save(self) -> None:
        if self.preferences_after_id is not None:
            self.root.after_cancel(self.preferences_after_id)
        self.preferences_after_id = self.root.after(900, self._save_preferences)

    def _save_preferences(self, announce: bool = False) -> None:
        self.preferences_after_id = None
        payload = {
            "settings": asdict(self.settings),
            "preview_zoom": self.preview_zoom,
            "preview_grid": self.grid_var.get(),
            "preview_background": self.preview_background,
            "hotkey": self.hotkey,
            "game_resolution": self._resolution_text(),
            "link_arms": self.link_arms.get(),
            "tab": self.tab_var.get(),
        }
        temporary = CONFIG_PATH.with_suffix(".tmp")
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(CONFIG_PATH)
            if announce:
                self.flash("Saved")
        except OSError as error:
            log_error(f"save preferences: {error}")
            if announce:
                messagebox.showerror("Save preferences", str(error), parent=self.root)

    def report_error(self, exc_type, exc_value, exc_traceback) -> None:
        """Called by Tk when something in the app fails; keeps a log so errors are not silent."""
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log_error(details)
        if not self._error_shown:
            self._error_shown = True
            messagebox.showerror("Sightline hit a problem",
                                 f"{exc_value}\n\nDetails were saved to:\n{LOG_PATH}", parent=self.root)

    def close(self) -> None:
        for callback_id in (self.history_after_id, self.preferences_after_id, self.render_after_id,
                            self.hotkey_after_id, self.flash_after_id):
            if callback_id is not None:
                try:
                    self.root.after_cancel(callback_id)
                except tk.TclError:
                    pass
        self.history_after_id = self.preferences_after_id = self.render_after_id = None
        self.hotkey_after_id = self.flash_after_id = None
        self._save_preferences()
        self.close_quick_settings()
        self.overlay.hide()
        self.root.destroy()


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Sightline is a Windows-only desktop overlay.")
    enable_dpi_awareness()
    root = tk.Tk()
    try:
        app = SightlineApp(root)
    except Exception as error:  # noqa: BLE001 - show any startup failure instead of closing silently
        log_error("startup:\n" + traceback.format_exc())
        messagebox.showerror("Sightline could not start", f"{error}\n\nDetails were saved to:\n{LOG_PATH}")
        root.destroy()
        raise SystemExit(1) from error
    root.report_callback_exception = app.report_error
    root.mainloop()


if __name__ == "__main__":
    main()
