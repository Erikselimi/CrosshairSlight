# Sightline Crosshair Studio

A lightweight Windows crosshair editor and click-through desktop overlay. It uses Python's built-in Tkinter library and Windows APIs, with no extra Python packages. It does not inject into, hook, or read game memory.

## Run

Install Python 3.10 or newer with Tcl/Tk enabled. Custom image crosshairs require Pillow:

```powershell
python -m pip install Pillow
```

From this folder, run:

```powershell
python crosshair_studio.py
```

On Windows, you can also double-click `run.bat`.

## Desktop app

Install PyInstaller once with `python -m pip install pyinstaller`, then double-click
`build_exe.bat`. It creates a standalone `Sightline.exe` on your Windows Desktop; launch it
from there like any other app. The desktop app uses the included crosshair icon. Your settings
and profiles remain in `%APPDATA%\Sightline`.

The EXE checks for GitHub releases at startup and prompts before installing a newer version.
If you decline, use the **Update** button in the main window. To publish an update, keep the
GitHub repository public, change `APP_VERSION` in `version.py`, commit and push that change,
then push a matching tag such as `v1.0.1`. GitHub Actions builds and attaches `Sightline.exe`
to the release. The first updater-enabled EXE must be installed manually; it can update itself
on later releases.

## Features

- Bright studio interface with violet accents, consistent across the editor, quick settings, profiles, and import/export.
- Eighteen built-in presets, with independent horizontal and vertical arms, gap, thickness, outline, center-dot toggle and size, fill color, outline color, and opacity.
- Custom PNG/JPG image crosshairs with adjustable size and optional top-left-color background removal.
- Pixel-art crosshair editor with paint, color selection, eraser, and transparent PNG output.
- Separate fill and outline colors, each with swatches, HEX entry, a color picker, and copy. Match or swap the two colors in one click; the editor warns when the outline is too close to the fill to be seen.
- Screen position offsets (left/right and up/down) to nudge the crosshair away from the exact screen center. The preview shows faint center marks while an offset is active.
- Zoomable preview with grid/background controls, live HEX color values, tooltips, mouse-wheel scrolling of the settings panel, and undo/redo.
- Named profiles with descriptions, tags, search, sorting, favorites, duplicate/rename/delete, side-by-side comparison, and single JSON or ZIP import/export.
- CS2 and legacy CS:GO console-command import from pasted text or a selected config file. Review detected settings and warnings before applying.
- CS2/legacy command copy and `.cfg`/`.txt` export. Other targets can export portable Sightline JSON.
- Configurable `Ctrl+Shift+F8`, `Alt+F8`, or `F8` crosshair visibility shortcut, plus a global `F2` quick-settings panel for live edits while a game is in front. Press `F2` or `Esc` to close the panel. Settings and the profile library are stored under `%APPDATA%\Sightline`.
- First-launch guide, local data-folder access, preference autosave, and safe profile writes.

## Rendering

All crosshair geometry lives in `crosshair_render.py` and is shared by the editor preview, the profile and import previews, and the overlay. Every arm is an exact integer pixel rectangle, drawn into a Tk `PhotoImage`, so there are no rounded line caps, half-pixel blur or per-arm rounding differences. Opposite arms are exact mirrors of each other.

- **Length** (`size`, `vertical_size`): arm length, not counting the gap.
- **Gap**: empty space from the center to the inner end of each arm. A gap of 0 gives one continuous cross with no hole in the middle.
- **Thickness**: width of vertical arms / height of horizontal arms. Odd thicknesses center on the middle pixel, even thicknesses on the line between pixels.
- **Outline**: a border added around every arm, drawn first, in its own configurable color. It never paints over the center gap.
- **T shape**: horizontal bar plus a stem going down (no top arm), like the in-game T style.

## Overlay

The overlay is a small click-through window (272 px square) placed on the center of the primary display, plus any offset you set. It is re-raised above other windows every second without taking focus, so it stays visible when a game window is activated.

For Fortnite, use **Windowed Fullscreen** (borderless). The overlay does not follow a game on a secondary display. Exclusive fullscreen may cover overlays. Check Epic's current rules before using third-party overlays; compatibility or policy approval is not guaranteed.

## Conversion Limits

CS2/CS:GO dimensions are mapped numerically into Sightline preview pixels, not rendered identically. Recoil behavior, legacy animated styles, and some game-specific shape details cannot be represented exactly; the importer/exporter reports approximations. Native VALORANT and Fortnite configuration import/export are not implemented. They can use portable Sightline JSON or manual editor settings. Preview backgrounds are solid colors, not captured game scenes. No AI provider is included. CS2 exports ignore the screen offset because CS2 always centers its crosshair.

## Tests

From this folder, run `python -m unittest discover -v`.
