import os

from guitar.models import Status
from guitar.scanner import scan
from guitar.state import (VIEW_ALL, VIEW_MATCHING, VIEW_PROBLEMS, AppState, check_dst, check_src)


def test_src_and_dst_are_independent():
    s = AppState()
    s.set_dst("/repo/dst")
    s.set_src("/some/src")
    assert (s.src_path, s.dst_path) == ("/some/src", "/repo/dst")
    s.set_src("/another/src")
    assert s.dst_path == "/repo/dst"                      # changing SRC never alters DST
    s.set_dst('  "/new/dst"  ')
    assert s.src_path == "/another/src" and s.dst_path == "/new/dst"
    s.set_src("")
    assert s.dst_path == "/new/dst"


def test_resolved_paths_are_derived_independently(env):
    res = scan(env.src, env.dst)
    r = next(x for x in res.results if x.rel_path == "same.txt")
    assert r.src_path == os.path.join(os.path.abspath(env.src), "same.txt")
    assert r.dst_path == os.path.join(os.path.abspath(env.dst), "same.txt")
    assert res.src_root != res.dst_root


def test_same_directory_detection(env, tmp_path):
    s = AppState()
    s.set_src(env.dst)
    s.set_dst(env.dst + os.sep)
    assert s.same_directory()
    s.set_src(env.src)
    assert not s.same_directory()


def test_path_checks(env, tmp_path):
    assert check_src("").level == "empty"
    assert check_src(str(tmp_path / "nope")).level == "error"
    assert check_src(env.src).level == "ok"
    assert check_dst(env.src).level == "error"           # no .git
    assert check_dst(env.dst).level == "ok"


def _state(env):
    s = AppState()
    s.set_src(env.src)
    s.set_dst(env.dst)
    s.set_scan(scan(env.src, env.dst))
    return s


def test_view_filters(env):
    s = _state(env)
    s.set_view(VIEW_ALL)
    assert len(s.visible_results()) == len(s.scan.results)
    s.set_view(VIEW_MATCHING)
    m = s.visible_results()
    assert m and all(r.status is Status.MATCH for r in m)
    assert {"same.txt", "empty.txt"} <= {r.rel_path for r in m}
    s.set_view(VIEW_PROBLEMS)
    p = s.visible_results()
    assert {r.status for r in p} == {Status.MISMATCH, Status.NOT_COMMITTED, Status.MISSING}
    assert len(m) + len(p) == len(s.scan.results)


def test_view_switch_does_not_rescan_and_keeps_counts_and_selection(env, monkeypatch):
    s = _state(env)
    scan_obj, counts = s.scan, s.counts()
    s.select("same.txt")
    calls = []
    import guitar.scanner
    monkeypatch.setattr(guitar.scanner, "scan", lambda *a, **k: calls.append(1))
    for v in (VIEW_MATCHING, VIEW_PROBLEMS, VIEW_ALL):
        s.set_view(v)
        s.visible_results()
    assert not calls and s.scan is scan_obj and s.counts() == counts
    assert s.selected == "same.txt"                        # selection retained


def test_search_filters_by_name_or_path(env):
    s = _state(env)
    s.set_view(VIEW_ALL)
    s.set_search("deep file")
    assert [r.rel_path for r in s.visible_results()] == ["nested/deep/file.py"]
    s.set_search("NA\u00cfVE")
    assert len(s.visible_results()) == 1
    s.set_search("zzz-nothing")
    assert s.visible_results() == []
    s.set_view(VIEW_MATCHING)
    s.set_search("diff.txt")                               # exists, but is a problem
    assert s.visible_results() == []


def test_sorting(env):
    s = _state(env)
    s.set_view(VIEW_ALL)
    s.set_sort("path")
    paths = [r.rel_path.casefold() for r in s.visible_results()]
    assert paths == sorted(paths)
    s.set_sort("path")                                     # second click reverses
    assert [r.rel_path.casefold() for r in s.visible_results()] == sorted(paths, reverse=True)


def test_selection_dropped_when_rescan_removes_file(env):
    s = _state(env)
    s.select("gone.txt")
    new = scan(env.src, env.dst)
    new.results = [r for r in new.results if r.rel_path != "gone.txt"]
    s.set_scan(new)
    assert s.selected is None


def test_theme_switch_preserves_everything(env):
    s = _state(env)
    s.set_view(VIEW_PROBLEMS)
    s.set_search("txt")
    s.select("diff.txt")
    before = (s.src_path, s.dst_path, s.scan, s.view, s.search, s.selected, s.visible_results())
    s.set_theme("light")
    s.set_theme("dark")
    after = (s.src_path, s.dst_path, s.scan, s.view, s.search, s.selected, s.visible_results())
    assert before == after and s.theme == "dark"
