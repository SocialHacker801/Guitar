"""``.gitignore`` filtering for the SRC scan.

ACTUAL SUPPORT (and limitations)
--------------------------------
* The **root** ``.gitignore`` only is honoured (taken from HEAD when committed,
  otherwise from the DST working tree).  Patterns are interpreted by
  ``pathspec.GitIgnoreSpec`` which implements Git's wildmatch semantics for
  that single file (negation, ``**``, anchored and directory-only patterns).
* NOT supported: nested ``.gitignore`` files in sub-directories,
  ``.git/info/exclude``, the global ``core.excludesFile`` and
  ``--assume-unchanged`` style flags.  Guitar therefore does not claim full
  Git-native ignore compatibility.
* As in Git, ignore rules never hide files that are *tracked* in HEAD: tracked
  files are always compared.  Rules only suppress *untracked* SRC files (which
  would otherwise be reported as NOT COMMITTED).
* The ``.git`` directory is always skipped.
"""

from __future__ import annotations

from typing import Iterable, Optional

import pathspec


class IgnoreRules:
    def __init__(self, lines: Iterable[str] = (), origin: str = "none") -> None:
        self.origin = origin
        self._lines = [ln for ln in lines]
        self._spec = (
            pathspec.GitIgnoreSpec.from_lines(self._lines) if self._lines else None
        )

    @classmethod
    def from_text(cls, text: Optional[str], origin: str = "none") -> "IgnoreRules":
        if not text:
            return cls((), origin)
        return cls(text.splitlines(), origin)

    @property
    def active(self) -> bool:
        return self._spec is not None

    def is_ignored(self, rel_posix: str, is_dir: bool = False) -> bool:
        """True if *rel_posix* (POSIX, relative to the root) matches the rules."""
        if rel_posix == ".git" or rel_posix.startswith(".git/"):
            return True
        if self._spec is None:
            return False
        path = rel_posix + "/" if is_dir and not rel_posix.endswith("/") else rel_posix
        return bool(self._spec.match_file(path))
