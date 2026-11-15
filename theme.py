"""Colors, fonts and ttk styles shared by every Sightline window."""

from __future__ import annotations

from tkinter import ttk

BG = "#F3F4F8"
PANEL = "#FFFFFF"
RAISED = "#F0F1F7"
RAISED_HOVER = "#E5E7F1"
BUTTON = "#E9EAF2"
BUTTON_HOVER = "#DDE0EC"
BORDER = "#D9DCE8"
TEXT = "#3D4258"
TEXT_STRONG = "#191C2B"
MUTED = "#737990"
FAINT = "#A0A5B6"
ACCENT = "#6558F5"
ACCENT_HOVER = "#5548E6"
ACCENT_TEXT = "#FFFFFF"
OK = "#21865D"
WARN = "#B95737"
PREVIEW_BG = "#252A3A"

FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"


def _flat_button(style: ttk.Style, name: str, background: str, hover: str, foreground: str,
                 padding=(12, 8), font=(FONT_BOLD, 10)) -> None:
    """A button without clam's 3D bevel."""
    style.configure(name, font=font, padding=padding, background=background, foreground=foreground,
                    bordercolor=background, lightcolor=background, darkcolor=background,
                    focuscolor=background, borderwidth=0, relief="flat")
    style.map(name,
              background=[("active", hover), ("pressed", hover)],
              bordercolor=[("active", hover), ("pressed", hover)],
              lightcolor=[("active", hover), ("pressed", hover)],
              darkcolor=[("active", hover), ("pressed", hover)],
              foreground=[("disabled", FAINT)])


def configure_styles(root) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")

    # Drop-down lists are classic Tk listboxes and need their own colors.
    root.option_add("*TCombobox*Listbox.background", RAISED)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_TEXT)
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Raised.TFrame", background=RAISED)

    style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT, 10))
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=(FONT, 10))
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=(FONT, 9))
    style.configure("Dim.TLabel", background=PANEL, foreground=FAINT, font=(FONT, 10))
    style.configure("Value.TLabel", background=PANEL, foreground=ACCENT, font=(FONT_BOLD, 10))
    style.configure("DimValue.TLabel", background=PANEL, foreground=FAINT, font=(FONT_BOLD, 10))
    style.configure("Eyebrow.TLabel", background=PANEL, foreground=ACCENT, font=(FONT_BOLD, 8))
    style.configure("Warn.TLabel", background=PANEL, foreground=WARN, font=(FONT, 9))
    style.configure("Title.TLabel", background=BG, foreground=TEXT_STRONG, font=(FONT_BOLD, 22))
    style.configure("Brand.TLabel", background=BG, foreground=ACCENT, font=(FONT_BOLD, 21))
    style.configure("Section.TLabel", background=PANEL, foreground=TEXT_STRONG, font=(FONT_BOLD, 11))
    style.configure("Chip.TLabel", background=RAISED, foreground=ACCENT, font=(FONT_BOLD, 9), padding=(10, 5))
    style.configure("Status.TLabel", background=BG, foreground=TEXT, font=(FONT_BOLD, 9))
    style.configure("Header.TFrame", background=BG)

    _flat_button(style, "TButton", BUTTON, BUTTON_HOVER, TEXT_STRONG)
    _flat_button(style, "Accent.TButton", ACCENT, ACCENT_HOVER, ACCENT_TEXT, padding=(18, 9), font=(FONT_BOLD, 11))
    _flat_button(style, "Step.TButton", RAISED, RAISED_HOVER, TEXT_STRONG, padding=(0, 1), font=(FONT_BOLD, 11))
    _flat_button(style, "Small.TButton", BUTTON, BUTTON_HOVER, TEXT_STRONG, padding=(10, 5), font=(FONT_BOLD, 9))

    # Segmented control: radio buttons without the round indicator.
    style.layout("Segment.TRadiobutton", [
        ("Radiobutton.padding", {"sticky": "nswe", "children": [("Radiobutton.label", {"sticky": "nswe"})]}),
    ])
    style.configure("Segment.TRadiobutton", background=RAISED, foreground=MUTED, padding=(10, 8),
                    anchor="center", font=(FONT_BOLD, 9), borderwidth=0, focuscolor=RAISED)
    style.map("Segment.TRadiobutton",
              background=[("selected", ACCENT), ("active", RAISED_HOVER)],
              foreground=[("selected", ACCENT_TEXT), ("active", TEXT_STRONG), ("disabled", FAINT)])

    style.configure("Panel.TCheckbutton", background=PANEL, foreground=TEXT, font=(FONT, 9),
                    indicatorbackground=RAISED, indicatorforeground=ACCENT_TEXT,
                    upperbordercolor=BORDER, lowerbordercolor=BORDER, focuscolor=PANEL)
    style.map("Panel.TCheckbutton",
              background=[("active", PANEL)], foreground=[("active", TEXT_STRONG), ("disabled", FAINT)],
              indicatorbackground=[("selected", ACCENT), ("disabled", PANEL)])

    style.configure("TEntry", fieldbackground=RAISED, foreground=TEXT_STRONG, insertcolor=ACCENT,
                    bordercolor=BORDER, lightcolor=RAISED, darkcolor=RAISED, padding=6)
    style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", RAISED)])

    style.configure("TCombobox", fieldbackground=RAISED, background=RAISED, foreground=TEXT_STRONG,
                    arrowcolor=ACCENT, bordercolor=BORDER, lightcolor=RAISED, darkcolor=RAISED, padding=6)
    style.map("TCombobox",
              fieldbackground=[("readonly", RAISED)], foreground=[("readonly", TEXT_STRONG)],
              selectbackground=[("readonly", RAISED)], selectforeground=[("readonly", TEXT_STRONG)],
              background=[("active", RAISED_HOVER)])

    style.configure("Horizontal.TScale", background=ACCENT, troughcolor=BORDER, bordercolor=PANEL,
                    lightcolor=ACCENT, darkcolor=ACCENT, gripcount=0)
    style.map("Horizontal.TScale", background=[("disabled", FAINT), ("active", ACCENT_HOVER)],
              lightcolor=[("disabled", FAINT)], darkcolor=[("disabled", FAINT)])

    style.configure("Vertical.TScrollbar", background=RAISED, troughcolor=PANEL, bordercolor=PANEL,
                    arrowcolor=MUTED, lightcolor=RAISED, darkcolor=RAISED, gripcount=0)
    style.map("Vertical.TScrollbar", background=[("active", RAISED_HOVER)])

    # Used by the profile and import/export windows.
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(15, 9), background=RAISED, foreground=MUTED,
                    font=(FONT_BOLD, 9), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", BUTTON)], foreground=[("selected", ACCENT)])
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=32, borderwidth=0)
    style.configure("Treeview.Heading", background=RAISED, foreground=TEXT_STRONG, font=(FONT_BOLD, 9), padding=(8, 8))
    style.map("Treeview", background=[("selected", BUTTON_HOVER)], foreground=[("selected", TEXT_STRONG)])