"""Read-only access to a Git repository's HEAD snapshot via GitPython.

Only *reading* operations are used: this module never writes to the repository,
never stages, never commits and never resets.  The comparison baseline is the
tree of the latest commit (``HEAD``) — not the index and not the working tree.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:  # GitPython raises ImportError when the git executable is unavailable.
    import git
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

    _GIT_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - depends on the host machine
    git = None  # type: ignore[assignment]
    GitCommandError = InvalidGitRepositoryError = NoSuchPathError = Exception  # type: ignore
    _GIT_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

from .paths import fs_path

GITLINK_MODE = 0o160000      # submodule entries are skipped
SYMLINK_MODE = 0o120000


class RepoError(Exception):
    """Raised for invalid repositories or unrecoverable Git failures."""


@dataclass(frozen=True)
class Tracked:
    """A file recorded in the HEAD tree."""

    path: str
    hexsha: str
    mode: int


class GitRepo:
    """Thin read-only wrapper around :class:`git.Repo`."""

    def __init__(self, repo: "git.Repo", root: str) -> None:
        self._repo = repo
        self.root = root
        self._tracked: Optional[dict[str, Tracked]] = None
        self.has_commits = False
        self.head_sha: Optional[str] = None
        self.head_summary = "No commits yet"
        self._commit = None
        self._load_head()

    # ------------------------------------------------------------------ open
    @classmethod
    def open(cls, path: str) -> "GitRepo":
        if _GIT_IMPORT_ERROR:
            raise RepoError(
                "GitPython could not be loaded (is Git installed and on PATH?): "
                + _GIT_IMPORT_ERROR
            )
        if not path:
            raise RepoError("No destination (DST) repository directory selected.")
        real = fs_path(path)
        if not os.path.exists(real):
            raise RepoError(f"DST path does not exist: {path}")
        if not os.path.isdir(real):
            raise RepoError(f"DST path is not a directory: {path}")
        try:
            repo = git.Repo(real, search_parent_directories=False)
        except InvalidGitRepositoryError:
            hint = ""
            try:
                parent = git.Repo(real, search_parent_directories=True)
                if parent.working_tree_dir:
                    hint = (
                        f" It lies inside the repository at "
                        f"{parent.working_tree_dir}; choose that folder instead."
                    )
                parent.close()
            except Exception:
                pass
            raise RepoError(f"DST is not the root of a Git repository: {path}.{hint}")
        except NoSuchPathError:
            raise RepoError(f"DST path does not exist: {path}")
        except Exception as exc:
            raise RepoError(f"Could not open repository ({type(exc).__name__}): {exc}")
        if repo.bare or not repo.working_tree_dir:
            repo.close()
            raise RepoError("Bare repositories are not supported; choose a working copy.")
        try:
            return cls(repo, path)
        except RepoError:
            repo.close()
            raise
        except Exception as exc:
            repo.close()
            raise RepoError(f"Could not read repository ({type(exc).__name__}): {exc}")

    def close(self) -> None:
        try:
            self._repo.close()
        except Exception:
            pass

    def __enter__(self) -> "GitRepo":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ HEAD
    def _load_head(self) -> None:
        try:
            valid = self._repo.head.is_valid()
        except Exception:
            valid = False
        if not valid:
            self.has_commits = False
            return
        try:
            commit = self._repo.head.commit
        except Exception as exc:
            raise RepoError(f"Could not resolve HEAD: {exc}")
        self._commit = commit
        self.has_commits = True
        self.head_sha = commit.hexsha
        summary = str(commit.summary).strip()
        self.head_summary = f"{commit.hexsha[:10]} \u2014 {summary}" if summary else commit.hexsha[:10]

    def tracked_files(self) -> dict[str, Tracked]:
        """Map POSIX relative path -> blob entry for every file in HEAD."""
        if self._tracked is not None:
            return self._tracked
        files: dict[str, Tracked] = {}
        if self._commit is not None:
            try:
                for item in self._commit.tree.traverse():
                    if item.type != "blob":       # skip trees and submodules
                        continue
                    if item.mode == GITLINK_MODE:
                        continue
                    files[item.path] = Tracked(item.path, item.hexsha, item.mode)
            except Exception as exc:
                raise RepoError(f"Could not read the HEAD tree: {exc}")
        self._tracked = files
        return files

    def read_blob(self, rel_path: str) -> bytes:
        """Return the committed bytes of *rel_path* in HEAD."""
        entry = self.tracked_files().get(rel_path)
        if entry is None:
            raise KeyError(f"{rel_path} is not tracked in HEAD")
        blob = self._commit.tree / rel_path          # type: ignore[union-attr]
        return blob.data_stream.read()

    def open_stream(self, rel_path: str):
        """Return a binary file-like object streaming the HEAD content of *rel_path*."""
        if rel_path not in self.tracked_files():
            raise KeyError(f"{rel_path} is not tracked in HEAD")
        blob = self._commit.tree / rel_path          # type: ignore[union-attr]
        return blob.data_stream

    def read_root_gitignore(self) -> tuple[Optional[str], str]:
        """Return ``(text, origin)`` of the root ``.gitignore``.

        Preference: the version committed in HEAD; otherwise the file in the
        DST working tree; otherwise ``(None, "none")``.
        """
        if ".gitignore" in self.tracked_files():
            try:
                data = self.read_blob(".gitignore")
                return data.decode("utf-8", errors="replace"), "HEAD:.gitignore"
            except Exception:
                pass
        candidate = os.path.join(fs_path(self.root), ".gitignore")
        try:
            if os.path.isfile(candidate):
                with open(candidate, "rb") as fh:
                    return fh.read().decode("utf-8", errors="replace"), "DST:.gitignore"
        except OSError:
            pass
        return None, "none"
