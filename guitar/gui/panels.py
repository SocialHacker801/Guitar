"""Dashboard building blocks: path selectors, scan card, summary cards, reports page, About."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Callable, Optional

from .. import APP_NAME, APP_SUBTITLE, __version__
from ..state import PathCheck
from ..theme import Theme
from .widgets import (Field, PillButton, ProgressBar, RoundedCard, ScrollText, TFrame, TLabel,
                      ThemeManager)

LEVEL_TOKEN = {"empty": "text_faint", "ok": "success", "warn": "warning", "error": "error",
               "info": "text_muted"}


def shorten(path: str, limit: int = 46) -> str:
    """Middle-ellipsis for long paths (display only)."""
    if len(path) <= limit:
        return path
    keep = (limit - 1) // 2
    return path[:keep] + "\u2026" + path[-keep:]


# ======================================================================
class PathSelector(TFrame):
    """One independent folder selector: its own variable, entry, browse button and message."""

    def __init__(self, master, tm: ThemeManager, tag: str, caption: str, placeholder: str,
                 on_change: Callable[[str], None], on_browse: Callable[[], None]) -> None:
        super().__init__(master, tm, bg="panel")
        self.var = tk.StringVar()
        self.on_change = on_change
        self.columnconfigure(0, minsize=118)       # identical label column for SRC and DST
        self.columnconfigure(1, weight=1)
        tag_box = TFrame(self, tm, bg="panel")
        tag_box.grid(row=0, column=0, sticky="w", padx=(0, 14))
        TLabel(tag_box, tm, tag, font="section", fg="accent").pack(anchor="w")
        TLabel(tag_box, tm, caption, font="caption", fg="text_muted").pack(anchor="w")
        self.field = Field(self, tm, self.var, placeholder=placeholder, mono=False, icon="folder", height=42)
        self.field.grid(row=0, column=1, sticky="ew")
        self.browse = PillButton(self, tm, "Browse", on_browse, variant="secondary", icon="folder",
                                 height=42, radius=11, padx=14, surface="panel", font="body_bold")
        self.browse.grid(row=0, column=2, padx=(10, 0))
        self.msg = TLabel(self, tm, "", font="small", fg="text_faint", anchor="w", justify="left")
        self.msg.grid(row=1, column=1, columnspan=2, sticky="w", pady=(3, 0))
        self.var.trace_add("write", lambda *a: self.on_change(self.var.get()))

    def set_path(self, text: str) -> None:
        self.var.set(text)

    def set_message(self, check: PathCheck, override: Optional[tuple[str, str]] = None) -> None:
        level, text = override if override else (check.level, check.message)
        self.msg.configure(text=text)
        self.msg.set_tokens(fg=LEVEL_TOKEN.get(level, "text_muted"))

    def set_enabled(self, enabled: bool) -> None:
        self.field.entry.configure(state="normal" if enabled else "disabled")
        self.browse.set_enabled(enabled)


# ======================================================================
class ScanCard(RoundedCard):
    """Source/destination selection, Scan button, status line and progress."""

    def __init__(self, master, tm: ThemeManager, callbacks: dict) -> None:
        super().__init__(master, tm, surface="bg", fill="panel", radius=16, pad=18, auto_height=True)
        self.cb = callbacks
        b = self.body
        b.columnconfigure(0, weight=1)

        self.selectors = TFrame(b, tm, bg="panel")
        self.selectors.columnconfigure(0, weight=1)
        self.src = PathSelector(self.selectors, tm, "SRC", "Original source",
                                "Select or paste the original source folder",
                                callbacks["src_changed"], callbacks["browse_src"])
        self.dst = PathSelector(self.selectors, tm, "DST", "Git repository",
                                "Select or paste the Git repository folder",
                                callbacks["dst_changed"], callbacks["browse_dst"])
        self.src.grid(row=0, column=0, sticky="ew")
        self.dst.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.compact = TFrame(b, tm, bg="panel")
        self.compact_text = TLabel(self.compact, tm, "", font="body", fg="text_muted", anchor="w")
        self.compact_text.pack(side="left", fill="x", expand=True)
        self.edit_btn = PillButton(self.compact, tm, "Edit paths", callbacks["edit_paths"], variant="ghost",
                                   height=34, font="body_bold", padx=12)
        self.edit_btn.pack(side="right")

        side = TFrame(b, tm, bg="panel")
        self.side = side
        self.scan_btn = PillButton(side, tm, "Scan", callbacks["scan"], variant="primary", icon="scan",
                                   height=48, min_width=150, radius=14, icon_size=18)
        self.scan_btn.pack()
        self.hint = TLabel(side, tm, "F5  \u00b7  Ctrl+R", font="caption", fg="text_faint")
        self.hint.pack(pady=(4, 0))

        self.selectors.grid(row=0, column=0, sticky="ew")
        side.grid(row=0, column=1, sticky="n", padx=(18, 0), pady=(0, 0))
        self.compact.grid(row=0, column=0, sticky="ew")
        self.compact.grid_remove()

        status = TFrame(b, tm, bg="panel")
        status.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        status.columnconfigure(0, weight=1)
        self.status = TLabel(status, tm, "Ready. Select SRC and DST to begin.", font="small",
                             fg="text_muted", anchor="w")
        self.status.grid(row=0, column=0, sticky="w")
        self.progress_text = TLabel(status, tm, "", font="small", fg="text_faint")
        self.progress_text.grid(row=0, column=1, sticky="e")
        self.progress = ProgressBar(status, tm, surface="panel", height=6)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))

    def set_compact(self, compact: bool, src: str = "", dst: str = "") -> None:
        if compact:
            dash = "\u2014"
            self.compact_text.configure(
                text=f"SRC  {shorten(src) or dash}      \u2192      DST  {shorten(dst) or dash}")
            self.selectors.grid_remove()
            self.compact.grid()
            self.hint.pack_forget()
            self.scan_btn.configure(height=40)
        else:
            self.compact.grid_remove()
            self.selectors.grid()
            self.hint.pack(pady=(4, 0))
            self.scan_btn.configure(height=48)

    def set_status(self, text: str, level: str = "info") -> None:
        self.status.configure(text=text)
        self.status.set_tokens(fg=LEVEL_TOKEN.get(level, "text_muted"))

    def set_scanning(self, scanning: bool) -> None:
        self.scan_btn.set_enabled(not scanning)
        self.scan_btn.set_text("Scanning\u2026" if scanning else "Scan")
        self.src.set_enabled(not scanning)
        self.dst.set_enabled(not scanning)
        self.edit_btn.set_enabled(not scanning)


# ======================================================================
class SummaryCard(RoundedCard):
    """Clickable KPI card."""

    def __init__(self, master, tm: ThemeManager, label: str, dot_token: str,
                 on_click: Optional[Callable[[], None]] = None) -> None:
        super().__init__(master, tm, surface="bg", fill="panel", radius=14, pad=14, height=106,
                         cursor="hand2" if on_click else "")
        self.on_click = on_click
        b = self.body
        top = TFrame(b, tm, bg="panel")
        top.pack(fill="x")
        self.dot = TLabel(top, tm, "\u25cf", font="small", fg=dot_token)
        self.dot.pack(side="left")
        self.label = TLabel(top, tm, label, font="small_bold", fg="text_muted")
        self.label.pack(side="left", padx=(6, 0))
        self.value = TLabel(b, tm, "0", font="number", fg="text", anchor="w")
        self.value.pack(fill="x", pady=(2, 0))
        self.sub = TLabel(b, tm, "", font="caption", fg="text_faint", anchor="w")
        self.sub.pack(fill="x")
        if on_click:
            for w in self._walk(self.body):
                w.bind("<Button-1>", lambda e: self.on_click())
                w.bind("<Enter>", lambda e: self.set_look(fill="elevated", border="primary"))
                w.bind("<Leave>", lambda e: self._leave(e))
            self.bind("<Button-1>", lambda e: self.on_click())

    def _leave(self, e) -> None:
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        if w is not None and (w is self or str(w).startswith(str(self))):
            return
        self.set_look(fill="panel", border="border")

    def _walk(self, w):
        yield w
        for c in w.winfo_children():
            yield from self._walk(c)

    def set(self, value: int, sub: str = "") -> None:
        self.value.configure(text=f"{value:,}")
        self.sub.configure(text=sub)


# ======================================================================
class ReportsPage(tk.Frame):
    """Export controls and scan information."""

    def __init__(self, master, tm: ThemeManager, callbacks: dict) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self.tm, self.cb = tm, callbacks
        self.scope = "all"
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        card = RoundedCard(self, tm, surface="bg", fill="panel", radius=16, pad=20, auto_height=True)
        card.grid(row=0, column=0, sticky="ew")
        b = card.body
        TLabel(b, tm, "Export a report", font="heading").pack(anchor="w")
        TLabel(b, tm, "CSV and TXT reports include status, paths, findings, hashes, sizes and difference details.",
               font="small", fg="text_muted").pack(anchor="w", pady=(2, 12))
        row = TFrame(b, tm, bg="panel")
        row.pack(fill="x")
        TLabel(row, tm, "Include", font="small_bold", fg="text_muted").pack(side="left", padx=(0, 10))
        self.scope_btns: dict[str, PillButton] = {}
        for key, text in (("all", "All files"), ("problems", "Problems only"), ("view", "Current view")):
            btn = PillButton(row, tm, text, lambda k=key: self.set_scope(k), variant="secondary",
                             height=34, font="body_bold", padx=14)
            btn.pack(side="left", padx=(0, 6))
            self.scope_btns[key] = btn
        row2 = TFrame(b, tm, bg="panel")
        row2.pack(fill="x", pady=(14, 0))
        self.csv_btn = PillButton(row2, tm, "Export CSV", lambda: callbacks["export"]("csv"),
                                  variant="primary", icon="download", height=42, radius=12)
        self.csv_btn.pack(side="left")
        self.txt_btn = PillButton(row2, tm, "Export TXT", lambda: callbacks["export"]("txt"),
                                  variant="secondary", icon="download", height=42, radius=12)
        self.txt_btn.pack(side="left", padx=(10, 0))
        self.msg = TLabel(b, tm, "", font="small", fg="text_muted", anchor="w")
        self.msg.pack(fill="x", pady=(12, 0))

        info_card = RoundedCard(self, tm, surface="bg", fill="panel", radius=16, pad=2)
        info_card.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.info = ScrollText(info_card.body, tm, font="mono_small", wrap="word", horizontal=False)
        self.info.pack(fill="both", expand=True, padx=8, pady=8)
        tm.register(self)
        self.set_scope("all")

    def set_scope(self, scope: str) -> None:
        self.scope = scope
        for k, b in self.scope_btns.items():
            b.set_variant("selected" if k == scope else "secondary")

    def set_message(self, text: str, level: str = "info") -> None:
        self.msg.configure(text=text)
        self.msg.set_tokens(fg=LEVEL_TOKEN.get(level, "text_muted"))

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th.bg)
        f = self.tm.fonts
        t = self.info.text
        t.tag_configure("heading", font=f.section, foreground=th.accent_soft if th.name == "dark" else th.primary,
                        spacing1=8, spacing3=4)
        t.tag_configure("flabel", font=f.small_bold, foreground=th.text_muted, tabs=(150,), lmargin2=150)
        t.tag_configure("fvalue", font=f.mono_small, foreground=th.text)
        t.tag_configure("warn", font=f.body, foreground=th.warning, lmargin1=0)
        t.tag_configure("muted", font=f.small, foreground=th.text_faint)
        t.tag_configure("ign", font=f.mono_small, foreground=th.text_muted)

    def show_scan(self, scan, counts: dict) -> None:
        parts: list[tuple[str, str]] = []
        if scan is None:
            parts += [("Scan information\n", "heading"),
                      ("Run a scan to see its details and enable exports.\n", "muted")]
        else:
            parts += [("Scan information\n", "heading")]
            for k, v in (("Finished", f"{scan.finished_at}  ({scan.duration:.2f}s)"),
                         ("SRC", scan.src_root), ("DST", scan.dst_root),
                         ("Baseline", f"Git HEAD \u2014 {scan.head_summary}"),
                         ("Files scanned", f"{counts['total']:,}"),
                         ("Matching", f"{counts['match']:,}"),
                         ("Mismatched", f"{counts['mismatch']:,}"),
                         ("Not committed", f"{counts['not_committed']:,}"),
                         ("Missing from SRC", f"{counts['missing']:,}"),
                         ("Errors", f"{counts['error']:,}"),
                         ("Skipped (.gitignore)", f"{counts['ignored']:,}")):
                parts += [(k + "\t", "flabel"), (v + "\n", "fvalue")]
            if scan.warnings:
                parts += [("\nNotes\n", "heading")]
                parts += [(f"\u2022 {w}\n", "warn") for w in scan.warnings]
            parts += [("\nSkipped by .gitignore\n", "heading"),
                      ("These untracked paths match the root .gitignore, so Guitar did not report them. "
                       "Tracked files are never skipped.\n", "muted")]
            if scan.ignored:
                shown = scan.ignored[:500]
                parts += [(f"  {p}\n", "ign") for p in shown]
                if len(scan.ignored) > len(shown):
                    parts.append((f"  \u2026 and {len(scan.ignored) - len(shown):,} more\n", "muted"))
            else:
                parts.append(("  (none)\n", "muted"))
        self.info.set_content(parts)


# ======================================================================
def show_about(root: tk.Tk, tm: ThemeManager) -> None:
    top = tk.Toplevel(root)
    top.title(f"About {APP_NAME}")
    top.transient(root)
    top.resizable(False, False)
    tm.register(top, lambda th: top.configure(bg=th.bg))
    frame = TFrame(top, tm, bg="bg")
    frame.pack(padx=26, pady=22)
    TLabel(frame, tm, APP_NAME, font="title", bg="bg").pack(anchor="w")
    TLabel(frame, tm, f"{APP_SUBTITLE}  \u00b7  v{__version__}", font="small", fg="text_muted", bg="bg").pack(anchor="w")
    text = (
        "Guitar compares the files in a source folder (SRC) with the latest committed\n"
        "Git snapshot (HEAD) of a repository folder (DST). It is strictly read-only: it never\n"
        "modifies files, stages changes, commits or resets.\n\n"
        "Ignore rules: only the root .gitignore is honoured (nested, global and\n"
        ".git/info/exclude rules are not). Tracked files are always compared.\n\n"
        "Shortcuts:  F5 / Ctrl+R scan  \u00b7  Ctrl+F search  \u00b7  Ctrl+T switch theme  \u00b7  Esc clear search"
    )
    TLabel(frame, tm, text, font="body", fg="text", bg="bg", justify="left").pack(anchor="w", pady=(14, 14))
    PillButton(frame, tm, "Close", top.destroy, variant="primary", height=38, surface="bg").pack(anchor="e")
    top.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - top.winfo_reqwidth()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - top.winfo_reqheight()) // 3
    top.geometry(f"+{max(0, x)}+{max(0, y)}")
    top.bind("<Escape>", lambda e: top.destroy())
    top.focus_set()
