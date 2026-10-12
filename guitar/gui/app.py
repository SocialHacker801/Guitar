"""Main window: composition, navigation, background scanning and theme switching."""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox
from typing import Optional

from .. import APP_NAME, APP_SUBTITLE
from ..details import DetailsProvider
from ..git_backend import RepoError
from ..reports import ReportError, export_csv, export_txt
from ..scanner import ScanCancelled, ScanError, scan
from ..settings import load_settings, save_settings
from ..state import (RESULT_VIEWS, VIEW_ALL, VIEW_DASHBOARD, VIEW_MATCHING, VIEW_PROBLEMS,
                     VIEW_REPORTS, AppState, PathCheck, check_dst, check_src)
from ..theme import HEADER_HEIGHT, SIDEBAR_WIDTH, THEMES, Fonts
from . import icons
from .panels import PathSelector, ReportsPage, ScanCard, SummaryCard, show_about
from .results import ResultsPanel
from .widgets import NavItem, PillButton, RoundedCard, TFrame, TLabel, ThemeManager, ThemeToggle

NAV = [
    (VIEW_DASHBOARD, "Dashboard", "dashboard", ""),
    (VIEW_ALL, "All Files", "files", "muted"),
    (VIEW_MATCHING, "Matching Files", "match", "muted"),
    (VIEW_PROBLEMS, "Problems", "problems", "problem"),
    (VIEW_REPORTS, "Reports", "reports", ""),
]


class GuitarApp:
    def __init__(self, root: tk.Tk, state: Optional[AppState] = None, use_settings: bool = True) -> None:
        self.root = root
        self.use_settings = use_settings
        self.state = state or AppState()
        settings = load_settings() if use_settings else {}
        if state is None:
            if settings.get("theme") in THEMES:
                self.state.theme = settings["theme"]
            self.state.src_path = settings.get("src", "") or ""
            self.state.dst_path = settings.get("dst", "") or ""

        root.title(f"{APP_NAME} \u2014 {APP_SUBTITLE}")
        root.geometry("1380x880")
        root.minsize(1060, 680)
        try:
            self._icon = icons.make_app_icon(root)
            root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        self.fonts = Fonts(root)
        self.tm = ThemeManager(root, self.fonts, THEMES[self.state.theme])
        root.configure(bg=self.tm.theme.bg)
        self.provider = DetailsProvider()

        self._scanning = False
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._cancel = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._validate_after: Optional[str] = None
        self._last_export_dir: Optional[str] = None
        self._src_override: Optional[tuple[str, str]] = None

        self._build()
        self._bind_keys()
        self.scan_card.src.set_path(self.state.src_path)
        self.scan_card.dst.set_path(self.state.dst_path)
        self._validate()
        self.toggle.set_mode(self.state.theme, animate=False)
        self.theme_label.configure(text=self.tm.theme.label)
        self.show_view(VIEW_DASHBOARD)
        root.protocol("WM_DELETE_WINDOW", self.close)

    # ================================================================== build
    def _build(self) -> None:
        tm, root = self.tm, self.root
        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)

        # ---- header ------------------------------------------------------
        header = TFrame(root, tm, bg="sidebar", height=HEADER_HEIGHT)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)
        self.logo = tk.Canvas(header, width=44, height=44, highlightthickness=0, bd=0)
        self.logo.pack(side="left", padx=(22, 12))
        tm.register(self.logo, self._draw_logo)
        titles = TFrame(header, tm, bg="sidebar")
        titles.pack(side="left")
        TLabel(titles, tm, APP_NAME, font="title", bg="sidebar").pack(anchor="w")
        TLabel(titles, tm, APP_SUBTITLE, font="small", fg="text_muted", bg="sidebar").pack(anchor="w")
        right = TFrame(header, tm, bg="sidebar")
        right.pack(side="right", padx=22)
        self.info_btn = PillButton(right, tm, "", self.about, variant="ghost", icon="info", height=36,
                                   min_width=36, radius=18, surface="sidebar", icon_size=18, padx=0)
        self.info_btn.pack(side="right", padx=(10, 0))
        self.toggle = ThemeToggle(right, tm, self.state.theme, self.set_theme, surface="sidebar")
        self.toggle.pack(side="right")
        self.theme_label = TLabel(right, tm, "", font="small", fg="text_muted", bg="sidebar")
        self.theme_label.pack(side="right", padx=(0, 10))

        # ---- body --------------------------------------------------------
        body = tk.Frame(root, bd=0, highlightthickness=0)
        tm.register(body, lambda th: body.configure(bg=th.bg))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # sidebar
        side = TFrame(body, tm, bg="sidebar", width=SIDEBAR_WIDTH)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.pack_propagate(False)
        TFrame(side, tm, bg="border", width=1).pack(side="right", fill="y")
        nav_box = TFrame(side, tm, bg="sidebar")
        nav_box.pack(fill="both", expand=True, pady=(18, 0))
        TLabel(nav_box, tm, "WORKSPACE", font="caption", fg="text_faint", bg="sidebar").pack(anchor="w", padx=24, pady=(0, 6))
        self.nav: dict[str, NavItem] = {}
        for key, label, icon, kind in NAV:
            item = NavItem(nav_box, tm, label, icon, lambda k=key: self.show_view(k), badge_kind=kind)
            item.pack(fill="x", pady=1)
            self.nav[key] = item
        foot = TFrame(side, tm, bg="sidebar")
        foot.pack(side="bottom", fill="x", padx=20, pady=18)
        TLabel(foot, tm, "Read-only. Compares with Git HEAD; nothing is modified, staged or committed.",
               font="caption", fg="text_faint", bg="sidebar", justify="left", wraplength=190).pack(anchor="w")

        # content
        content = TFrame(body, tm, bg="bg")
        content.grid(row=0, column=1, sticky="nsew", padx=(24, 24), pady=(20, 20))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(2, weight=1)

        self.scan_card = ScanCard(content, tm, {
            "src_changed": self._on_src_changed, "dst_changed": self._on_dst_changed,
            "browse_src": self.browse_src, "browse_dst": self.browse_dst,
            "scan": self.start_scan, "edit_paths": lambda: self.show_view(VIEW_DASHBOARD),
        })
        self.scan_card.grid(row=0, column=0, sticky="ew")

        cards = TFrame(content, tm, bg="bg")
        cards.grid(row=1, column=0, sticky="ew", pady=(14, 14))
        for i in range(5):
            cards.columnconfigure(i, weight=1, uniform="cards")
        specs = [
            ("total", "Total files", "primary", lambda: self.show_view(VIEW_ALL)),
            ("match", "Matched", "success", lambda: self.show_view(VIEW_MATCHING)),
            ("mismatch", "Mismatched", "error", lambda: self.show_view(VIEW_PROBLEMS)),
            ("missing_or_uncommitted", "Missing / Uncommitted", "warning", lambda: self.show_view(VIEW_PROBLEMS)),
            ("error", "Errors", "error", lambda: self.show_view(VIEW_PROBLEMS)),
        ]
        self.cards: dict[str, SummaryCard] = {}
        for i, (key, label, token, cb) in enumerate(specs):
            c = SummaryCard(cards, tm, label, token, cb)
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0 if i == 4 else 6))
            self.cards[key] = c

        stack = TFrame(content, tm, bg="bg")
        stack.grid(row=2, column=0, sticky="nsew")
        stack.rowconfigure(0, weight=1)
        stack.columnconfigure(0, weight=1)
        self.results = ResultsPanel(stack, tm, self.state, {
            "select": self.on_select, "sort": self.on_sort, "search": self.on_search,
        })
        self.results.grid(row=0, column=0, sticky="nsew")
        self.reports = ReportsPage(stack, tm, {"export": self.export})
        self.reports.grid(row=0, column=0, sticky="nsew")
        self.inspector = self.results.inspector

    def _draw_logo(self, th) -> None:
        self.logo.configure(bg=th.sidebar)
        self.logo.delete("all")
        icons.draw_logo(self.logo, 22, 22, 40, th.primary, "#FFFFFF")

    def _bind_keys(self) -> None:
        r = self.root
        for seq in ("<F5>", "<Control-r>", "<Control-R>"):
            r.bind(seq, lambda e: self.start_scan())
        for seq in ("<Control-f>", "<Control-F>"):
            r.bind(seq, lambda e: self.focus_search())
        for seq in ("<Control-t>", "<Control-T>"):
            r.bind(seq, lambda e: self.toggle_theme())
        r.bind("<Escape>", self._on_escape)

    def _on_escape(self, _e) -> None:
        if self.state.search:
            self.results.search_var.set("")

    # ============================================================== navigation
    def show_view(self, view: str) -> None:
        self.state.set_view(view)
        if view != VIEW_REPORTS:
            self._last_result_view = view
        for key, item in self.nav.items():
            item.set_active(key == view)
        self.scan_card.set_compact(view != VIEW_DASHBOARD, self.state.src_path, self.state.dst_path)
        if view == VIEW_REPORTS:
            self.results.grid_remove()
            self.reports.grid()
            self.reports.show_scan(self.state.scan, self.state.counts())
            self._update_report_buttons()
        else:
            self.reports.grid_remove()
            self.results.grid()
            self.results.refresh()
            self.update_inspector()

    def focus_search(self) -> None:
        if self.state.view == VIEW_REPORTS:
            self.show_view(VIEW_ALL)
        self.results.focus_search()

    def about(self) -> None:
        show_about(self.root, self.tm)

    # ================================================================== theme
    def set_theme(self, name: str) -> None:
        """Switch theme in place. Paths, results, filters and selection are untouched."""
        if name == self.state.theme:
            return
        self.state.set_theme(name)
        self.tm.apply(THEMES[name])
        self.toggle.set_mode(name)
        self.theme_label.configure(text=self.tm.theme.label)

    def toggle_theme(self) -> None:
        self.set_theme("light" if self.state.theme == "dark" else "dark")

    # ===================================================== SRC / DST handling
    def _on_src_changed(self, text: str) -> None:       # touches SRC only
        self.state.set_src(text)
        self._schedule_validate()

    def _on_dst_changed(self, text: str) -> None:       # touches DST only
        self.state.set_dst(text)
        self._schedule_validate()

    def _schedule_validate(self) -> None:
        if self._validate_after:
            self.root.after_cancel(self._validate_after)
        self._validate_after = self.root.after(250, self._validate)

    def _validate(self) -> None:
        self._validate_after = None
        s, d = check_src(self.state.src_path), check_dst(self.state.dst_path)
        warn = None
        if s.level == "ok" and d.level == "ok" and self.state.same_directory():
            warn = ("warn", "SRC and DST are the same folder \u2014 its files are compared with its own HEAD.")
        self.scan_card.src.set_message(s, warn)
        self.scan_card.dst.set_message(d, warn)

    def browse_src(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="Select the original source folder (SRC)",
                                       initialdir=self._initial_dir(self.state.src_path), mustexist=True)
        if path:                                        # "" means the dialog was cancelled
            self.scan_card.src.set_path(os.path.normpath(path))

    def browse_dst(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="Select the Git repository folder (DST)",
                                       initialdir=self._initial_dir(self.state.dst_path), mustexist=True)
        if path:
            self.scan_card.dst.set_path(os.path.normpath(path))

    @staticmethod
    def _initial_dir(current: str) -> str:
        return current if current and os.path.isdir(current) else os.path.expanduser("~")

    # ====================================================== filtering / select
    def on_search(self, text: str) -> None:
        self.state.set_search(text)
        self.results.refresh()

    def on_sort(self, key: str) -> None:
        self.state.set_sort(key)
        self.results.refresh(force=True)

    def on_select(self, rel: Optional[str]) -> None:
        self.state.select(rel)
        self.update_inspector()

    def update_inspector(self) -> None:
        res = self.state.selected_result()
        scan_ = self.state.scan
        if res is None or scan_ is None:
            self.inspector.show(None)
            return
        try:
            self.inspector.show(self.provider.get(res, scan_.dst_root, scan_.head_summary))
        except Exception:
            self.inspector.viewer.set_content([
                ("Could not build the details for this file.\n", "warn"),
                (traceback.format_exc(), "err"),
            ])

    # ====================================================================== scan
    def start_scan(self) -> None:
        if self._scanning:
            return
        ok, why = self.state.can_scan()
        if not ok:
            self.scan_card.set_status(why, "error")
            if self.state.view != VIEW_DASHBOARD:
                self.show_view(VIEW_DASHBOARD)
            return
        src, dst = self.state.src_path, self.state.dst_path     # captured for this run
        self._scanning = True
        self._cancel = threading.Event()
        self._queue = queue.Queue()
        self.scan_card.set_scanning(True)
        self.scan_card.set_status("Discovering files\u2026", "info")
        self.scan_card.progress_text.configure(text="")
        self.scan_card.progress.start()
        q, cancel = self._queue, self._cancel

        def work() -> None:                                  # worker thread: NO Tk calls here
            try:
                res = scan(src, dst, progress=lambda d, t, c, p: q.put(("progress", d, t, c, p)), cancel=cancel)
                q.put(("done", res))
            except ScanCancelled:
                q.put(("cancelled",))
            except (RepoError, ScanError) as exc:
                q.put(("fail", str(exc)))
            except Exception:
                q.put(("crash", traceback.format_exc()))

        self._worker = threading.Thread(target=work, name="guitar-scan", daemon=True)
        self._worker.start()
        self.root.after(50, self._poll)

    def _poll(self) -> None:
        last_progress = None
        finished = None
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg[0] == "progress":
                    last_progress = msg
                else:
                    finished = msg
                    break
        except queue.Empty:
            pass
        if last_progress:
            _, done, total, cur, phase = last_progress
            if phase == "compare" and total:
                self.scan_card.progress.stop(done / total)
                self.scan_card.set_status(f"Comparing\u2026  {cur}", "info")
                self.scan_card.progress_text.configure(text=f"{done:,} / {total:,}")
            else:
                self.scan_card.set_status("Discovering files\u2026", "info")
        if finished is None:
            if self._worker and self._worker.is_alive() or not self._queue.empty():
                self.root.after(60, self._poll)
            else:
                self._finish_scan(("crash", "The scan worker stopped unexpectedly."))
            return
        self._finish_scan(finished)

    def _finish_scan(self, msg: tuple) -> None:
        self._scanning = False
        card = self.scan_card
        card.set_scanning(False)
        card.progress.stop(0.0)
        card.progress_text.configure(text="")
        kind = msg[0]
        if kind == "done":
            res = msg[1]
            self.provider.reset()
            self.state.set_scan(res)
            c = res.counts()
            card.progress.stop(1.0)
            level = "ok" if c["problems"] == 0 else "warn"
            txt = (f"Scan complete \u2014 {c['total']:,} files in {res.duration:.1f}s \u00b7 "
                   + ("everything matches Git HEAD." if c["problems"] == 0 else f"{c['problems']:,} need attention."))
            if not res.head_sha:
                txt, level = "Repository has no commits yet \u2014 every file is reported as Not committed.", "warn"
            card.set_status(txt, level)
            self.refresh_all()
        elif kind == "fail":
            card.set_status(msg[1], "error")
            self._validate()
        elif kind == "cancelled":
            card.set_status("Scan cancelled.", "warn")
        else:
            card.set_status("The scan failed unexpectedly. See details.", "error")
            messagebox.showerror(APP_NAME, "The scan failed unexpectedly:\n\n" + msg[1][-1800:], parent=self.root)

    def refresh_all(self) -> None:
        c = self.state.counts()
        scan_ = self.state.scan
        has = scan_ is not None
        dur = f"{scan_.duration:.1f}s" if has else ""
        pct = f"{c['match'] * 100 // c['total']}% of files" if has and c["total"] else ""
        self.cards["total"].set(c["total"], f"scanned in {dur}" if has else "")
        self.cards["match"].set(c["match"], pct)
        self.cards["mismatch"].set(c["mismatch"], "differ from HEAD" if has else "")
        self.cards["missing_or_uncommitted"].set(
            c["missing_or_uncommitted"], f"{c['missing']:,} missing \u00b7 {c['not_committed']:,} new" if has else "")
        self.cards["error"].set(c["error"], "could not be inspected" if has else "")
        self.nav[VIEW_ALL].set_count(c["total"] if has else None)
        self.nav[VIEW_MATCHING].set_count(c["match"] if has else None)
        self.nav[VIEW_PROBLEMS].set_count(c["problems"] if has else None)
        if self.state.view == VIEW_REPORTS:
            self.reports.show_scan(scan_, c)
            self._update_report_buttons()
        else:
            self.results.refresh(force=True)
            self.update_inspector()

    # ==================================================================== export
    def _update_report_buttons(self) -> None:
        on = self.state.scan is not None
        self.reports.csv_btn.set_enabled(on)
        self.reports.txt_btn.set_enabled(on)
        if not on:
            self.reports.set_message("Run a scan first to enable exports.", "info")

    def export(self, fmt: str) -> None:
        st = self.state
        rp = self.reports
        if st.scan is None:
            rp.set_message("Run a scan first.", "warn")
            return
        if rp.scope == "problems":
            rows, scope = [r for r in st.scan.results if r.status.is_problem], "Problems only"
        elif rp.scope == "view":
            rows, scope = self._view_rows_for_export(), "Current view"
        else:
            rows, scope = list(st.scan.results), "All files"
        if not rows:
            rp.set_message(f"Nothing to export for \u201c{scope}\u201d.", "warn")
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        ext = ".csv" if fmt == "csv" else ".txt"
        path = filedialog.asksaveasfilename(
            parent=self.root, title=f"Save {fmt.upper()} report", defaultextension=ext,
            initialfile=f"guitar-report-{stamp}{ext}", initialdir=self._last_export_dir or os.path.expanduser("~"),
            filetypes=[("CSV file", "*.csv")] if fmt == "csv" else [("Text file", "*.txt")])
        if not path:                                        # dialog cancelled
            rp.set_message("Export cancelled.", "info")
            return
        try:
            n = export_csv(rows, path) if fmt == "csv" else export_txt(st.scan, rows, path, scope)
        except ReportError as exc:
            rp.set_message(str(exc), "error")
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            return
        except Exception as exc:
            msg = f"Unexpected export error: {type(exc).__name__}: {exc}"
            rp.set_message(msg, "error")
            messagebox.showerror(APP_NAME, msg, parent=self.root)
            return
        self._last_export_dir = os.path.dirname(path)
        rp.set_message(f"Saved {n:,} rows to {path}", "ok")

    def _view_rows_for_export(self):
        """Rows of the last results view (the Reports page itself has no table)."""
        saved = self.state.view
        self.state.view = getattr(self, "_last_result_view", VIEW_ALL)
        try:
            return self.state.visible_results()
        finally:
            self.state.view = saved

    # ====================================================================== misc
    def close(self) -> None:
        self._cancel.set()
        if self.use_settings:
            save_settings({"theme": self.state.theme, "src": self.state.src_path, "dst": self.state.dst_path})
        self.provider.reset()
        self.root.destroy()


def main() -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # crisp rendering on HiDPI displays
        except Exception:
            pass
    root = tk.Tk()
    GuitarApp(root)
    root.mainloop()
    return 0
