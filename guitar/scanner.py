"""File scanner and comparison engine.

Compares every file below SRC with the committed snapshot in DST's Git HEAD.
SRC and DST are resolved *independently*: the SRC-side path of a result is
``join(src_root, rel)`` and the DST-side path is ``join(dst_root, rel)``; the
two roots are never derived from one another.

The scanner is strictly read-only and free of any Tk dependency so it can run
in a worker thread and be unit-tested without a display.
"""

from __future__ import annotations

import hashlib
import io
import os
import threading
import time
import traceback
from dataclasses import dataclass
from typing import BinaryIO, Callable, Optional

from .git_backend import SYMLINK_MODE, GitRepo, RepoError, Tracked
from .ignore_rules import IgnoreRules
from .models import FileResult, ScanResult, Status
from .paths import display_path, fs_path, join_rel

CHUNK = 1 << 20           # 1 MiB streaming chunk
BINARY_PROBE = 8000       # same heuristic Git uses: NUL byte in first 8000 bytes

ProgressCB = Callable[[int, int, str, str], None]   # done, total, current, phase


class ScanError(Exception):
    """Raised when a scan cannot start (bad SRC/DST)."""


class ScanCancelled(Exception):
    """Raised when the cancel event is set during a scan."""


# --------------------------------------------------------------------------
# Low-level comparison helpers
# --------------------------------------------------------------------------
def first_diff_index(a: bytes, b: bytes) -> int:
    """Index of the first differing byte; ``min(len)`` if one is a prefix of the
    other; ``len(a)`` (== ``len(b)``) when identical."""
    n = min(len(a), len(b))
    if a[:n] == b[:n]:
        return n
    lo, hi = 0, n               # a[lo:hi] != b[lo:hi]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if a[lo:mid] == b[lo:mid]:
            lo = mid
        else:
            hi = mid
    return lo


def looks_binary(sample: bytes) -> bool:
    return b"\x00" in sample[:BINARY_PROBE]


def _read_exact(stream: BinaryIO, n: int) -> bytes:
    parts: list[bytes] = []
    got = 0
    while got < n:
        chunk = stream.read(n - got)
        if not chunk:
            break
        parts.append(chunk)
        got += len(chunk)
    return parts[0] if len(parts) == 1 else b"".join(parts)


@dataclass
class StreamCompare:
    equal: bool
    head_size: int
    src_size: int
    head_sha256: str
    src_sha256: str
    is_binary: bool
    first_diff_byte: Optional[int] = None
    head_byte: Optional[int] = None
    src_byte: Optional[int] = None
    first_diff_line: Optional[int] = None


def compare_streams(head: BinaryIO, src: BinaryIO) -> StreamCompare:
    """Stream both inputs in lock-step; hash both fully, locate first difference."""
    hs, ss = hashlib.sha256(), hashlib.sha256()
    hsize = ssize = pos = newlines = 0
    first: Optional[int] = None
    head_b = src_b = None
    binary = False
    probe_done = False
    while True:
        hc = _read_exact(head, CHUNK)
        sc = _read_exact(src, CHUNK)
        if not hc and not sc:
            break
        if not probe_done:
            binary = looks_binary(hc) or looks_binary(sc)
            probe_done = True
        hs.update(hc)
        ss.update(sc)
        hsize += len(hc)
        ssize += len(sc)
        if first is None:
            idx = first_diff_index(hc, sc)
            if idx < len(hc) or idx < len(sc):          # a real difference
                first = pos + idx
                head_b = hc[idx] if idx < len(hc) else None
                src_b = sc[idx] if idx < len(sc) else None
                newlines += hc[:idx].count(b"\n")
            else:
                newlines += hc.count(b"\n")
        pos += max(len(hc), len(sc))
    equal = first is None
    return StreamCompare(
        equal=equal,
        head_size=hsize,
        src_size=ssize,
        head_sha256=hs.hexdigest(),
        src_sha256=ss.hexdigest(),
        is_binary=binary,
        first_diff_byte=first,
        head_byte=head_b,
        src_byte=src_b,
        first_diff_line=None if (equal or binary) else newlines + 1,
    )


def sha256_stream(stream: BinaryIO) -> tuple[str, int, bool]:
    h = hashlib.sha256()
    size = 0
    binary = False
    first = True
    while True:
        chunk = _read_exact(stream, CHUNK)
        if not chunk:
            break
        if first:
            binary = looks_binary(chunk)
            first = False
        h.update(chunk)
        size += len(chunk)
    return h.hexdigest(), size, binary


# --------------------------------------------------------------------------
# Scanner
# --------------------------------------------------------------------------
def _validate_src(src: str) -> str:
    if not src:
        raise ScanError("No source (SRC) directory selected.")
    real = fs_path(src)
    if not os.path.exists(real):
        raise ScanError(f"SRC path does not exist: {src}")
    if not os.path.isdir(real):
        raise ScanError(f"SRC path is not a directory: {src}")
    return real


def _tracked_dir_prefixes(tracked: dict[str, Tracked]) -> set[str]:
    prefixes: set[str] = set()
    for path in tracked:
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            prefixes.add("/".join(parts[:i]))
    return prefixes




def scan(
    src: str,
    dst: str,
    progress: Optional[ProgressCB] = None,
    cancel: Optional[threading.Event] = None,
) -> ScanResult:
    """Compare *src* with the HEAD snapshot of the repository at *dst*."""
    started = time.perf_counter()
    src_real = _validate_src(src)
    src_abs = display_path(os.path.abspath(src))
    dst_abs = display_path(os.path.abspath(dst)) if dst else dst

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise ScanCancelled()

    def report(done: int, total: int, current: str, phase: str) -> None:
        if progress is not None:
            progress(done, total, current, phase)

    with GitRepo.open(dst) as repo:            # raises RepoError (surfaced to GUI)
        tracked = repo.tracked_files()
        text, origin = repo.read_root_gitignore()
        rules = IgnoreRules.from_text(text, origin)
        result = ScanResult(
            src_root=src_abs,
            dst_root=dst_abs,
            head_sha=repo.head_sha,
            head_summary=repo.head_summary,
        )
        if not repo.has_commits:
            result.warnings.append(
                "The repository has no commits yet: every SRC file is reported as "
                "NOT COMMITTED."
            )
        if rules.active:
            result.warnings.append(
                f"Ignore rules loaded from {rules.origin}. Only the root .gitignore is "
                "supported (no nested, global or .git/info/exclude rules)."
            )

        # ---- phase 1: discover SRC files -------------------------------------
        report(0, 0, "", "discover")
        dir_prefixes = _tracked_dir_prefixes(tracked)
        files: list[tuple[str, str]] = []              # (rel, real path)
        unreadable_dirs: list[str] = []
        walk_errors: list[FileResult] = []

        def on_walk_error(err: OSError) -> None:
            fn = getattr(err, "filename", None) or src_real
            rel = _rel_from(src_real, str(fn))
            unreadable_dirs.append(rel)
            walk_errors.append(
                FileResult(
                    rel_path=rel or ".",
                    status=Status.ERROR,
                    src_path=display_path(str(fn)),
                    dst_path=join_rel(dst_abs, rel),
                    message=f"Directory could not be read: {type(err).__name__}: {err}",
                    error_detail="".join(traceback.format_exception_only(type(err), err)),
                )
            )

        counter = 0
        for dirpath, dirnames, filenames in os.walk(src_real, onerror=on_walk_error):
            check_cancel()
            rel_dir = _rel_from(src_real, dirpath)
            keep: list[str] = []
            for d in sorted(dirnames):
                if d == ".git":
                    continue
                rel_d = f"{rel_dir}/{d}" if rel_dir else d
                if rules.is_ignored(rel_d, is_dir=True) and rel_d not in dir_prefixes:
                    result.ignored.append(rel_d + "/")
                    continue
                keep.append(d)
            dirnames[:] = keep
            for f in sorted(filenames):
                if f == ".git":
                    continue
                rel = f"{rel_dir}/{f}" if rel_dir else f
                if rel not in tracked and rules.is_ignored(rel):
                    result.ignored.append(rel)
                    continue
                files.append((rel, os.path.join(dirpath, f)))
                counter += 1
                if counter % 200 == 0:
                    report(0, 0, rel, "discover")

        seen = {rel for rel, _ in files}
        missing = [p for p in sorted(tracked) if p not in seen]
        total = len(files) + len(missing)
        done = 0
        last = 0.0

        def tick(rel: str) -> None:
            nonlocal done, last
            done += 1
            now = time.perf_counter()
            if now - last >= 0.05 or done == total:
                last = now
                report(done, total, rel, "compare")

        # ---- phase 2: compare files present in SRC --------------------------
        result.results.extend(walk_errors)
        for rel, real in files:
            check_cancel()
            result.results.append(
                _compare_file(repo, rel, real, tracked.get(rel), src_abs, dst_abs)
            )
            tick(rel)

        # ---- phase 3: tracked files that are absent from SRC ----------------
        for rel in missing:
            check_cancel()
            result.results.append(
                _missing_file(repo, rel, tracked[rel], src_abs, dst_abs, src_real, unreadable_dirs)
            )
            tick(rel)

    result.results.sort(key=lambda r: r.rel_path.casefold())
    result.duration = time.perf_counter() - started
    result.finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
    return result


def _rel_from(root_real: str, path: str) -> str:
    """POSIX-style path of *path* relative to *root_real* (both from os.walk)."""
    rel = path[len(root_real):] if path.startswith(root_real) else path
    return rel.strip("\\/").replace("\\", "/") if os.sep == "\\" else rel.strip("/")


def _compare_file(
    repo: GitRepo,
    rel: str,
    real: str,
    entry: Optional[Tracked],
    src_abs: str,
    dst_abs: str,
) -> FileResult:
    src_path = join_rel(src_abs, rel)
    dst_path = join_rel(dst_abs, rel)
    res = FileResult(rel_path=rel, status=Status.ERROR, src_path=src_path, dst_path=dst_path)
    try:
        st = os.stat(real)
        res.src_size = st.st_size
        res.src_mtime = st.st_mtime

        if entry is None:
            with open(real, "rb") as fh:
                sha, size, binary = sha256_stream(fh)
            res.status = Status.NOT_COMMITTED
            res.src_sha256, res.src_size, res.is_binary = sha, size, binary
            res.message = (
                "File exists in SRC but has no commit in HEAD."
                if repo.has_commits
                else "File exists in SRC but the repository has no commits."
            )
            return res

        head_stream = repo.open_stream(rel)
        try:
            if entry.mode == SYMLINK_MODE and os.path.islink(real):
                target = os.readlink(real).replace("\\", "/")
                src_stream: BinaryIO = io.BytesIO(target.encode("utf-8", "surrogateescape"))
                cmp = compare_streams(head_stream, src_stream)
            else:
                with open(real, "rb") as fh:
                    cmp = compare_streams(head_stream, fh)
        finally:
            close = getattr(head_stream, "close", None)
            if close:
                close()

        res.head_size, res.src_size = cmp.head_size, cmp.src_size
        res.head_sha256, res.src_sha256 = cmp.head_sha256, cmp.src_sha256
        res.is_binary = cmp.is_binary
        if cmp.equal:
            res.status = Status.MATCH
            res.message = "Content matches the committed Git HEAD snapshot exactly."
        else:
            res.status = Status.MISMATCH
            res.first_diff_byte = cmp.first_diff_byte
            res.head_byte, res.src_byte = cmp.head_byte, cmp.src_byte
            res.first_diff_line = cmp.first_diff_line
            if cmp.is_binary:
                res.message = f"Binary content differs at byte offset {cmp.first_diff_byte}."
            else:
                res.message = f"Content differs from HEAD; first difference on line {cmp.first_diff_line}."
        return res
    except Exception as exc:                      # keep scanning other files
        res.status = Status.ERROR
        res.message = f"Could not inspect file: {type(exc).__name__}: {exc}"
        res.error_detail = traceback.format_exc()
        return res


def _missing_file(
    repo: GitRepo,
    rel: str,
    entry: Tracked,
    src_abs: str,
    dst_abs: str,
    src_real: str,
    unreadable_dirs: list[str],
) -> FileResult:
    res = FileResult(
        rel_path=rel,
        status=Status.MISSING,
        src_path=join_rel(src_abs, rel),
        dst_path=join_rel(dst_abs, rel),
    )
    try:
        # A directory in SRC where HEAD has a file is a type conflict, not "missing".
        real = join_rel(src_real, rel)
        if os.path.isdir(real):
            res.status = Status.ERROR
            res.message = "SRC has a directory where Git HEAD has a file."
            res.error_detail = res.message
            return res
        for bad in unreadable_dirs:
            if bad and (rel == bad or rel.startswith(bad + "/")):
                res.status = Status.ERROR
                res.message = f"Cannot inspect: parent directory '{bad}' is unreadable."
                res.error_detail = res.message
                return res
        stream = repo.open_stream(rel)
        try:
            sha, size, binary = sha256_stream(stream)
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
        res.head_sha256, res.head_size, res.is_binary = sha, size, binary
        res.message = "Tracked in Git HEAD but not present in SRC."
        return res
    except Exception as exc:
        res.status = Status.ERROR
        res.message = f"Could not read committed content: {type(exc).__name__}: {exc}"
        res.error_detail = traceback.format_exc()
        return res
