"""GUI-independent application state.

Keeping state in a plain object (no Tk) makes the critical behaviours testable:
independent SRC/DST, view filtering, selection retention and theme switching.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .models import FileResult, ScanResult, Status
from .paths import fs_path, normalize_user_path, same_directory

VIEW_DASHBOARD = "dashboard"
VIEW_ALL = "all"
VIEW_MATCHING = "matching"
VIEW_PROBLEMS = "problems"
VIEW_REPORTS = "reports"
RESULT_VIEWS = (VIEW_DASHBOARD, VIEW_ALL, VIEW_MATCHING, VIEW_PROBLEMS)

SORT_KEYS = ("status", "name", "path", "size", "modified")


@dataclass(frozen=True)
class PathCheck:
    level: str      # "empty" | "ok" | "warn" | "error"
    message: str


def check_src(path: str) -> PathCheck:
    if not path:
        return PathCheck("empty", "Choose the original source folder.")
    real = fs_path(path)
    if not os.path.exists(real):
        return PathCheck("error", "This folder does not exist.")
    if not os.path.isdir(real):
        return PathCheck("error", "This path is not a folder.")
    return PathCheck("ok", "Folder found.")


def check_dst(path: str) -> PathCheck:
    if not path:
        return PathCheck("empty", "Choose the Git repository folder.")
    real = fs_path(path)
    if not os.path.exists(real):
        return PathCheck("error", "This folder does not exist.")
    if not os.path.isdir(real):
        return PathCheck("error", "This path is not a folder.")
    if not os.path.exists(os.path.join(real, ".git")):
        return PathCheck("error", "No .git entry here \u2014 select the repository root.")
    return PathCheck("ok", "Git repository detected.")


class AppState:
    def __init__(self) -> None:
        # SRC and DST live in separate attributes with separate setters.
        self.src_path: str = ""
        self.dst_path: str = ""
        self.theme: str = "dark"
        self.view: str = VIEW_DASHBOARD
        self.search: str = ""
        self.selected: Optional[str] = None          # rel_path of the selected row
        self.scan: Optional[ScanResult] = None
        self.sort_key: Optional[str] = None
        self.sort_reverse: bool = False

    # -------------------------------------------------------- path selection
    def set_src(self, path: str) -> None:
        self.src_path = normalize_user_path(path)

    def set_dst(self, path: str) -> None:
        self.dst_path = normalize_user_path(path)

    def same_directory(self) -> bool:
        return same_directory(self.src_path, self.dst_path)

    def can_scan(self) -> tuple[bool, str]:
        s, d = check_src(self.src_path), check_dst(self.dst_path)
        if s.level != "ok":
            return False, "SRC: " + s.message
        if d.level != "ok":
            return False, "DST: " + d.message
        return True, ""

    # ------------------------------------------------------------ scan data
    def set_scan(self, scan: Optional[ScanResult]) -> None:
        self.scan = scan
        if self.selected is not None and self.result_by_path(self.selected) is None:
            self.selected = None

    def result_by_path(self, rel: str) -> Optional[FileResult]:
        if self.scan is None:
            return None
        if not hasattr(self, "_index") or self._index_scan is not self.scan:
            self._index = {r.rel_path: r for r in self.scan.results}
            self._index_scan = self.scan
        return self._index.get(rel)

    def counts(self) -> dict[str, int]:
        if self.scan is None:
            return {k: 0 for k in
                    ("total", "match", "mismatch", "missing_or_uncommitted",
                     "not_committed", "missing", "error", "ignored", "problems")}
        return self.scan.counts()

    # --------------------------------------------------------------- views
    def set_view(self, view: str) -> None:
        """Change the active view. Selection and search are preserved."""
        self.view = view

    def set_search(self, text: str) -> None:
        self.search = text.strip()

    def select(self, rel: Optional[str]) -> None:
        self.selected = rel

    def selected_result(self) -> Optional[FileResult]:
        return self.result_by_path(self.selected) if self.selected else None

    def set_sort(self, key: str) -> None:
        if self.sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_key, self.sort_reverse = key, False

    def set_theme(self, name: str) -> None:
        if name not in ("dark", "light"):
            raise ValueError(f"unknown theme {name!r}")
        self.theme = name        # nothing else is touched

    def _in_view(self, r: FileResult) -> bool:
        if self.view == VIEW_MATCHING:
            return r.status is Status.MATCH
        if self.view == VIEW_PROBLEMS:
            return r.status is not Status.MATCH
        return True

    def visible_results(self) -> list[FileResult]:
        """Filter (view + search) and sort the existing results; never rescans."""
        if self.scan is None:
            return []
        terms = self.search.casefold().split()
        rows = [
            r for r in self.scan.results
            if self._in_view(r) and all(t in r.rel_path.casefold() for t in terms)
        ]
        key = self.sort_key
        if key is None:
            key = "status" if self.view == VIEW_DASHBOARD else "path"
        rev = self.sort_reverse
        if key == "status":
            rows.sort(key=lambda r: (r.status.severity, r.rel_path.casefold()), reverse=rev)
        elif key == "name":
            rows.sort(key=lambda r: (r.name.casefold(), r.rel_path.casefold()), reverse=rev)
        elif key == "size":
            rows.sort(key=lambda r: (r.src_size if r.src_size is not None else (r.head_size or 0)), reverse=rev)
        elif key == "modified":
            rows.sort(key=lambda r: r.src_mtime or 0.0, reverse=rev)
        else:
            rows.sort(key=lambda r: r.rel_path.casefold(), reverse=rev)
        return rows
