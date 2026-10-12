"""Reusable, theme-aware widgets.

Everything registers with the :class:`ThemeManager`.  Switching theme calls
``apply_theme`` on each live widget (configure + redraw) — no widget is
destroyed or recreated, so entry text, scroll positions, selections and
results survive a theme change.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..theme import Fonts, Theme, blend
from . import icons
from .icons import round_rect


# ======================================================================
# Theme manager
# ======================================================================
class ThemeManager:
    def __init__(self, root: tk.Tk, fonts: Fonts, theme: Theme) -> None:
        self.root = root
        self.fonts = fonts
        self.theme = theme
        self._items: list[tuple[tk.Misc, Callable[[Theme], None]]] = []
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")      # the only stock theme that honours colours everywhere
        except tk.TclError:
            pass
        self._configure_ttk(theme)

    # -- registration -----------------------------------------------------
    def register(self, widget: tk.Misc, fn: Optional[Callable[[Theme], None]] = None) -> None:
        fn = fn or widget.apply_theme          # type: ignore[attr-defined]
        self._items.append((widget, fn))
        fn(self.theme)

    def apply(self, theme: Theme) -> None:
        """Re-skin every live widget in place."""
        self.theme = theme
        self.root.configure(bg=theme.bg)
        self._configure_ttk(theme)
        alive = []
        for widget, fn in self._items:
            try:
                if widget.winfo_exists():
                    fn(theme)
                    alive.append((widget, fn))
            except tk.TclError:
                continue
        self._items = alive

    # -- ttk styles ---------------------------------------------------------
    def _configure_ttk(self, th: Theme) -> None:
        s, f = self.style, self.fonts
        s.configure("Guitar.Treeview", background=th.panel, fieldbackground=th.panel,
                    foreground=th.text, borderwidth=0, relief="flat", rowheight=38,
                    font=f.body, lightcolor=th.panel, darkcolor=th.panel, bordercolor=th.panel)
        s.map("Guitar.Treeview",
              background=[("selected", th.selection_bg)],
              foreground=[("selected", th.text)])
        s.layout("Guitar.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Guitar.Treeview.Heading", background=th.elevated, foreground=th.text_muted,
                    relief="flat", borderwidth=0, font=f.small_bold, padding=(12, 9),
                    lightcolor=th.elevated, darkcolor=th.elevated, bordercolor=th.elevated)
        s.map("Guitar.Treeview.Heading",
              background=[("active", th.hover_bg)], foreground=[("active", th.text)])
        for orient, trough_el, thumb_el in (
            ("Vertical", "Vertical.Scrollbar.trough", "Vertical.Scrollbar.thumb"),
            ("Horizontal", "Horizontal.Scrollbar.trough", "Horizontal.Scrollbar.thumb"),
        ):
            name = f"Guitar.{orient}.TScrollbar"
            s.layout(name, [(trough_el, {"sticky": "nswe", "children": [(thumb_el, {"expand": "1", "sticky": "nswe"})]})])
            s.configure(name, background=th.scroll_thumb, troughcolor=th.scroll_trough,
                        bordercolor=th.scroll_trough, lightcolor=th.scroll_thumb,
                        darkcolor=th.scroll_thumb, relief="flat", borderwidth=0,
                        gripcount=0, arrowsize=11, width=11)
            s.map(name, background=[("active", th.scroll_thumb_hover), ("pressed", th.accent)],
                  lightcolor=[("active", th.scroll_thumb_hover), ("pressed", th.accent)],
                  darkcolor=[("active", th.scroll_thumb_hover), ("pressed", th.accent)])


# ======================================================================
# Basic themed Tk widgets
# ======================================================================
class TFrame(tk.Frame):
    def __init__(self, master, tm: ThemeManager, bg: str = "panel", **kw) -> None:
        kw.setdefault("bd", 0)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self.tm = tm
        self.bg_tok = bg
        tm.register(self)

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th[self.bg_tok])

    def set_bg(self, token: str) -> None:
        self.bg_tok = token
        self.apply_theme(self.tm.theme)


class TLabel(tk.Label):
    def __init__(self, master, tm: ThemeManager, text: str = "", font: str = "body",
                 fg: str = "text", bg: str = "panel", **kw) -> None:
        kw.setdefault("bd", 0)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, text=text, font=tm.fonts.get(font), **kw)
        self.tm = tm
        self.fg_tok, self.bg_tok = fg, bg
        tm.register(self)

    def apply_theme(self, th: Theme) -> None:
        self.configure(fg=th[self.fg_tok], bg=th[self.bg_tok])

    def set_tokens(self, fg: Optional[str] = None, bg: Optional[str] = None) -> None:
        if fg:
            self.fg_tok = fg
        if bg:
            self.bg_tok = bg
        self.apply_theme(self.tm.theme)


# ======================================================================
# Rounded card
# ======================================================================
class RoundedCard(tk.Canvas):
    """A canvas-drawn rounded panel with a ``body`` frame for child widgets."""

    def __init__(self, master, tm: ThemeManager, surface: str = "bg", fill: str = "panel",
                 border: str = "border", radius: int = 14, pad: int = 16,
                 auto_height: bool = False, height: int = 40, cursor: str = "") -> None:
        super().__init__(master, highlightthickness=0, bd=0, height=height, cursor=cursor)
        self.tm = tm
        self.surface, self.fill_tok, self.border_tok = surface, fill, border
        self.radius, self.pad, self.auto_height = radius, pad, auto_height
        self.border_width = 1
        self.body = tk.Frame(self, bd=0, highlightthickness=0, cursor=cursor)
        self._win = self.create_window(pad, pad, window=self.body, anchor="nw")
        self.bind("<Configure>", self._on_resize)
        if auto_height:
            self.body.bind("<Configure>", self._on_body)
        tm.register(self)

    def _on_resize(self, e) -> None:
        w, h = max(1, e.width - 2 * self.pad), max(1, e.height - 2 * self.pad)
        self.itemconfigure(self._win, width=w, **({} if self.auto_height else {"height": h}))
        self._redraw()

    def _on_body(self, _e=None) -> None:
        want = self.body.winfo_reqheight() + 2 * self.pad
        if abs(want - int(float(self.cget("height")))) > 0:
            self.configure(height=want)

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th[self.surface])
        self.body.configure(bg=th[self.fill_tok])
        self._redraw()

    def set_look(self, fill: Optional[str] = None, border: Optional[str] = None,
                 border_width: Optional[int] = None) -> None:
        if fill:
            self.fill_tok = fill
            self.body.configure(bg=self.tm.theme[fill])
        if border:
            self.border_tok = border
        if border_width:
            self.border_width = border_width
        self._redraw()

    def _redraw(self) -> None:
        th = self.tm.theme
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("card_bg")
        if w < 4 or h < 4:
            return
        o = self.border_width / 2
        round_rect(self, o, o, w - o, h - o, self.radius, fill=th[self.fill_tok],
                   outline=th[self.border_tok], width=self.border_width, tags="card_bg")
        self.tag_lower("card_bg")


# ======================================================================
# Buttons
# ======================================================================
class PillButton(tk.Canvas):
    """Rounded button with hover/pressed/focus/disabled states and a short colour fade."""

    def __init__(self, master, tm: ThemeManager, text: str = "", command: Optional[Callable] = None,
                 variant: str = "primary", icon: Optional[str] = None, height: int = 40,
                 min_width: int = 0, surface: str = "panel", font: str = "button",
                 radius: Optional[int] = None, icon_size: int = 16, padx: int = 18) -> None:
        self.tm = tm
        self.text, self.command, self.variant, self.icon = text, command, variant, icon
        self.font_name, self.surface, self.icon_size = font, surface, icon_size
        self.radius = radius if radius is not None else height // 2
        self.padx = padx
        self.enabled = True
        self._t = 0.0
        self._target = 0.0
        self._pressed = False
        self._focused = False
        self._after: Optional[str] = None
        width = max(min_width, self._content_width() + 2 * padx)
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=1)
        self.bind("<Enter>", lambda e: self._hover(1.0))
        self.bind("<Leave>", lambda e: self._hover(0.0))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.bind("<Key-space>", lambda e: self._invoke())
        self.bind("<Key-Return>", lambda e: self._invoke())
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Destroy>", lambda e: self._cancel())
        tm.register(self)

    # -- sizing ---------------------------------------------------------------
    def _content_width(self) -> int:
        f = self.tm.fonts.get(self.font_name)
        if not self.icon:
            return f.measure(self.text)
        return self.icon_size + (8 + f.measure(self.text) if self.text else 0)

    def set_text(self, text: str) -> None:
        self.text = text
        self.configure(width=max(int(float(self.cget("width"))), self._content_width() + 2 * self.padx))
        self._draw()

    def set_variant(self, variant: str) -> None:
        self.variant = variant
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow", takefocus=1 if enabled else 0)
        self._t = self._target = 0.0
        self._draw()

    # -- interaction ------------------------------------------------------------
    def _hover(self, target: float) -> None:
        if not self.enabled:
            return
        self._target = target
        if self._after is None:
            self._step()

    def _step(self) -> None:
        self._after = None
        diff = self._target - self._t
        if abs(diff) < 0.05:
            self._t = self._target
        else:
            self._t += diff * 0.45
            self._after = self.after(16, self._step)
        self._draw()

    def _cancel(self) -> None:
        if self._after:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _press(self, _e) -> None:
        if self.enabled:
            self._pressed = True
            self.focus_set()
            self._draw()

    def _release(self, e) -> None:
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self._invoke()

    def _set_focus(self, v: bool) -> None:
        self._focused = v
        self._draw()

    def _invoke(self) -> None:
        if self.enabled and self.command:
            self.command()

    # -- drawing ------------------------------------------------------------------
    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th[self.surface])
        self._draw()

    def _palette(self, th: Theme) -> tuple[str, str, str]:
        v = self.variant
        if not self.enabled:
            return blend(th[self.surface], th.track, 0.6), th.text_faint, ""
        if v == "primary":
            base = th.primary_active if self._pressed else blend(th.primary, th.primary_hover, self._t)
            return base, th.on_primary, ""
        if v == "secondary":
            base = th.selection_bg if self._pressed else blend(th.elevated, th.hover_bg, self._t)
            return base, th.text, th.border
        if v == "selected":
            return th.selection_bg, th.accent_soft if th.name == "dark" else th.primary, th.primary
        base = th.selection_bg if self._pressed else blend(th[self.surface], th.hover_bg, self._t)   # ghost
        return base, blend(th.text_muted, th.text, self._t), ""

    def _draw(self) -> None:
        th = self.tm.theme
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            w, h = int(float(self.cget("width"))), int(float(self.cget("height")))
        self.delete("all")
        fill, fg, outline = self._palette(th)
        round_rect(self, 1, 1, w - 1, h - 1, self.radius, fill=fill, outline=outline, width=1)
        if self._focused and self.enabled:
            round_rect(self, 2, 2, w - 2, h - 2, self.radius, fill="", outline=th.focus, width=2)
        f = self.tm.fonts.get(self.font_name)
        cw = self._content_width()
        x = (w - cw) / 2
        if self.icon:
            icons.draw_icon(self, self.icon, x + self.icon_size / 2, h / 2, self.icon_size, fg, 1.7)
            x += self.icon_size + 8
        if self.text:
            self.create_text(x, h / 2, text=self.text, font=f, fill=fg, anchor="w")


class ThemeToggle(tk.Canvas):
    """Sun/moon switch. The knob slides; icons and colours follow the theme."""

    W, H = 78, 36

    def __init__(self, master, tm: ThemeManager, mode: str, command: Callable[[str], None],
                 surface: str = "bg") -> None:
        super().__init__(master, width=self.W, height=self.H, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=1)
        self.tm, self.command, self.surface = tm, command, surface
        self.mode = mode
        self._pos = 1.0 if mode == "dark" else 0.0
        self._hover = False
        self._focused = False
        self._after: Optional[str] = None
        self.bind("<Button-1>", lambda e: self.toggle())
        self.bind("<Key-space>", lambda e: self.toggle())
        self.bind("<Key-Return>", lambda e: self.toggle())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.bind("<Destroy>", lambda e: self._cancel())
        tm.register(self)

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _set_focus(self, v):
        self._focused = v
        self._draw()

    def _cancel(self):
        if self._after:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def toggle(self) -> None:
        self.command("light" if self.mode == "dark" else "dark")

    def set_mode(self, mode: str, animate: bool = True) -> None:
        self.mode = mode
        if not animate:
            self._pos = 1.0 if mode == "dark" else 0.0
            self._draw()
            return
        self._cancel()
        self._animate()

    def _animate(self) -> None:
        target = 1.0 if self.mode == "dark" else 0.0
        diff = target - self._pos
        if abs(diff) < 0.04:
            self._pos = target
            self._after = None
        else:
            self._pos += diff * 0.4
            self._after = self.after(14, self._animate)
        self._draw()

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th[self.surface])
        self._draw()

    def _draw(self) -> None:
        th = self.tm.theme
        W, H = self.W, self.H
        self.delete("all")
        track = th.elevated if th.name == "dark" else th.selection_bg
        border = th.accent if (self._hover or self._focused) else th.border
        round_rect(self, 1, 1, W - 1, H - 1, H // 2, fill=track, outline=border,
                   width=2 if self._focused else 1)
        icons.draw_icon(self, "sun", 20, H / 2, 15, th.text_faint, 1.5)
        icons.draw_icon(self, "moon", W - 20, H / 2, 15, th.text_faint, 1.5)
        r = H / 2 - 4
        kx = 4 + r + self._pos * (W - 8 - 2 * r)
        self.create_oval(kx - r, H / 2 - r, kx + r, H / 2 + r, fill=th.primary, outline="")
        icons.draw_icon(self, "moon" if self._pos > 0.5 else "sun", kx, H / 2, 15, th.on_primary, 1.6)


class NavItem(tk.Canvas):
    """Sidebar row: outline icon + label + optional count badge."""

    def __init__(self, master, tm: ThemeManager, label: str, icon: str,
                 command: Callable[[], None], badge_kind: str = "") -> None:
        super().__init__(master, height=46, highlightthickness=0, bd=0, cursor="hand2", takefocus=1)
        self.tm, self.label, self.icon, self.command = tm, label, icon, command
        self.badge_kind = badge_kind          # "" | "muted" | "problem"
        self.count: Optional[int] = None
        self.active = False
        self._hover = False
        self._focused = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set("_hover", True))
        self.bind("<Leave>", lambda e: self._set("_hover", False))
        self.bind("<FocusIn>", lambda e: self._set("_focused", True))
        self.bind("<FocusOut>", lambda e: self._set("_focused", False))
        self.bind("<Button-1>", lambda e: (self.focus_set(), self.command()))
        self.bind("<Key-space>", lambda e: self.command())
        self.bind("<Key-Return>", lambda e: self.command())
        tm.register(self)

    def _set(self, attr: str, v: bool) -> None:
        setattr(self, attr, v)
        self._draw()

    def set_active(self, v: bool) -> None:
        self.active = v
        self._draw()

    def set_count(self, n: Optional[int]) -> None:
        self.count = n
        self._draw()

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th.sidebar)
        self._draw()

    def _draw(self) -> None:
        th, f = self.tm.theme, self.tm.fonts
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        if w < 10:
            return
        if self.active:
            fill = th.selection_bg
        elif self._hover:
            fill = th.hover_bg
        else:
            fill = th.sidebar
        round_rect(self, 8, 3, w - 8, h - 3, 11, fill=fill, outline=th.focus if self._focused else "",
                   width=2 if self._focused else 1)
        if self.active:
            round_rect(self, 8, 12, 12, h - 12, 2, fill=th.primary, outline="")
        col = th.text if self.active else (th.text if self._hover else th.text_muted)
        icon_col = th.accent if self.active else col
        icons.draw_icon(self, self.icon, 34, h / 2, 20, icon_col, 1.7)
        self.create_text(58, h / 2, text=self.label, anchor="w", fill=col,
                         font=f.nav_active if self.active else f.nav)
        if self.count is not None:
            txt = str(self.count) if self.count < 100000 else "99k+"
            bw = max(26, f.small_bold.measure(txt) + 16)
            problem = self.badge_kind == "problem" and self.count > 0
            bg = blend(th.error, th.sidebar, 0.78) if problem else blend(th.accent, th.sidebar, 0.8)
            if self.active:
                bg = blend(bg, th.selection_bg, 0.4)
            fg = th.error if problem else th.text_muted
            round_rect(self, w - 18 - bw, h / 2 - 10, w - 18, h / 2 + 10, 10, fill=bg, outline="")
            self.create_text(w - 18 - bw / 2, h / 2, text=txt, font=f.small_bold, fill=fg)


class ProgressBar(tk.Canvas):
    """Thin rounded progress bar; determinate or an animated indeterminate sweep."""

    def __init__(self, master, tm: ThemeManager, surface: str = "panel", height: int = 6) -> None:
        super().__init__(master, height=height, highlightthickness=0, bd=0)
        self.tm, self.surface = tm, surface
        self.value = 0.0
        self.indeterminate = False
        self._phase = 0.0
        self._after: Optional[str] = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Destroy>", lambda e: self._stop_anim())
        tm.register(self)

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th[self.surface])
        self._draw()

    def set(self, value: float) -> None:
        self.value = max(0.0, min(1.0, value))
        self._draw()

    def start(self) -> None:
        self.indeterminate = True
        if self._after is None:
            self._tick()

    def stop(self, value: float = 0.0) -> None:
        self.indeterminate = False
        self._stop_anim()
        self.value = value
        self._draw()

    def _stop_anim(self) -> None:
        if self._after:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _tick(self) -> None:
        self._phase = (self._phase + 0.025) % 1.0
        self._draw()
        self._after = self.after(30, self._tick) if self.indeterminate else None

    def _draw(self) -> None:
        th = self.tm.theme
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        if w < 4:
            return
        round_rect(self, 0, 0, w, h, h / 2, fill=th.track, outline="")
        if self.indeterminate:
            seg = w * 0.28
            x = -seg + (w + seg) * self._phase
            x1, x2 = max(0, x), min(w, x + seg)
            if x2 - x1 > 2:
                round_rect(self, x1, 0, x2, h, h / 2, fill=th.primary, outline="")
        elif self.value > 0:
            round_rect(self, 0, 0, max(h, w * self.value), h, h / 2, fill=th.primary, outline="")


class Badge(tk.Canvas):
    """Small status pill: tinted background with a coloured dot and label."""

    def __init__(self, master, tm: ThemeManager, surface: str = "panel") -> None:
        super().__init__(master, width=10, height=26, highlightthickness=0, bd=0)
        self.tm, self.surface = tm, surface
        self.text, self.token = "", "text_muted"
        tm.register(self)

    def set(self, text: str, token: str) -> None:
        self.text, self.token = text, token
        self._draw()

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th[self.surface])
        self._draw()

    def _draw(self) -> None:
        th, f = self.tm.theme, self.tm.fonts.small_bold
        self.delete("all")
        if not self.text:
            self.configure(width=1)
            return
        w = f.measure(self.text) + 36
        self.configure(width=w)
        col = th[self.token]
        round_rect(self, 0, 0, w, 26, 13, fill=blend(col, th[self.surface], 0.82), outline=blend(col, th[self.surface], 0.55))
        self.create_oval(11, 10, 17, 16, fill=col, outline="")
        self.create_text(24, 13, text=self.text, font=f, fill=col, anchor="w")


# ======================================================================
# Entry fields
# ======================================================================
class Field(RoundedCard):
    """Rounded single-line input with focus ring, optional icon and clear button."""

    def __init__(self, master, tm: ThemeManager, textvariable: tk.StringVar, placeholder: str = "",
                 icon: Optional[str] = None, clearable: bool = False, mono: bool = False,
                 surface: str = "panel", height: int = 42) -> None:
        super().__init__(master, tm, surface=surface, fill="input_bg", radius=11, pad=0, height=height)
        self.var, self.placeholder, self.icon, self.clearable = textvariable, placeholder, icon, clearable
        self._focused = False
        f = tm.fonts.mono if mono else tm.fonts.body
        inner = self.body
        if icon:
            self.icon_cv = tk.Canvas(inner, width=34, height=height, highlightthickness=0, bd=0)
            self.icon_cv.pack(side="left")
        else:
            self.icon_cv = None
        self.clear_cv: Optional[tk.Canvas] = None
        if clearable:
            self.clear_cv = tk.Canvas(inner, width=34, height=height, highlightthickness=0, bd=0, cursor="hand2")
            self.clear_cv.pack(side="right")
            self.clear_cv.bind("<Button-1>", lambda e: self.clear())
        self.entry = tk.Entry(inner, textvariable=textvariable, font=f, relief="flat", bd=0,
                              highlightthickness=0, insertwidth=2)
        self.entry.pack(side="left", fill="both", expand=True, padx=(0 if icon else 14, 8), pady=10)
        self.ph = tk.Label(inner, text=placeholder, font=f, bd=0, anchor="w", cursor="xterm")
        self.ph.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self._focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._focus(False))
        self.var.trace_add("write", lambda *a: self._refresh())
        tm.register(self, self._themed)
        self._refresh()

    def clear(self) -> None:
        self.var.set("")
        self.entry.focus_set()

    def _focus(self, v: bool) -> None:
        self._focused = v
        self.set_look(border="focus" if v else "border", border_width=2 if v else 1)
        self._refresh()

    def _refresh(self) -> None:
        empty = not self.var.get()
        if empty and self.placeholder:
            self.ph.place(in_=self.entry, x=0, y=0, relheight=1, relwidth=1)
        else:
            self.ph.place_forget()
        if self.clear_cv is not None:
            self.clear_cv.pack_forget() if empty else self.clear_cv.pack(side="right", before=self.entry)
            self._draw_clear()

    def _draw_clear(self) -> None:
        if self.clear_cv is None:
            return
        th = self.tm.theme
        self.clear_cv.delete("all")
        h = int(float(self.clear_cv.cget("height")))
        icons.draw_icon(self.clear_cv, "close", 17, h / 2, 15, th.text_muted, 1.6)

    def _themed(self, th: Theme) -> None:
        RoundedCard.apply_theme(self, th)
        bg = th.input_bg
        self.entry.configure(bg=bg, fg=th.text, insertbackground=th.accent,
                             selectbackground=th.primary, selectforeground=th.on_primary,
                             disabledbackground=bg, readonlybackground=bg)
        self.ph.configure(bg=bg, fg=th.text_faint)
        for cv in (self.icon_cv, self.clear_cv):
            if cv is not None:
                cv.configure(bg=bg)
        if self.icon_cv is not None:
            self.icon_cv.delete("all")
            h = int(float(self.icon_cv.cget("height")))
            icons.draw_icon(self.icon_cv, self.icon, 18, h / 2, 16, th.text_faint, 1.6)
        self._draw_clear()
        self.set_look(border="focus" if self._focused else "border")

    def apply_theme(self, th: Theme) -> None:   # RoundedCard registers itself first
        RoundedCard.apply_theme(self, th)


# ======================================================================
# Scrollable read-only text
# ======================================================================
class ScrollText(tk.Frame):
    """Read-only Text with themed scrollbars. Selection and copy still work."""

    def __init__(self, master, tm: ThemeManager, font: str = "mono_small", wrap: str = "none",
                 horizontal: bool = True) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self.tm = tm
        self.text = tk.Text(self, wrap=wrap, bd=0, highlightthickness=0, relief="flat",
                            font=tm.fonts.get(font), padx=14, pady=10, cursor="arrow",
                            undo=False, takefocus=1, spacing1=1, spacing3=1)
        self.vbar = ttk.Scrollbar(self, orient="vertical", style="Guitar.Vertical.TScrollbar",
                                  command=self.text.yview)
        self.text.configure(yscrollcommand=self.vbar.set)
        self.hbar = None
        if horizontal and wrap == "none":
            self.hbar = ttk.Scrollbar(self, orient="horizontal", style="Guitar.Horizontal.TScrollbar",
                                      command=self.text.xview)
            self.text.configure(xscrollcommand=self.hbar.set)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.text.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        if self.hbar:
            self.hbar.grid(row=1, column=0, sticky="ew")
        self.text.configure(state="disabled")
        # allow Ctrl+C / select-all while read-only
        self.text.bind("<Button-1>", lambda e: self.text.focus_set())
        self.text.bind("<Control-a>", self._select_all)
        self.text.bind("<Control-A>", self._select_all)
        tm.register(self)

    def _select_all(self, _e) -> str:
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def set_content(self, parts: list[tuple[str, str]]) -> None:
        """Replace the content with ``(text, tag)`` parts (single insert call)."""
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        args: list[str] = []
        for txt, tag in parts:
            args.append(txt)
            args.append(tag)
        if args:
            t.insert("end", *args)
        t.configure(state="disabled")
        t.yview_moveto(0)
        t.xview_moveto(0)

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th.panel)
        self.text.configure(bg=th.input_bg, fg=th.text, selectbackground=th.primary,
                            selectforeground=th.on_primary, inactiveselectbackground=th.selection_bg,
                            insertbackground=th.input_bg)
