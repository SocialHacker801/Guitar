"""Builds the content of the Problem Details inspector for one result.

The output is a flat list of :class:`Block` objects (a kind + text) that the
GUI renders into a read-only ``Text`` widget with theme-aware tags.  Keeping it
GUI-free makes it unit-testable.
"""

from __future__ import annotations

import difflib
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

from .git_backend import GitRepo
from .models import FileResult, Status
from .paths import fs_path, human_size

MAX_VIEW_BYTES = 8 * 1024 * 1024      # content shown in the inspector per side
DIFF_WINDOW_LINES = 4000              # max lines diffed per side
PREVIEW_LINES = 40
EOL_MARK = "\u240d"                   # ␍ makes a stray carriage return visible


@dataclass
class Block:
    kind: str       # heading|fact|para|ok|warn|err|trace|muted|hdr|hunk|add|del|ctx|mono|blank
    text: str = ""


@dataclass
class Details:
    result: FileResult
    headline: str
    blocks: list[Block] = field(default_factory=list)

    def text(self) -> str:
        """Plain-text rendering (used by tests and the 'copy' action)."""
        out = []
        for b in self.blocks:
            out.append(b.text.replace("\t", ": ") if b.kind == "fact" else b.text)
        return "\n".join(out)


# --------------------------------------------------------------------------
def _read_limited(stream, limit: int = MAX_VIEW_BYTES + 1) -> bytes:
    parts, got = [], 0
    while got < limit:
        chunk = stream.read(min(1 << 20, limit - got))
        if not chunk:
            break
        parts.append(chunk)
        got += len(chunk)
    return b"".join(parts)


def _decode(data: bytes) -> tuple[str, bool]:
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), True


NO_EOL_NOTE = "  \\ No newline at end of file"


def split_lines(text: str) -> list[str]:
    """Split on ``\\n`` only (so a stray CR stays visible).

    A trailing newline does not create an extra empty line; a missing final
    newline is annotated, so "x\\n" and "x" are shown as different.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    elif lines:
        lines[-1] += NO_EOL_NOTE
    return lines


def _visible(line: str) -> str:
    return line.replace("\r", EOL_MARK).replace("\t", "    ")


def _hexdump(data: bytes, start: int, length: int = 48) -> list[str]:
    lines = []
    for off in range(start, start + length, 16):
        row = data[off: off + 16]
        if not row and off >= len(data):
            break
        hexes = " ".join(f"{b:02x}" for b in row).ljust(47)
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        lines.append(f"{off:08x}  {hexes}  {ascii_}")
    return lines


def _fmt_byte(b: Optional[int]) -> str:
    if b is None:
        return "(end of file)"
    ch = chr(b) if 32 <= b < 127 else "\u00b7"
    return f"0x{b:02X}  ({b})  '{ch}'"


def _fmt_time(ts: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "\u2014"


def _size_line(res: FileResult) -> str:
    def one(n: Optional[int]) -> str:
        return "\u2014" if n is None else f"{human_size(n)} ({n:,} bytes)"
    return f"SRC {one(res.src_size)}   \u00b7   HEAD {one(res.head_size)}"


def unified_blocks(
    a_lines: list[str], b_lines: list[str], first_line: int = 1, context: int = 3
) -> tuple[list[Block], Optional[str]]:
    """Unified diff blocks with correct line numbers, windowed for big inputs."""
    note = None
    offset = 0
    if len(a_lines) > DIFF_WINDOW_LINES or len(b_lines) > DIFF_WINDOW_LINES:
        offset = max(0, first_line - 1 - 100)
        a_lines = a_lines[offset: offset + DIFF_WINDOW_LINES]
        b_lines = b_lines[offset: offset + DIFF_WINDOW_LINES]
        note = (
            f"Large file: the diff is limited to a {DIFF_WINDOW_LINES:,}-line window "
            f"starting at line {offset + 1}."
        )
    sm = difflib.SequenceMatcher(None, a_lines, b_lines, autojunk=False)
    blocks: list[Block] = []
    for group in sm.get_grouped_opcodes(context):
        f, l = group[0], group[-1]
        blocks.append(
            Block(
                "hunk",
                f"@@ -{f[1] + offset + 1},{l[2] - f[1]} +{f[3] + offset + 1},{l[4] - f[3]} @@",
            )
        )
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                blocks.extend(Block("ctx", "  " + _visible(x)) for x in a_lines[i1:i2])
                continue
            if tag in ("replace", "delete"):
                blocks.extend(Block("del", "- " + _visible(x)) for x in a_lines[i1:i2])
            if tag in ("replace", "insert"):
                blocks.extend(Block("add", "+ " + _visible(x)) for x in b_lines[j1:j2])
    return blocks, note


def _preview(data: bytes, kind: str, binary: bool, truncated: bool) -> list[Block]:
    if binary:
        return [Block("muted", "Binary file \u2014 preview not shown."),
                *[Block("mono", ln) for ln in _hexdump(data, 0, 64)]]
    text, _ = _decode(data[:MAX_VIEW_BYTES])
    lines = split_lines(text)
    shown = lines[:PREVIEW_LINES]
    out = [Block(kind, f"{i:>5}  {_visible(ln)}") for i, ln in enumerate(shown, 1)]
    if len(lines) > PREVIEW_LINES or truncated:
        out.append(Block("muted", f"\u2026 preview limited to the first {PREVIEW_LINES} lines."))
    if not data:
        out = [Block("muted", "(empty file)")]
    return out


# --------------------------------------------------------------------------
def build_details(
    res: FileResult, repo: Optional[GitRepo], head_summary: str = ""
) -> Details:
    """Create the inspector content for *res*.

    *repo* may be ``None`` (or unusable); in that case only data already stored
    in the result is shown and a warning is added.
    """
    d = Details(res, res.message)
    B = d.blocks.append
    baseline = f"Git HEAD \u2014 {head_summary}" if head_summary else "Git HEAD (latest commit)"

    # ---- explanation ------------------------------------------------------
    B(Block("heading", "Finding"))
    explain = {
        Status.MATCH: (
            "ok",
            "This file's content matches the committed Git snapshot (HEAD) exactly, "
            "byte for byte \u2014 including line endings and encoding.",
        ),
        Status.MISMATCH: (
            "err",
            "The SRC file differs from the version committed in Git HEAD. HEAD is the "
            "baseline; staged or working-tree changes in DST are not considered.",
        ),
        Status.NOT_COMMITTED: (
            "warn",
            "The file exists in SRC but is not part of the latest commit. It may be new, "
            "untracked, or only staged (Guitar compares against HEAD, not the index). "
            "It is not excluded by the supported root .gitignore rules.",
        ),
        Status.MISSING: (
            "warn",
            "Git HEAD records this file, but it does not exist in SRC. It may have been "
            "deleted, moved or renamed in the original source directory.",
        ),
        Status.ERROR: (
            "err",
            "Guitar could not complete the inspection of this path. The original "
            "exception is shown below; no data was modified.",
        ),
    }[res.status]
    B(Block(explain[0], explain[1]))
    if res.message and res.message not in explain[1]:
        B(Block("para", res.message))

    # ---- facts -------------------------------------------------------------
    B(Block("blank"))
    B(Block("heading", "Details"))
    B(Block("fact", f"File\t{res.name}"))
    B(Block("fact", f"Relative path\t{res.rel_path}"))
    B(Block("fact", f"SRC path\t{res.src_path}"))
    B(Block("fact", f"DST repo path\t{res.dst_path}"))
    B(Block("fact", f"Baseline\t{baseline}"))
    B(Block("fact", f"Status\t{res.status.value}"))
    B(Block("fact", f"Size\t{_size_line(res)}"))
    B(Block("fact", f"Modified (SRC)\t{_fmt_time(res.src_mtime)}"))
    same = bool(res.src_sha256 and res.src_sha256 == res.head_sha256)
    B(Block("fact", f"SHA-256 SRC\t{res.src_sha256 or chr(0x2014)}"))
    B(Block("fact", f"SHA-256 HEAD\t{res.head_sha256 or chr(0x2014)}" + ("   (identical)" if same else "")))
    if res.status is Status.MISMATCH:
        if res.is_binary:
            B(Block("fact", f"First differing byte\toffset {res.first_diff_byte} (0x{res.first_diff_byte or 0:X})"))
        else:
            B(Block("fact", f"First differing line\t{res.first_diff_line}"))
            B(Block("fact", f"First differing byte\toffset {res.first_diff_byte}"))
    B(Block("fact", f"Content type\t{'binary' if res.is_binary else 'text'}"))

    # ---- error status: exception text is the content ------------------------
    if res.status is Status.ERROR:
        B(Block("blank"))
        B(Block("heading", "Exception details"))
        for ln in (res.error_detail or res.message).rstrip().splitlines():
            B(Block("trace", ln))
        return d

    # ---- load content ------------------------------------------------------
    src_data: Optional[bytes] = None
    head_data: Optional[bytes] = None
    src_trunc = head_trunc = False
    problems: list[str] = []
    if res.status is not Status.MISSING:
        try:
            with open(fs_path(res.src_path), "rb") as fh:
                src_data = _read_limited(fh)
            src_trunc = len(src_data) > MAX_VIEW_BYTES
        except Exception as exc:
            problems.append(f"SRC file could not be re-read for display: {type(exc).__name__}: {exc}")
    if res.status is not Status.NOT_COMMITTED:
        if repo is None:
            problems.append("Repository is not available, so the HEAD content cannot be displayed.")
        else:
            try:
                stream = repo.open_stream(res.rel_path)
                try:
                    head_data = _read_limited(stream)
                finally:
                    close = getattr(stream, "close", None)
                    if close:
                        close()
                head_trunc = len(head_data) > MAX_VIEW_BYTES
            except Exception as exc:
                problems.append(f"HEAD content could not be read: {type(exc).__name__}: {exc}")

    if problems:
        B(Block("blank"))
        for p in problems:
            B(Block("warn", p))

    if src_data is not None and not src_trunc and res.src_sha256:
        if hashlib.sha256(src_data).hexdigest() != res.src_sha256:
            B(Block("blank"))
            B(Block("warn", "Note: the SRC file changed after the scan. Re-scan for current results."))

    big = src_trunc or head_trunc
    B(Block("blank"))

    # ---- per status content --------------------------------------------------
    if res.status is Status.MATCH:
        B(Block("heading", "Content"))
        B(Block("ok", "Matches the committed Git snapshot."))
        if src_data is not None:
            for blk in _preview(src_data, "ctx", res.is_binary, src_trunc):
                B(blk)
        return d

    if res.status is Status.NOT_COMMITTED:
        B(Block("heading", "SRC content (not in HEAD)"))
        if src_data is not None:
            for blk in _preview(src_data, "add", res.is_binary, src_trunc):
                B(blk)
        return d

    if res.status is Status.MISSING:
        B(Block("heading", "HEAD content (missing from SRC)"))
        if head_data is not None:
            for blk in _preview(head_data, "del", res.is_binary, head_trunc):
                B(blk)
        return d

    # ---- MISMATCH ----------------------------------------------------------
    if src_data is None or head_data is None:
        return d

    if res.is_binary:
        off = res.first_diff_byte or 0
        B(Block("heading", "Binary difference"))
        B(Block("fact", f"Offset\t{off} (0x{off:X})"))
        B(Block("fact", f"HEAD byte\t{_fmt_byte(res.head_byte)}"))
        B(Block("fact", f"SRC byte\t{_fmt_byte(res.src_byte)}"))
        B(Block("blank"))
        start = max(0, off - off % 16 - 16)
        B(Block("heading", "Expected (HEAD) bytes"))
        for ln in _hexdump(head_data, start):
            B(Block("del", ln))
        B(Block("blank"))
        B(Block("heading", "Actual (SRC) bytes"))
        for ln in _hexdump(src_data, start):
            B(Block("add", ln))
        return d

    head_text, h_bad = _decode(head_data)
    src_text, s_bad = _decode(src_data)
    h_lines, s_lines = split_lines(head_text), split_lines(src_text)
    line_no = res.first_diff_line or 1
    if h_bad or s_bad:
        B(Block("warn", "Content is not valid UTF-8; undecodable bytes are shown as \ufffd."))

    if head_data.replace(b"\r\n", b"\n") == src_data.replace(b"\r\n", b"\n"):
        B(Block("warn", "Only line endings differ (CRLF vs LF). Each \u240d marks a carriage return."))

    B(Block("heading", f"First difference \u2014 line {line_no}"))
    exp = h_lines[line_no - 1] if line_no - 1 < len(h_lines) else None
    act = s_lines[line_no - 1] if line_no - 1 < len(s_lines) else None
    B(Block("fact", "Expected (HEAD)\t" + ("(end of file)" if exp is None else _visible(exp) or "(empty line)")))
    B(Block("fact", "Actual (SRC)\t" + ("(end of file)" if act is None else _visible(act) or "(empty line)")))
    B(Block("blank"))
    B(Block("heading", "Unified diff  (\u2212 HEAD   + SRC)"))
    if big:
        B(Block("warn", f"File exceeds {human_size(MAX_VIEW_BYTES)}; the inspector shows only the beginning. "
                        "Use the first differing line/byte above to locate the change."))
    B(Block("hdr", f"--- HEAD:{res.rel_path}"))
    B(Block("hdr", f"+++ SRC:{res.rel_path}"))
    blocks, note = unified_blocks(h_lines, s_lines, line_no)
    if not blocks:
        B(Block("muted", "No textual differences within the displayed range."))
    if note:
        B(Block("warn", note))
    d.blocks.extend(blocks)
    return d


class DetailsProvider:
    """Caches Details per path and keeps one lazily opened repo handle.

    Must be used from a single thread (the Tk main thread).
    """

    def __init__(self) -> None:
        self._repo: Optional[GitRepo] = None
        self._root: Optional[str] = None
        self._cache: dict[str, Details] = {}
        self._repo_error: Optional[str] = None

    def reset(self) -> None:
        self._cache.clear()
        self._repo_error = None
        if self._repo is not None:
            self._repo.close()
        self._repo, self._root = None, None

    def get(self, res: FileResult, dst_root: str, head_summary: str) -> Details:
        key = res.rel_path
        if key in self._cache:
            return self._cache[key]
        repo = None
        if res.status is not Status.NOT_COMMITTED and res.status is not Status.ERROR:
            if self._repo is None and self._repo_error is None:
                try:
                    self._repo = GitRepo.open(dst_root)
                    self._root = dst_root
                except Exception as exc:
                    self._repo_error = str(exc)
            repo = self._repo
        d = build_details(res, repo, head_summary)
        if len(self._cache) > 300:
            self._cache.clear()
        self._cache[key] = d
        return d
