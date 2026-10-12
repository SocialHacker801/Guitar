"""CSV and TXT report generation (atomic, read-only with respect to the repo)."""

from __future__ import annotations

import csv
import os
import tempfile
import time
from typing import Iterable, Optional

from .models import FileResult, ScanResult, Status

CSV_COLUMNS = [
    "status", "relative_path", "source_path", "destination_path", "finding",
    "src_size_bytes", "head_size_bytes", "src_sha256", "head_sha256",
    "content_type", "first_diff_line", "first_diff_byte",
    "head_byte", "src_byte", "error_detail",
]


class ReportError(Exception):
    """Raised when a report cannot be written."""


def _safe_cell(value: object) -> object:
    """Neutralise spreadsheet formula injection in text cells."""
    if isinstance(value, str) and value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


def result_row(r: FileResult) -> list[object]:
    return [
        r.status.value, r.rel_path, r.src_path, r.dst_path, r.message,
        r.src_size, r.head_size, r.src_sha256 or "", r.head_sha256 or "",
        "binary" if r.is_binary else "text",
        r.first_diff_line if r.first_diff_line is not None else "",
        r.first_diff_byte if r.first_diff_byte is not None else "",
        f"0x{r.head_byte:02X}" if r.head_byte is not None else "",
        f"0x{r.src_byte:02X}" if r.src_byte is not None else "",
        " | ".join(r.error_detail.strip().splitlines()[-2:]) if r.error_detail else "",
    ]


def _atomic_write(path: str, writer, newline: Optional[str], encoding: str) -> None:
    folder = os.path.dirname(os.path.abspath(path)) or "."
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".guitar-", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as fh:
            writer(fh)
        os.replace(tmp, path)
        tmp = None
    except OSError as exc:
        raise ReportError(f"Could not write report to {path}: {exc}") from exc
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def export_csv(results: Iterable[FileResult], path: str) -> int:
    rows = list(results)

    def write(fh) -> None:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for r in rows:
            w.writerow([_safe_cell(c) for c in result_row(r)])

    _atomic_write(path, write, newline="", encoding="utf-8-sig")
    return len(rows)


def export_txt(scan: ScanResult, results: Iterable[FileResult], path: str,
               scope: str = "All files") -> int:
    rows = list(results)
    counts = scan.counts()
    problems = [r for r in rows if r.status.is_problem]
    matches = [r for r in rows if not r.status.is_problem]

    def write(fh) -> None:
        p = lambda s="": fh.write(s + "\n")
        p("GUITAR \u2014 Git Integrity Report")
        p("=" * 60)
        p(f"Generated : {time.strftime('%Y-%m-%d %H:%M:%S')}")
        p(f"Scan time : {scan.finished_at}  ({scan.duration:.2f}s)")
        p(f"SRC       : {scan.src_root}")
        p(f"DST       : {scan.dst_root}")
        p(f"Baseline  : Git HEAD {scan.head_summary}")
        p(f"Scope     : {scope} ({len(rows)} rows)")
        p()
        p("Summary (whole scan)")
        p("-" * 60)
        p(f"  Total files            : {counts['total']}")
        p(f"  Matching               : {counts['match']}")
        p(f"  Mismatched             : {counts['mismatch']}")
        p(f"  Not committed          : {counts['not_committed']}")
        p(f"  Missing from source    : {counts['missing']}")
        p(f"  Errors                 : {counts['error']}")
        p(f"  Skipped by .gitignore  : {counts['ignored']}")
        for w in scan.warnings:
            p(f"  Note: {w}")
        p()
        if problems:
            p(f"PROBLEMS ({len(problems)})")
            p("=" * 60)
            for r in sorted(problems, key=lambda x: (x.status.severity, x.rel_path.casefold())):
                p(f"[{r.status.value}] {r.rel_path}")
                p(f"    SRC : {r.src_path}")
                p(f"    DST : {r.dst_path}")
                p(f"    {r.message}")
                p(f"    Size SRC/HEAD : {r.src_size}/{r.head_size}")
                p(f"    SHA-256 SRC   : {r.src_sha256 or '-'}")
                p(f"    SHA-256 HEAD  : {r.head_sha256 or '-'}")
                if r.status is Status.MISMATCH:
                    if r.is_binary:
                        hb = f"0x{r.head_byte:02X}" if r.head_byte is not None else "EOF"
                        sb = f"0x{r.src_byte:02X}" if r.src_byte is not None else "EOF"
                        p(f"    First differing byte : offset {r.first_diff_byte} (HEAD {hb}, SRC {sb})")
                    else:
                        p(f"    First differing line : {r.first_diff_line} (byte offset {r.first_diff_byte})")
                if r.error_detail:
                    p("    Exception:")
                    for ln in r.error_detail.rstrip().splitlines():
                        p(f"      {ln}")
                p()
        if matches:
            p(f"MATCHING FILES ({len(matches)})")
            p("=" * 60)
            for r in matches:
                p(f"[MATCH] {r.rel_path}  ({r.src_size} bytes, sha256 {(r.src_sha256 or '')[:16]}\u2026)")
            p()
        if scan.ignored:
            p(f"SKIPPED BY .gitignore ({len(scan.ignored)})")
            p("=" * 60)
            for ig in scan.ignored:
                p(f"[IGNORED] {ig}")
            p()

    _atomic_write(path, write, newline="\n", encoding="utf-8")
    return len(rows)
