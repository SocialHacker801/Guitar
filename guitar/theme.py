"""Centralised design system: colour tokens, typography and spacing.

Every colour used by the GUI is a token on :class:`Theme`.  Widgets read tokens
by name, so switching themes is a matter of re-applying a different instance.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from tkinter import font as tkfont
from typing import Optional


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    # surfaces
    bg: str               # application background
    sidebar: str
    panel: str            # main cards / panels
    elevated: str         # raised panels, table headers
    input_bg: str
    border: str
    # accents
    primary: str
    primary_hover: str
    primary_active: str
    on_primary: str       # text on primary fills
    accent: str           # bright lavender
    accent_soft: str      # soft lavender
    # text
    text: str
    text_muted: str
    text_faint: str
    # interaction
    hover_bg: str
    selection_bg: str
    focus: str
    # status
    success: str
    warning: str
    error: str
    # diff viewer
    diff_add_bg: str
    diff_add_fg: str
    diff_del_bg: str
    diff_del_fg: str
    diff_hunk_fg: str
    # scrollbars / progress
    scroll_trough: str
    scroll_thumb: str
    scroll_thumb_hover: str
    track: str

    def __getitem__(self, token: str) -> str:
        return getattr(self, token)

    def tokens(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name not in ("name", "label")}


DARK = Theme(
    name="dark", label="Dark Violet",
    bg="#100C19", sidebar="#171126", panel="#1F1830", elevated="#28203D",
    input_bg="#171126", border="#392D50",
    primary="#8B5CF6", primary_hover="#9D75F8", primary_active="#7C47EC",
    on_primary="#FFFFFF", accent="#A78BFA", accent_soft="#C4B5FD",
    text="#F5F3FF", text_muted="#B7ADC9", text_faint="#8378A0",
    hover_bg="#2D2446", selection_bg="#3B2D63", focus="#A78BFA",
    success="#34D399", warning="#FBBF24", error="#FB7185",
    diff_add_bg="#12372C", diff_add_fg="#6EE7B7",
    diff_del_bg="#431B2B", diff_del_fg="#FDA4AF",
    diff_hunk_fg="#C4B5FD",
    scroll_trough="#1F1830", scroll_thumb="#4A3C69", scroll_thumb_hover="#6A58A0",
    track="#392D50",
)

LIGHT = Theme(
    name="light", label="Light Lavender",
    bg="#F6F3FF", sidebar="#EDE8FD", panel="#FFFFFF", elevated="#F4F0FF",
    input_bg="#F8F5FF", border="#D6CCF0",
    primary="#6D28D9", primary_hover="#7C3AED", primary_active="#5B21B6",
    on_primary="#FFFFFF", accent="#7C3AED", accent_soft="#5B21B6",
    text="#1E1033", text_muted="#5F5378", text_faint="#8A7FA3",
    hover_bg="#F0EAFF", selection_bg="#E4DAFC", focus="#7C3AED",
    success="#047857", warning="#B45309", error="#BE123C",
    diff_add_bg="#D9F5E8", diff_add_fg="#065F46",
    diff_del_bg="#FCE0E7", diff_del_fg="#9F1239",
    diff_hunk_fg="#5B21B6",
    scroll_trough="#F4F0FF", scroll_thumb="#CDBFF0", scroll_thumb_hover="#A994E0",
    track="#E4DDF7",
)

THEMES = {"dark": DARK, "light": LIGHT}


def status_token(status_value: str) -> str:
    """Theme token used to colour a Status value."""
    return {
        "MATCH": "success",
        "MISMATCH": "error",
        "NOT COMMITTED": "warning",
        "MISSING FROM SOURCE": "warning",
        "ERROR": "error",
    }.get(status_value, "text_muted")


# --------------------------------------------------------------------------
# Spacing / geometry
# --------------------------------------------------------------------------
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = {"sm": 8, "md": 12, "lg": 16}
SIDEBAR_WIDTH = 236
HEADER_HEIGHT = 68


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------
def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def blend(c1: str, c2: str, t: float) -> str:
    """Linear blend: t=0 -> c1, t=1 -> c2."""
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------
UI_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
               "Helvetica Neue", "Ubuntu", "DejaVu Sans", "Helvetica", "Arial"]
MONO_FAMILIES = ["Cascadia Mono", "JetBrains Mono", "Consolas", "SF Mono",
                 "Menlo", "DejaVu Sans Mono", "Liberation Mono", "Courier New"]


def _pick(available: set[str], wanted: list[str], fallback: str) -> str:
    for fam in wanted:
        if fam in available:
            return fam
    return fallback


class Fonts:
    """Named font objects created once; changing a font here restyles the app."""

    def __init__(self, root) -> None:
        available = set(tkfont.families(root))
        ui = _pick(available, UI_FAMILIES, "TkDefaultFont")
        mono = _pick(available, MONO_FAMILIES, "TkFixedFont")
        F = lambda **kw: tkfont.Font(root=root, **kw)
        self.ui_family, self.mono_family = ui, mono
        self.title = F(family=ui, size=17, weight="bold")
        self.heading = F(family=ui, size=13, weight="bold")
        self.section = F(family=ui, size=11, weight="bold")
        self.body = F(family=ui, size=10)
        self.body_bold = F(family=ui, size=10, weight="bold")
        self.small = F(family=ui, size=9)
        self.small_bold = F(family=ui, size=9, weight="bold")
        self.caption = F(family=ui, size=8)
        self.number = F(family=ui, size=24, weight="bold")
        self.button = F(family=ui, size=10, weight="bold")
        self.nav = F(family=ui, size=11)
        self.nav_active = F(family=ui, size=11, weight="bold")
        self.mono = F(family=mono, size=10)
        self.mono_small = F(family=mono, size=9)

    def get(self, name: str) -> tkfont.Font:
        return getattr(self, name)
