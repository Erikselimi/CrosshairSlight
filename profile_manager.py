import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import theme
from crosshair_data import Crosshair, ProfileStore, validate_settings
from crosshair_render import draw_on_canvas, fit_scale

PREVIEW_BACKGROUND = theme.PREVIEW_BG


class ProfileManagerWindow:
    def __init__(self, parent: tk.Tk, store: ProfileStore, get_settings, apply_settings) -> None:
        self.parent = parent
        self.store = store
        self.get_settings = get_settings
        self.apply_settings = apply_settings
        self.window = tk.Toplevel(parent)
        self.window.title("Sightline Profiles")
        self.window.geometry("920x620")
        self.window.minsize(780, 520)
        self.window.configure(bg=theme.BG)
        self.search = tk.StringVar()
        self.sort = tk.StringVar(value="Recently modified")
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.window, padding=26)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="PROFILE LIBRARY", style="Title.TLabel").pack(side="left")
        ttk.Entry(header, textvariable=self.search, width=26).pack(side="left", padx=(18, 8))
        self.search.trace_add("write", lambda *_args: self.refresh())
        ttk.Label(header, text="Sort", style="Muted.TLabel").pack(side="left", padx=(0, 5))
        sort_box = ttk.Combobox(header, textvariable=self.sort, values=("Recently modified", "Name", "Favorites"), state="readonly", width=19)
        sort_box.pack(side="left")
        sort_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        list_panel = ttk.Frame(body, style="Panel.TFrame", padding=10)
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        preview_panel = ttk.Frame(body, style="Panel.TFrame", padding=16)
        preview_panel.grid(row=0, column=1, sticky="nsew")

        self.tree = ttk.Treeview(list_panel, columns=("tags", "favorite"), show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="PROFILE")
        self.tree.heading("tags", text="TAGS")
        self.tree.heading("favorite", text="FAV")
        self.tree.column("#0", width=170, stretch=True)
        self.tree.column("tags", width=180, stretch=True)
        self.tree.column("favorite", width=45, anchor="center", stretch=False)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())
        self.tree.bind("<Double-1>", lambda _event: self.load_selected())

        ttk.Label(preview_panel, text="PROFILE PREVIEW", style="Section.TLabel").pack(anchor="w")
        self.preview = tk.Canvas(preview_panel, width=240, height=190, bg=PREVIEW_BACKGROUND, highlightthickness=0)
        self.preview.pack(fill="x", pady=(12, 10))
        self.preview_name = ttk.Label(preview_panel, text="Select a profile", style="Section.TLabel")
        self.preview_name.pack(anchor="w")
        self.preview_details = ttk.Label(preview_panel, text="", style="Muted.TLabel", wraplength=280, justify="left")
        self.preview_details.pack(anchor="w", pady=(7, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(14, 0))
        actions_row_one = ttk.Frame(actions)
        actions_row_one.pack(fill="x")
        actions_row_two = ttk.Frame(actions)
        actions_row_two.pack(fill="x", pady=(6, 0))
        for parent, entries in (
            (actions_row_one, (("Save current", self.save_current), ("Load", self.load_selected), ("Update", self.update_selected), ("Rename", self.rename_selected), ("Duplicate", self.duplicate_selected), ("Delete", self.delete_selected))),
            (actions_row_two, (("Favorite", self.toggle_favorite), ("Compare 2", self.compare_selected), ("Import JSON", self.import_json), ("Export JSON", self.export_json), ("Import ZIP", self.import_zip), ("Export ZIP", self.export_zip))),
        ):
            for text, command in entries:
                ttk.Button(parent, text=text, command=command).pack(side="left", padx=(0, 6))
        self.status = ttk.Label(outer, text="Profiles are stored locally and never overwrite another name.", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(10, 0))

    def refresh(self, select_id: str | None = None) -> None:
        try:
            sort_mode = {"Name": "name", "Favorites": "favorites"}.get(self.sort.get(), "modified")
            profiles = self.store.list_profiles(self.search.get(), sort_mode)
        except ValueError as error:
            self._error(str(error))
            return
        self.tree.delete(*self.tree.get_children())
        for record in profiles:
            self.tree.insert("", "end", iid=record["id"], text=record["name"], values=(", ".join(record.get("tags", [])), "*" if record.get("favorite") else ""))
        if select_id and self.tree.exists(select_id):
            self.tree.selection_set(select_id)
            self.tree.focus(select_id)
            self.tree.see(select_id)
            self._show_selected()
        elif profiles:
            self.tree.selection_set(profiles[0]["id"])
            self._show_selected()
        else:
            self.preview.delete("all")
            self.preview_name.configure(text="No profiles found")
            self.preview_details.configure(text="Save the current design or import a profile file.")

    def _selected(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return self.store.get(selection[0])
        except ValueError as error:
            self._error(str(error))
            self.refresh()
            return None

    def _show_selected(self) -> None:
        record = self._selected()
        if record is None:
            return
        settings = validate_settings(record["settings"])
        self.preview.delete("all")
        self._draw_preview(settings)
        self.preview_name.configure(text=record["name"])
        tags = ", ".join(record.get("tags", [])) or "No tags"
        description = record.get("description") or "No description"
        colors = f"Fill {settings.color}"
        if settings.outline:
            colors += f"  /  Outline {settings.outline_color}"
        self.preview_details.configure(text=f"{description}\n\nTags: {tags}\nShape: {settings.shape}  /  {colors}\nArms: {settings.size} x {settings.vertical_size}px  /  Gap: {settings.gap}px")

    def _draw_preview(self, settings: Crosshair) -> None:
        # The shared renderer keeps this preview identical to the editor and the overlay.
        width = self.preview.winfo_width()
        height = self.preview.winfo_height()
        center_x = width // 2 if width > 1 else 120
        center_y = height // 2 if height > 1 else 95
        scale = fit_scale(settings, max(20, min(center_x, center_y) - 4))
        draw_on_canvas(self.preview, settings, center_x, center_y, scale, background=PREVIEW_BACKGROUND)

    def save_current(self) -> None:
        name = simpledialog.askstring("Save profile", "Profile name:", parent=self.window)
        if name is None:
            return
        description = simpledialog.askstring("Profile description", "Description (optional):", parent=self.window) or ""
        tags_text = simpledialog.askstring("Profile tags", "Tags, separated by commas (optional):", parent=self.window) or ""
        try:
            record = self.store.save(name, self.get_settings(), description, tags_text.split(","))
            self.status.configure(text=f'Saved "{record["name"]}".')
            self.refresh(record["id"])
        except ValueError as error:
            self._error(str(error))

    def load_selected(self) -> None:
        record = self._selected()
        if record is not None:
            self.apply_settings(validate_settings(record["settings"]))
            self.status.configure(text=f'Loaded "{record["name"]}" into the editor.')

    def update_selected(self) -> None:
        record = self._selected()
        if record is None:
            return
        try:
            updated = self.store.save(record["name"], self.get_settings(), record.get("description", ""), record.get("tags", []), record["id"], record.get("favorite", False))
            self.status.configure(text=f'Updated "{updated["name"]}".')
            self.refresh(updated["id"])
        except ValueError as error:
            self._error(str(error))

    def rename_selected(self) -> None:
        record = self._selected()
        if record is None:
            return
        name = simpledialog.askstring("Rename profile", "New name:", initialvalue=record["name"], parent=self.window)
        if name is None:
            return
        try:
            renamed = self.store.save(name, record["settings"], record.get("description", ""), record.get("tags", []), record["id"], record.get("favorite", False))
            self.refresh(renamed["id"])
        except ValueError as error:
            self._error(str(error))

    def duplicate_selected(self) -> None:
        record = self._selected()
        if record is None:
            return
        name = simpledialog.askstring("Duplicate profile", "Name for the copy:", initialvalue=f'{record["name"]} Copy', parent=self.window)
        if name is None:
            return
        try:
            duplicate = self.store.duplicate(record["id"], name)
            self.refresh(duplicate["id"])
        except ValueError as error:
            self._error(str(error))

    def delete_selected(self) -> None:
        record = self._selected()
        if record is None:
            return
        if not messagebox.askyesno("Delete profile", f'Delete "{record["name"]}"? This cannot be undone.', parent=self.window):
            return
        try:
            self.store.delete(record["id"])
            self.refresh()
        except ValueError as error:
            self._error(str(error))

    def toggle_favorite(self) -> None:
        record = self._selected()
        if record is None:
            return
        try:
            updated = self.store.set_favorite(record["id"], not record.get("favorite", False))
            self.refresh(updated["id"])
        except ValueError as error:
            self._error(str(error))

    def compare_selected(self) -> None:
        selection = self.tree.selection()
        if len(selection) != 2:
            messagebox.showinfo("Compare profiles", "Select exactly two profiles in the list.", parent=self.window)
            return
        try:
            records = [self.store.get(profile_id) for profile_id in selection]
        except ValueError as error:
            self._error(str(error))
            return
        compare = tk.Toplevel(self.window)
        compare.title("Compare Crosshairs")
        compare.geometry("820x460")
        compare.configure(bg=theme.BG)
        content = ttk.Frame(compare, padding=20)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        for column, record in enumerate(records):
            settings = validate_settings(record["settings"])
            panel = ttk.Frame(content, style="Panel.TFrame", padding=14)
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
            ttk.Label(panel, text=record["name"], style="Section.TLabel").pack(anchor="w")
            canvas = tk.Canvas(panel, bg=PREVIEW_BACKGROUND, height=270, highlightthickness=0)
            canvas.pack(fill="both", expand=True, pady=12)
            canvas.after_idle(self._draw_comparison, canvas, settings)
            colors = f"{settings.color} / outline {settings.outline_color}" if settings.outline else settings.color
            ttk.Label(panel, text=f"{settings.shape}  /  {colors}  /  {settings.size} x {settings.vertical_size}px  /  gap {settings.gap}px", style="Muted.TLabel").pack(anchor="w")

    @staticmethod
    def _draw_comparison(canvas: tk.Canvas, settings: Crosshair) -> None:
        # Both sides use the same center rule and the same scale of 1:1, so differences are real.
        draw_on_canvas(canvas, settings, canvas.winfo_width() // 2, canvas.winfo_height() // 2, background=PREVIEW_BACKGROUND)

    def import_json(self) -> None:
        source = filedialog.askopenfilename(parent=self.window, filetypes=(("Sightline profile", "*.json"), ("All files", "*.*")))
        if not source:
            return
        try:
            record = self.store.import_profile(source)
            self.status.configure(text=f'Imported "{record["name"]}".')
            self.refresh(record["id"])
        except ValueError as error:
            self._error(str(error))

    def export_json(self) -> None:
        record = self._selected()
        if record is None:
            return
        destination = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json", initialfile=f'{record["name"]}.json', filetypes=(("JSON profile", "*.json"),))
        if not destination:
            return
        try:
            self.store.export_profile(record["id"], destination)
            self.status.configure(text="Profile exported as JSON.")
        except (OSError, ValueError) as error:
            self._error(str(error))

    def import_zip(self) -> None:
        source = filedialog.askopenfilename(parent=self.window, filetypes=(("Profile archive", "*.zip"),))
        if not source:
            return
        try:
            imported = self.store.import_archive(source)
            self.status.configure(text=f"Imported {len(imported)} profile(s).")
            self.refresh(imported[-1]["id"] if imported else None)
        except ValueError as error:
            self._error(str(error))

    def export_zip(self) -> None:
        destination = filedialog.asksaveasfilename(parent=self.window, defaultextension=".zip", filetypes=(("ZIP archive", "*.zip"),))
        if not destination:
            return
        try:
            self.store.export_archive(destination)
            self.status.configure(text="All profiles exported to ZIP.")
        except (OSError, ValueError) as error:
            self._error(str(error))

    def _error(self, message: str) -> None:
        self.status.configure(text=message)
        messagebox.showerror("Profile manager", message, parent=self.window)
