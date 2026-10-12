"""Plain data models shared by the engine, the GUI and the report exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Status(str, Enum):
    """Comparison outcome of one file relative to Git HEAD."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_COMMITTED = "NOT COMMITTED"
    MISSING = "MISSING FROM SOURCE"
    ERROR = "ERROR"

    @property
    def label(self) -> str:
        return {
            Status.MATCH: "Match",
            Status.MISMATCH: "Mismatch",
            Status.NOT_COMMITTED: "Not committed",
            Status.MISSING: "Missing from SRC",
            Status.ERROR: "Error",
        }[self]

    @property
    def glyph(self) -> str:
        return {
            Status.MATCH: "\u25cf",
            Status.MISMATCH: "\u25cf",
            Status.NOT_COMMITTED: "\u25cf",
            Status.MISSING: "\u25cf",
            Status.ERROR: "\u25cf",
        }[self]

    @property
    def severity(self) -> int:
        """Sort weight: lower = more urgent."""
        return {
            Status.ERROR: 0,
            Status.MISMATCH: 1,
            Status.MISSING: 2,
            Status.NOT_COMMITTED: 3,
            Status.MATCH: 4,
        }[self]

    @property
    def is_problem(self) -> bool:
        return self is not Status.MATCH


@dataclass
class FileResult:
    """The outcome of comparing one relative path."""

    rel_path: str                       # POSIX-style path relative to both roots
    status: Status
    src_path: str                       # absolute SRC path (display form)
    dst_path: str                       # absolute DST path of the repo-side file
    message: str = ""                   # one-line finding
    src_size: Optional[int] = None
    head_size: Optional[int] = None
    src_sha256: Optional[str] = None
    head_sha256: Optional[str] = None
    src_mtime: Optional[float] = None
    is_binary: bool = False
    first_diff_line: Optional[int] = None   # 1-based, text files
    first_diff_byte: Optional[int] = None   # 0-based offset
    head_byte: Optional[int] = None         # byte value in HEAD at that offset
    src_byte: Optional[int] = None          # byte value in SRC at that offset
    error_detail: str = ""                  # full exception text for ERROR rows

    @property
    def name(self) -> str:
        return self.rel_path.rsplit("/", 1)[-1]

    @property
    def directory(self) -> str:
        return self.rel_path.rsplit("/", 1)[0] if "/" in self.rel_path else ""


@dataclass
class ScanResult:
    """Everything produced by one scan run."""

    src_root: str
    dst_root: str
    head_sha: Optional[str]
    head_summary: str
    results: list[FileResult] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)   # paths skipped by .gitignore
    warnings: list[str] = field(default_factory=list)
    duration: float = 0.0
    finished_at: str = ""

    def counts(self) -> dict[str, int]:
        c = {
            "total": len(self.results),
            "match": 0,
            "mismatch": 0,
            "missing_or_uncommitted": 0,
            "not_committed": 0,
            "missing": 0,
            "error": 0,
            "ignored": len(self.ignored),
        }
        for r in self.results:
            if r.status is Status.MATCH:
                c["match"] += 1
            elif r.status is Status.MISMATCH:
                c["mismatch"] += 1
            elif r.status is Status.NOT_COMMITTED:
                c["not_committed"] += 1
                c["missing_or_uncommitted"] += 1
            elif r.status is Status.MISSING:
                c["missing"] += 1
                c["missing_or_uncommitted"] += 1
            else:
                c["error"] += 1
        c["problems"] = c["total"] - c["match"]
        return c
