import json
import os
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import theme
from crosshair_data import Crosshair, export_cs2_commands, parse_cs2_commands, validate_settings
from crosshair_render import draw_on_canvas, fit_scale

PREVIEW_BACKGROUND = theme.PREVIEW_BG


class ImportExportWindow:
    def __init__(self, parent: tk.Tk, get_settings, apply_settings) -> None:
        self.parent = parent
        self.get_settings = get_settings
        self.apply_settings = apply_settings
        self.window = tk.Toplevel(parent)
        self.window.title("Sightline Import / Export")
        self.window.geometry("900x650")
        self.window.minsize(760, 540)
        self.window.configure(bg=theme.BG)
        self.pending_import: Crosshair | None = None
        self._build_ui()
        self.refresh_export()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.window, padding=26)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="GAME CONFIGURATION", style="Title.TLabel").pack(anchor="w", pady=(0, 14))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        import_page = ttk.Frame(self.tabs, style="TFrame", padding=16)
        export_page = ttk.Frame(self.tabs, style="TFrame", padding=16)
        self.tabs.add(import_page, text="IMPORT")
        self.tabs.add(export_page, text="EXPORT")
        self._build_import_page(import_page)
        self._build_export_page(export_page)

    def _build_import_page(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="SOURCE", style="Muted.TLabel").pack(side="left")
        self.import_game = tk.StringVar(value="Counter-Strike 2 / CS:GO")
        game_box = ttk.Combobox(
            toolbar,
            textvariable=self.import_game,
            values=("Counter-Strike 2 / CS:GO", "Sightline JSON", "VALORANT", "Fortnite"),
            state="readonly",
            width=25,
        )
        game_box.pack(side="left", padx=(8, 12))
        game_box.bind("<<ComboboxSelected>>", lambda _event: self._update_import_hint())
        ttk.Button(toolbar, text="Open file", command=self.open_import_file).pack(side="left")
        ttk.Button(toolbar, text="Review settings", style="Accent.TButton", command=self.preview_import).pack(side="right")

        self.import_hint = ttk.Label(parent, text="Paste CS2 / legacy console commands or open a .cfg file.", style="Muted.TLabel")
        self.import_hint.pack(anchor="w", pady=(0, 7))
        self.import_text = tk.Text(
            parent, height=10, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.ACCENT,
            selectbackground=theme.ACCENT, selectforeground=theme.ACCENT_TEXT, relief="flat",
            highlightthickness=1, highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            wrap="word", padx=12, pady=10,
        )
        self.import_text.pack(fill="both", expand=True)
        results = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        results.pack(fill="x", pady=(12, 0))
        self.import_preview = tk.Canvas(results, width=100, height=80, bg=PREVIEW_BACKGROUND, highlightthickness=0)
        self.import_preview.pack(side="left", padx=(0, 12))
        self.import_report = ttk.Label(results, text="Review the source before applying it.", style="Panel.TLabel", wraplength=560, justify="left")
        self.import_report.pack(side="left", fill="x", expand=True)
        self.apply_import_button = ttk.Button(results, text="Apply", style="Accent.TButton", command=self.apply_import, state="disabled")
        self.apply_import_button.pack(side="right", padx=(10, 0))

    def _build_export_page(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="TARGET", style="Muted.TLabel").pack(side="left")
        self.export_game = tk.StringVar(value="Counter-Strike 2")
        game_box = ttk.Combobox(
            toolbar,
            textvariable=self.export_game,
            values=("Counter-Strike 2", "CS:GO Legacy", "Sightline Profile JSON", "VALORANT", "Fortnite"),
            state="readonly",
            width=25,
        )
        game_box.pack(side="left", padx=(8, 12))
        game_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_export())
        ttk.Button(toolbar, text="Refresh", command=self.refresh_export).pack(side="left")
        ttk.Button(toolbar, text="Copy", command=self.copy_export).pack(side="right")

        self.export_text = tk.Text(
            parent, height=15, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.ACCENT,
            selectbackground=theme.ACCENT, selectforeground=theme.ACCENT_TEXT, relief="flat",
            highlightthickness=1, highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
            wrap="none", padx=12, pady=10,
        )
        self.export_text.pack(fill="both", expand=True)
        self.export_notes = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=790, justify="left")
        self.export_notes.pack(anchor="w", pady=(10, 10))
        ttk.Button(parent, text="Export file...", command=self.save_export).pack(anchor="e")

    def _update_import_hint(self) -> None:
        hints = {
            "Counter-Strike 2 / CS:GO": "Paste console commands or open a .cfg/.txt file. Unsupported commands are reported.",
            "Sightline JSON": "Paste a Sightline profile JSON object or open a .json file.",
            "VALORANT": "VALORANT's local format is not treated as a documented import. Use Sightline JSON or enter settings manually.",
            "Fortnite": "Fortnite does not expose a supported external crosshair config. This overlay is separate from the in-game reticle.",
        }
        self.import_hint.configure(text=hints[self.import_game.get()])
        self.pending_import = None
        self.apply_import_button.configure(state="disabled")

    def open_import_file(self) -> None:
        filetypes = (("Config and profile files", "*.cfg *.txt *.json"), ("All files", "*.*"))
        source = filedialog.askopenfilename(parent=self.window, filetypes=filetypes)
        if not source:
            return
        try:
            if os.path.getsize(source) > 2_000_000:
                raise ValueError("Config files must be smaller than 2 MB.")
            text = Path(source).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError, ValueError) as error:
            messagebox.showerror("Open import", str(error), parent=self.window)
            return
        self.import_text.delete("1.0", "end")
        self.import_text.insert("1.0", text)
        if source.lower().endswith(".json"):
            self.import_game.set("Sightline JSON")
            self._update_import_hint()

    def preview_import(self) -> None:
        raw = self.import_text.get("1.0", "end-1c").strip()
        self.pending_import = None
        self.apply_import_button.configure(state="disabled")
        try:
            if self.import_game.get() == "Counter-Strike 2 / CS:GO":
                result = parse_cs2_commands(raw)
                settings = result.settings
                report = "Detected:\n" + (", ".join(result.detected) or "No supported settings")
                if result.warnings:
                    report += "\n\nWarnings:\n" + "\n".join(result.warnings)
                else:
                    report += "\n\nEquivalent settings mapped directly."
            elif self.import_game.get() == "Sightline JSON":
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("Sightline JSON must contain an object.")
                source_settings = payload.get("settings", payload)
                if not isinstance(source_settings, dict) or not source_settings.keys() & set(asdict(Crosshair())):
                    raise ValueError("No supported crosshair settings were found.")
                settings = validate_settings(source_settings)
                report = "Sightline settings validated.\n\nAll supported Sightline dimensions and options are preserved."
            else:
                raise ValueError("Native import is not supported for this game. Choose Sightline JSON or enter settings manually.")
            self.pending_import = settings
            self._draw_preview(settings)
            self.import_report.configure(text=report)
            self.apply_import_button.configure(state="normal")
        except (ValueError, json.JSONDecodeError, AttributeError, TypeError) as error:
            self.import_preview.delete("all")
            self.import_report.configure(text=f"Import not applied.\n\n{error}")

    def apply_import(self) -> None:
        if self.pending_import is None:
            return
        self.apply_settings(self.pending_import)
        self.tabs.select(0)
        messagebox.showinfo("Import applied", "The reviewed settings are now in the editor.", parent=self.window)

    def refresh_export(self) -> None:
        settings = validate_settings(self.get_settings())
        target = self.export_game.get()
        notes = ""
        if target in {"Counter-Strike 2", "CS:GO Legacy"}:
            text, warnings = export_cs2_commands(settings)
            if warnings:
                notes = "Conversion notes: " + " ".join(warnings)
            notes += "\nSave as a .cfg or .txt file, then execute it in the game's console. Sightline never edits game files."
        elif target == "Sightline Profile JSON":
            text = json.dumps({"format": "sightline-profile", "format_version": 1, "settings": asdict(settings)}, indent=2)
            notes = "Portable Sightline settings; this is not a native game configuration."
        else:
            text = ""
            notes = f"No verified native {target} crosshair export is available. Export a Sightline Profile JSON and reproduce the settings manually; game parameters may not have direct equivalents."
        self.export_text.configure(state="normal")
        self.export_text.delete("1.0", "end")
        self.export_text.insert("1.0", text)
        self.export_text.configure(state="disabled")
        self.export_notes.configure(text=notes)

    def copy_export(self) -> None:
        text = self.export_text.get("1.0", "end-1c")
        if not text:
            messagebox.showinfo("Copy", "There is no native export for this target.", parent=self.window)
            return
        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        messagebox.showinfo("Copied", "Export copied to the clipboard.", parent=self.window)

    def save_export(self) -> None:
        target = self.export_game.get()
        native = target in {"Counter-Strike 2", "CS:GO Legacy"}
        extension = ".cfg" if native else ".json"
        types = (("Game config", "*.cfg"), ("Text file", "*.txt")) if native else (("Sightline JSON", "*.json"),)
        destination = filedialog.asksaveasfilename(parent=self.window, defaultextension=extension, filetypes=types)
        if not destination:
            return
        if not self.export_text.get("1.0", "end-1c"):
            messagebox.showinfo("Export", "Choose a supported game or Sightline Profile JSON.", parent=self.window)
            return
        try:
            with open(destination, "w", encoding="utf-8", newline="\n") as output:
                output.write(self.export_text.get("1.0", "end-1c"))
        except OSError as error:
            messagebox.showerror("Export file", str(error), parent=self.window)

    def _draw_preview(self, settings: Crosshair) -> None:
        # Same renderer as the editor; scaled down only when the design would not fit the small box.
        canvas = self.import_preview
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        center_x = width // 2 if width > 1 else 50
        center_y = height // 2 if height > 1 else 40
        scale = fit_scale(settings, min(center_x, center_y) - 2)
        draw_on_canvas(canvas, settings, center_x, center_y, scale, background=PREVIEW_BACKGROUND)
