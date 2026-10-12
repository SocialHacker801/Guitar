import os
import shutil
import subprocess

import pytest

from conftest import HAS_GIT, init_repo, run_git, write
from guitar import scanner
from guitar.git_backend import RepoError
from guitar.models import Status
from guitar.scanner import ScanError, scan


def by_path(res):
    return {r.rel_path: r for r in res.results}


def test_statuses(env):
    r = by_path(scan(env.src, env.dst))
    assert r["same.txt"].status is Status.MATCH
    assert r["nested/deep/file.py"].status is Status.MATCH
    assert r["empty.txt"].status is Status.MATCH            # empty files
    assert r["unic\u00f6de/na\u00efve \u6587\u4ef6.txt"].status is Status.MATCH   # unicode names
    assert r["diff.txt"].status is Status.MISMATCH
    assert r["bin/data.bin"].status is Status.MISMATCH
    assert r["brand_new.txt"].status is Status.NOT_COMMITTED
    assert r["gone.txt"].status is Status.MISSING


def test_text_difference_line_number(env):
    r = by_path(scan(env.src, env.dst))["diff.txt"]
    assert r.first_diff_line == 2
    assert not r.is_binary
    assert r.first_diff_byte == 4            # "one\n" is 4 bytes, "T" differs at offset 4
    assert r.src_sha256 != r.head_sha256


def test_binary_difference_offset(env):
    r = by_path(scan(env.src, env.dst))["bin/data.bin"]
    assert r.is_binary
    assert r.first_diff_byte == 300
    assert r.head_byte == 300 % 256
    assert r.src_byte == (300 % 256) ^ 0xFF


def test_ignored_untracked_files_are_skipped(env):
    res = scan(env.src, env.dst)
    paths = by_path(res)
    assert "debug.log" not in paths and "build/out.o" not in paths
    assert "debug.log" in res.ignored and "build/" in res.ignored


def test_tracked_file_is_never_ignored(env):
    # A tracked file matching an ignore pattern is still compared.
    write(env.dst, "keep.log", "tracked log\n")
    run_git(env.dst, "add", "-f", "keep.log")
    run_git(env.dst, "commit", "-q", "-m", "add log")
    write(env.src, "keep.log", "tracked log CHANGED\n")
    assert by_path(scan(env.src, env.dst))["keep.log"].status is Status.MISMATCH


def test_compares_against_head_not_index_or_worktree(env):
    # Stage a change and edit the working tree in DST; SRC equals the *committed* text.
    write(env.dst, "same.txt", "staged change\n")
    run_git(env.dst, "add", "same.txt")
    write(env.dst, "same.txt", "worktree change\n")
    assert by_path(scan(env.src, env.dst))["same.txt"].status is Status.MATCH


def test_line_endings_difference_is_a_mismatch(env):
    write(env.src, "same.txt", "alpha\r\nbeta\r\ngamma\r\n")
    r = by_path(scan(env.src, env.dst))["same.txt"]
    assert r.status is Status.MISMATCH and r.first_diff_line == 1


def test_scan_is_read_only(env):
    head = subprocess.run(["git", "-C", env.dst, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    status = subprocess.run(["git", "-C", env.dst, "status", "--porcelain"], capture_output=True, text=True).stdout
    before = {p: os.stat(os.path.join(env.src, p)).st_mtime_ns for p in ("same.txt", "diff.txt")}
    scan(env.src, env.dst)
    assert subprocess.run(["git", "-C", env.dst, "rev-parse", "HEAD"], capture_output=True, text=True).stdout == head
    assert subprocess.run(["git", "-C", env.dst, "status", "--porcelain"], capture_output=True, text=True).stdout == status
    assert before == {p: os.stat(os.path.join(env.src, p)).st_mtime_ns for p in before}


def test_repo_without_commits(tmp_path):
    if not HAS_GIT:
        pytest.skip("git missing")
    dst, src = tmp_path / "d", tmp_path / "s"
    init_repo(dst)
    write(src, "a.txt", "x")
    res = scan(str(src), str(dst))
    assert [r.status for r in res.results] == [Status.NOT_COMMITTED]
    assert res.head_sha is None and any("no commits" in w for w in res.warnings)


def test_invalid_repository_errors(tmp_path):
    src = tmp_path / "s"
    plain = tmp_path / "plain"
    src.mkdir()
    plain.mkdir()
    with pytest.raises(RepoError):
        scan(str(src), str(plain))
    with pytest.raises(RepoError):
        scan(str(src), str(tmp_path / "does-not-exist"))
    with pytest.raises(RepoError):
        scan(str(src), "")


def test_repo_subfolder_gives_helpful_error(env):
    sub = os.path.join(env.dst, "nested")
    with pytest.raises(RepoError) as e:
        scan(env.src, sub)
    assert "root" in str(e.value)


def test_invalid_src(env, tmp_path):
    with pytest.raises(ScanError):
        scan(str(tmp_path / "nope"), env.dst)
    with pytest.raises(ScanError):
        scan("", env.dst)
    f = write(tmp_path, "afile.txt", "x")
    with pytest.raises(ScanError):
        scan(f, env.dst)


def test_unreadable_file_reports_error_with_exception(env, monkeypatch):
    real = scanner.compare_streams

    def boom(head, src):
        raise PermissionError(13, "Permission denied (simulated)")

    monkeypatch.setattr(scanner, "compare_streams", boom)
    res = by_path(scan(env.src, env.dst))
    r = res["same.txt"]
    assert r.status is Status.ERROR
    assert "PermissionError" in r.message and "simulated" in r.error_detail
    assert res["brand_new.txt"].status is Status.NOT_COMMITTED      # scan carried on


def test_directory_where_file_expected_is_error(env):
    os.remove(os.path.join(env.src, "same.txt"))
    os.makedirs(os.path.join(env.src, "same.txt"))
    assert by_path(scan(env.src, env.dst))["same.txt"].status is Status.ERROR


def test_cancel(env):
    import threading
    ev = threading.Event()
    ev.set()
    with pytest.raises(scanner.ScanCancelled):
        scan(env.src, env.dst, cancel=ev)


def test_progress_callback(env):
    calls = []
    scan(env.src, env.dst, progress=lambda *a: calls.append(a))
    assert calls and calls[-1][0] == calls[-1][1]            # done == total at the end


def test_large_file_streaming_across_chunks(env, monkeypatch):
    monkeypatch.setattr(scanner, "CHUNK", 64)
    big = ("0123456789\n" * 50)
    write(env.dst, "big.txt", big)
    run_git(env.dst, "add", "big.txt")
    run_git(env.dst, "commit", "-q", "-m", "big")
    write(env.src, "big.txt", big[:333] + "X" + big[334:])
    r = by_path(scan(env.src, env.dst))["big.txt"]
    assert r.status is Status.MISMATCH and r.first_diff_byte == 333
    assert r.first_diff_line == 333 // 11 + 1


def test_first_diff_index_helper():
    f = scanner.first_diff_index
    assert f(b"abc", b"abc") == 3
    assert f(b"abc", b"abd") == 2
    assert f(b"abc", b"abcdef") == 3
    assert f(b"", b"x") == 0
    assert f(b"xaaaa", b"yaaaa") == 0
