import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HAS_GIT = shutil.which("git") is not None


def run_git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def init_repo(path, commit=True):
    os.makedirs(path, exist_ok=True)
    run_git(path, "init", "-q")
    run_git(path, "config", "user.email", "t@example.com")
    run_git(path, "config", "user.name", "Tester")
    run_git(path, "config", "commit.gpgsign", "false")


def write(root, rel, data):
    p = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    return p


@pytest.fixture
def env(tmp_path):
    """DST = committed repo, SRC = copy of it with controlled differences applied by tests."""
    if not HAS_GIT:
        pytest.skip("git executable not available")
    dst, src = tmp_path / "dst", tmp_path / "src"
    init_repo(dst)
    write(dst, "same.txt", "alpha\nbeta\ngamma\n")
    write(dst, "diff.txt", "one\ntwo\nthree\nfour\n")
    write(dst, "nested/deep/file.py", "print('x')\n")
    write(dst, "bin/data.bin", bytes(range(256)) * 4)
    write(dst, "empty.txt", b"")
    write(dst, "gone.txt", "will be missing\n")
    write(dst, "unic\u00f6de/na\u00efve \u6587\u4ef6.txt", "h\u00e9llo\n")
    write(dst, ".gitignore", "*.log\nbuild/\n")
    run_git(dst, "add", "-A")
    run_git(dst, "commit", "-q", "-m", "initial")
    shutil.copytree(dst, src, ignore=shutil.ignore_patterns(".git"))
    os.remove(src / "gone.txt")
    write(src, "diff.txt", "one\nTWO\nthree\nfour\n")
    data = bytearray(bytes(range(256)) * 4)
    data[300] ^= 0xFF
    write(src, "bin/data.bin", bytes(data))
    write(src, "brand_new.txt", "new file\n")
    write(src, "debug.log", "ignored\n")
    write(src, "build/out.o", "ignored dir\n")

    class E:
        pass

    e = E()
    e.src, e.dst, e.tmp = str(src), str(dst), tmp_path
    return e
