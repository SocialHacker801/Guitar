"""Filesystem path helpers (long Windows paths, normalisation, same-dir checks)."""

from __future__ import annotations

import os
from pathlib import Path


def normalize_user_path(text: str) -> str:
    """Trim whitespace/quotes that commonly sneak in when pasting paths."""
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def fs_path(path: str) -> str:
    """Return a path safe for the OS APIs.

    On Windows, paths longer than MAX_PATH (260) need the ``\\\\?\\`` prefix.
    The prefix is applied to every absolute path (harmless for short ones).
    On other platforms the absolute path is returned unchanged.
    """
    if os.name != "nt":
        return os.path.abspath(path)
    p = os.path.abspath(path)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):                 # UNC share
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def display_path(path: str) -> str:
    """Strip the Windows extended-length prefix for human display."""
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def join_rel(root: str, rel_posix: str) -> str:
    """Join *root* with a POSIX relative path using the OS separator."""
    return os.path.join(root, *rel_posix.split("/")) if rel_posix else root


def same_directory(a: str, b: str) -> bool:
    """True when both paths resolve to the same physical directory."""
    if not a or not b:
        return False
    try:
        pa, pb = fs_path(a), fs_path(b)
        if os.path.exists(pa) and os.path.exists(pb):
            return os.path.samefile(pa, pb)
    except OSError:
        pass
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(
            str(Path(b).resolve())
        )
    except (OSError, RuntimeError):
        return False


def human_size(n: int | None) -> str:
    if n is None:
        return "\u2014"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"
