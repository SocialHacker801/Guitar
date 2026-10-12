"""Results table, search/filter header, empty states and the inspector split view."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ..models import FileResult, Status
from ..paths import human_size
from ..state import (VIEW_ALL, VIEW_DASHBOARD, VIEW_MATCHING, VIEW_PROBLEMS, AppState)
from ..theme import Theme, status_token
from . import icons
from .inspector import InspectorPanel
from .widgets import Field, RoundedCard, TFrame, TLabel, ThemeManager

VIEW_TEXT = {
    VIEW_DASHBOARD: ("Scan results", "Every scanned path \u2014 problems listed first"),
    VIEW_ALL: ("All files", "Every scanned path compared with Git HEAD"),
    VIEW_MATCHING: ("Matching files", "Content identical to the committed Git HEAD snapshot"),
    VIEW_PROBLEMS: ("Problems", "Mismatches, uncommitted files, files missing from SRC, and errors"),
}

COLUMN_SORT = {"#0": "status", "name": "name", "folder": "path", "size": "size", "modified": "modified"}
BATCH = 400


def _fmt_mtime(ts: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "\u2014"


def _dot_image(root, color: str, size: int = 12) -> tk.PhotoImage:
    img = tk.PhotoImage(master=root, width=size, height=size)
    r = size / 2 - 0.5
    rows = []
    for y in range(size):
        rows.append("{" + " ".join(color if (x - r) ** 2 + (y - r) ** 2 <= (r + .3) ** 2 else "#000000"
                                     for x in range(size)) + "}")
    img.put(" ".join(rows))
    for y in range(size):
        for x in range(size):
            if (x - r) ** 2 + (y - r) ** 2 > (r + .3) ** 2:
                img.tk.call(img, "transparency", "set", x, y, True)
    return img


class EmptyState(tk.Frame):
    """Centered icon + message shown over the table when there are no rows."""

    def __init__(self, master, tm: ThemeManager) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self.tm = tm
        self.icon_name = "files"
        self.cv = tk.Canvas(self, width=64, height=64, highlightthickness=0, bd=0)
        self.cv.pack()
        self.title = tk.Label(self, font=tm.fonts.heading, bd=0)
        self.title.pack(pady=(8, 2))
        self.sub = tk.Label(self, font=tm.fonts.body, bd=0, wraplength=360, justify="center")
        self.sub.pack()
        tm.register(self)

    def show(self, icon: str, title: str, sub: str) -> None:
        self.icon_name = icon
        self.title.configure(text=title)
        self.sub.configure(text=sub)
        self._draw()
        self.place(relx=0.5, rely=0.46, anchor="center")
        self.lift()

    def hide(self) -> None:
        self.place_forget()

    def _draw(self) -> None:
        th = self.tm.theme
        self.cv.delete("all")
        icons.draw_icon(self.cv, self.icon_name, 32, 32, 40, th.accent, 1.8)

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th.panel)
        self.cv.configure(bg=th.panel)
        self.title.configure(bg=th.panel, fg=th.text)
        self.sub.configure(bg=th.panel, fg=th.text_muted)
        self._draw()


class ResultsTable(tk.Frame):
    """ttk.Treeview-based table with batched population, hover, sorting and selection."""

    def __init__(self, master, tm: ThemeManager, state: AppState,
                 on_select: Callable[[Optional[str]], None], on_sort: Callable[[str], None]) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self.tm, self.state = tm, state
        self.on_select, self.on_sort = on_select, on_sort
        self._gen = 0
        self._last_key: Optional[tuple] = None
        self._rel_by_iid: dict[str, str] = {}
        self._iid_by_rel: dict[str, str] = {}
        self._restoring = False
        self._hover: Optional[str] = None
        self._dots: dict[str, tk.PhotoImage] = {}
        self._sel_after: Optional[str] = None

        cols = ("name", "folder", "size", "modified")
        self.tree = ttk.Treeview(self, columns=cols, style="Guitar.Treeview", selectmode="browse",
                                 show="tree headings")
        self.vbar = ttk.Scrollbar(self, orient="vertical", style="Guitar.Vertical.TScrollbar",
                                  command=self.tree.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", style="Guitar.Horizontal.TScrollbar",
                                  command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vbar.set, xscrollcommand=self._on_xscroll)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.tree.column("#0", width=176, minwidth=150, stretch=False)
        self.tree.column("name", width=150, minwidth=110, stretch=False)
        self.tree.column("folder", width=90, minwidth=80, stretch=True)
        self.tree.column("size", width=72, minwidth=68, stretch=False, anchor="e")
        self.tree.column("modified", width=138, minwidth=130, stretch=False)
        self._heading_text = {"#0": "Status", "name": "File", "folder": "Folder",
                              "size": "Size", "modified": "Modified"}
        self._update_headings()

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", lambda e: self._set_hover(None))
        self.tree.bind("<Control-c>", self._copy_path)
        self.empty = EmptyState(self, tm)
        tm.register(self)

    # -- theme --------------------------------------------------------------
    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th.panel)
        self.tree.tag_configure("hover", background=th.hover_bg)
        self._dots = {s.value: _dot_image(self, th[status_token(s.value)]) for s in Status}
        for iid, rel in self._rel_by_iid.items():
            res = self.state.result_by_path(rel)
            if res is not None and self.tree.exists(iid):
                self.tree.item(iid, image=self._dots[res.status.value])

    def _update_headings(self) -> None:
        st = self.state
        eff = st.sort_key or ("status" if st.view == VIEW_DASHBOARD else "path")
        for col, text in self._heading_text.items():
            arrow = ""
            if COLUMN_SORT.get(col) == eff:
                arrow = "  \u25bc" if st.sort_reverse else "  \u25b2"
            self.tree.heading(col, text=text + arrow, anchor="e" if col == "size" else "w",
                              command=(lambda c=col: self._sort(c)) if col in COLUMN_SORT else "")

    def _on_xscroll(self, lo: str, hi: str) -> None:
        """Show the horizontal scrollbar only when the columns overflow."""
        self.hbar.set(lo, hi)
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.hbar.grid_remove()
        else:
            self.hbar.grid(row=1, column=0, sticky="ew")

    def _sort(self, col: str) -> None:
        self.on_sort(COLUMN_SORT[col])

    # -- population -----------------------------------------------------------
    def populate(self, rows: list[FileResult], force: bool = False) -> None:
        st = self.state
        key = (id(st.scan), st.view, st.search, st.sort_key, st.sort_reverse, len(rows))
        self._update_headings()
        if key == self._last_key and not force:
            self._restore_selection()
            return
        self._last_key = key
        self._gen += 1
        gen = self._gen
        self._restoring = True
        self.tree.delete(*self.tree.get_children())
        self._rel_by_iid.clear()
        self._iid_by_rel.clear()
        self._hover = None
        self._insert_batch(rows, 0, gen)

    def _insert_batch(self, rows: list[FileResult], start: int, gen: int) -> None:
        if gen != self._gen:
            return                                  # superseded by a newer populate()
        end = min(len(rows), start + BATCH)
        tree = self.tree
        for i in range(start, end):
            r = rows[i]
            iid = f"r{i}"
            size = r.src_size if r.src_size is not None else r.head_size
            tree.insert("", "end", iid=iid, text="  " + r.status.label, image=self._dots[r.status.value],
                        values=(r.name, r.directory or "(root)", human_size(size), _fmt_mtime(r.src_mtime)))
            self._rel_by_iid[iid] = r.rel_path
            self._iid_by_rel[r.rel_path] = iid
        self._restore_selection()
        if end < len(rows):
            self.after(1, self._insert_batch, rows, end, gen)
        else:
            self._restoring = False

    def _restore_selection(self) -> None:
        rel = self.state.selected
        iid = self._iid_by_rel.get(rel) if rel else None
        if iid and self.tree.exists(iid):
            if self.tree.selection() != (iid,):
                was = self._restoring
                self._restoring = True
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self._restoring = was
        elif self.tree.selection() and not self._iid_by_rel.get(rel or ""):
            was = self._restoring
            self._restoring = True
            self.tree.selection_remove(self.tree.selection())
            self._restoring = was

    # -- events ------------------------------------------------------------------
    def _on_tree_select(self, _e) -> None:
        if self._restoring:
            return
        sel = self.tree.selection()
        if not sel:
            return
        self._set_hover(None)
        rel = self._rel_by_iid.get(sel[0])
        if self._sel_after:
            self.after_cancel(self._sel_after)
        self._sel_after = self.after(40, lambda: self.on_select(rel))

    def _on_motion(self, e) -> None:
        iid = self.tree.identify_row(e.y) or None
        self._set_hover(iid)

    def _set_hover(self, iid: Optional[str]) -> None:
        if iid == self._hover:
            return
        if self._hover and self.tree.exists(self._hover):
            self.tree.item(self._hover, tags=())
        self._hover = None
        if iid and self.tree.exists(iid) and iid not in self.tree.selection():
            self.tree.item(iid, tags=("hover",))
            self._hover = iid

    def _copy_path(self, _e=None) -> None:
        sel = self.tree.selection()
        if sel:
            self.clipboard_clear()
            self.clipboard_append(self._rel_by_iid.get(sel[0], ""))


class ResultsPanel(tk.Frame):
    """Header (title, count, search) + [table | inspector] split."""

    def __init__(self, master, tm: ThemeManager, state: AppState, callbacks: dict) -> None:
        super().__init__(master, bd=0, highlightthickness=0)
        self.tm, self.state, self.cb = tm, state, callbacks
        self.search_var = tk.StringVar()
        self._search_after: Optional[str] = None
        self._suppress_search = False

        head = TFrame(self, tm, bg="bg")
        head.pack(fill="x", pady=(0, 10))
        left = TFrame(head, tm, bg="bg")
        left.pack(side="left", fill="x", expand=True)
        self.title = TLabel(left, tm, "", font="heading", bg="bg")
        self.title.pack(anchor="w")
        self.subtitle = TLabel(left, tm, "", font="small", fg="text_muted", bg="bg")
        self.subtitle.pack(anchor="w")
        right = TFrame(head, tm, bg="bg")
        right.pack(side="right")
        self.count = TLabel(right, tm, "", font="small", fg="text_muted", bg="bg")
        self.count.pack(side="left", padx=(0, 14))
        self.search = Field(right, tm, self.search_var, placeholder="Search by filename or path\u2026",
                            icon="search", clearable=True, surface="bg", height=40)
        self.search.configure(width=300)
        self.search.pack(side="left")
        self.search_var.trace_add("write", lambda *a: self._on_search_changed())

        self.pane = tk.PanedWindow(self, orient="horizontal", sashwidth=10, sashrelief="flat",
                                   bd=0, opaqueresize=True, showhandle=False)
        self.pane.pack(fill="both", expand=True)
        self.table_card = RoundedCard(self.pane, tm, surface="bg", fill="panel", radius=14, pad=2)
        self.table = ResultsTable(self.table_card.body, tm, state, callbacks["select"], callbacks["sort"])
        self.table.pack(fill="both", expand=True, padx=2, pady=2)
        self.inspector = InspectorPanel(self.pane, tm)
        self.pane.add(self.table_card, minsize=420, stretch="always", padx=0)
        self.pane.add(self.inspector, minsize=340, width=400, stretch="never")
        tm.register(self)

    def apply_theme(self, th: Theme) -> None:
        self.configure(bg=th.bg)
        self.pane.configure(bg=th.bg)

    # -- search -------------------------------------------------------------------
    def _on_search_changed(self) -> None:
        if self._suppress_search:
            return
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(160, lambda: self.cb["search"](self.search_var.get()))

    def set_search_text(self, text: str) -> None:
        if self.search_var.get() != text:
            self._suppress_search = True
            self.search_var.set(text)
            self._suppress_search = False

    def focus_search(self) -> None:
        self.search.entry.focus_set()
        self.search.entry.select_range(0, "end")

    # -- refresh ---------------------------------------------------------------------
    def refresh(self, force: bool = False) -> None:
        st = self.state
        title, sub = VIEW_TEXT.get(st.view, ("Results", ""))
        self.title.configure(text=title)
        self.subtitle.configure(text=sub)
        rows = st.visible_results()
        total_in_view = self._total_in_view()
        if st.scan is None:
            self.count.configure(text="")
        elif st.search:
            self.count.configure(text=f"{len(rows):,} of {total_in_view:,} files")
        else:
            self.count.configure(text=f"{len(rows):,} file{'s' if len(rows) != 1 else ''}")
        self.table.populate(rows, force=force)
        self._update_empty(rows)

    def _total_in_view(self) -> int:
        st = self.state
        if st.scan is None:
            return 0
        c = st.counts()
        if st.view == VIEW_MATCHING:
            return c["match"]
        if st.view == VIEW_PROBLEMS:
            return c["problems"]
        return c["total"]

    def _update_empty(self, rows: list[FileResult]) -> None:
        st, e = self.state, self.table.empty
        if rows:
            e.hide()
        elif st.scan is None:
            e.show("scan", "No results yet", "Choose the SRC and DST folders above, then press Scan.")
        elif st.search:
            e.show("search", "No files match your search", f"Nothing in this view matches \u201c{st.search}\u201d.")
        elif st.view == VIEW_MATCHING:
            e.show("match", "No matching files", "None of the scanned files are identical to Git HEAD.")
        elif st.view == VIEW_PROBLEMS:
            e.show("match", "No problems found", "Every scanned file matches the committed Git HEAD snapshot.")
        else:
            e.show("files", "Nothing to show", "The scan did not find any files.")
