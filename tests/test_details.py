import os

from conftest import write
from guitar.details import build_details
from guitar.git_backend import GitRepo
from guitar.scanner import scan


def details(env, rel, monkeypatch=None):
    res = scan(env.src, env.dst)
    r = next(x for x in res.results if x.rel_path == rel)
    with GitRepo.open(env.dst) as repo:
        return build_details(r, repo, res.head_summary)


def kinds(d):
    return {b.kind for b in d.blocks}


def test_match_details_state_it_matches(env):
    d = details(env, "same.txt")
    t = d.text()
    assert "matches the committed Git snapshot" in t and "(identical)" in t
    assert "Git HEAD" in t and os.path.join(env.src, "same.txt") in t and os.path.join(env.dst, "same.txt") in t


def test_text_mismatch_details(env):
    d = details(env, "diff.txt")
    t = d.text()
    assert "First differing line: 2" in t
    assert "Expected (HEAD): two" in t and "Actual (SRC): TWO" in t
    assert any(b.kind == "del" and b.text == "- two" for b in d.blocks)
    assert any(b.kind == "add" and b.text == "+ TWO" for b in d.blocks)
    assert any(b.kind == "hunk" and b.text.startswith("@@ -1,4 +1,4 @@") for b in d.blocks)


def test_binary_mismatch_details(env):
    d = details(env, "bin/data.bin")
    t = d.text()
    assert "offset 300" in t and "HEAD byte" in t and "SRC byte" in t
    assert {"add", "del"} <= kinds(d)


def test_missing_and_uncommitted_details(env):
    assert "does not exist in SRC" in details(env, "gone.txt").text()
    assert "will be missing" in details(env, "gone.txt").text()
    d = details(env, "brand_new.txt")
    assert "not part of the latest commit" in d.text() and "new file" in d.text()


def test_line_ending_note(env):
    write(env.src, "same.txt", "alpha\r\nbeta\r\ngamma\r\n")
    t = details(env, "same.txt").text()
    assert "Only line endings differ" in t and "\u240d" in t


def test_no_trailing_newline_is_visible(env):
    write(env.src, "same.txt", "alpha\nbeta\ngamma")
    assert "No newline at end of file" in details(env, "same.txt").text()


def test_error_details_show_exception(env, monkeypatch):
    from guitar import scanner
    monkeypatch.setattr(scanner, "compare_streams", lambda h, s: (_ for _ in ()).throw(OSError(5, "I/O boom")))
    d = details(env, "same.txt")
    assert "Exception details" in d.text() and "I/O boom" in d.text()
    assert "trace" in kinds(d)


def test_content_changed_after_scan_is_flagged(env):
    res = scan(env.src, env.dst)
    r = next(x for x in res.results if x.rel_path == "same.txt")
    write(env.src, "same.txt", "modified later\n")
    with GitRepo.open(env.dst) as repo:
        assert "changed after the scan" in build_details(r, repo).text()


def test_repo_unavailable_still_renders(env):
    res = scan(env.src, env.dst)
    r = next(x for x in res.results if x.rel_path == "diff.txt")
    assert "Repository is not available" in build_details(r, None).text()
