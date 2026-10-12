"""Real Tk tests. Skipped automatically when no display is available."""

import os
import time
import tkinter as tk

import pytest

from guitar.gui.app import GuitarApp
from guitar.state import VIEW_ALL, VIEW_DASHBOARD, VIEW_MATCHING, VIEW_PROBLEMS, VIEW_REPORTS


@pytest.fixture
def app(env, monkeypatch, tmp_path):
    monkeypatch.setenv("GUITAR_CONFIG_DIR", str(tmp_path / "cfg"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1380x880+0+0")
    a = GuitarApp(root, use_settings=False)
    a.env = env
    yield a
    try:
        root.destroy()
    except tk.TclError:
        pass


def pump(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.005)


def do_scan(app):
    app.scan_card.src.set_path(app.env.src)
    app.scan_card.dst.set_path(app.env.dst)
    pump(app, 0.1)
    app.start_scan()
    end = time.time() + 20
    while app._scanning and time.time() < end:
        pump(app, 0.02)
    pump(app, 0.4)
    assert not app._scanning and app.state.scan is not None


def table_paths(app):
    t = app.results.table
    return {t._rel_by_iid[i] for i in t.tree.get_children()}


def test_independent_selectors_in_ui(app):
    app.scan_card.dst.set_path("/dst/one")
    app.scan_card.src.set_path("/src/one")
    app.scan_card.src.set_path("/src/two")
    assert app.state.dst_path == "/dst/one" and app.scan_card.dst.var.get() == "/dst/one"
    app.scan_card.dst.set_path("/dst/two")
    assert app.state.src_path == "/src/two" and app.scan_card.src.var.get() == "/src/two"


def test_scan_and_views_show_real_rows(app):
    do_scan(app)
    c = app.state.counts()
    assert c["match"] >= 4 and c["mismatch"] == 2
    app.show_view(VIEW_ALL)
    pump(app)
    assert len(table_paths(app)) == c["total"]
    app.show_view(VIEW_MATCHING)
    pump(app)
    rows = table_paths(app)
    assert len(rows) == c["match"] and "same.txt" in rows and "diff.txt" not in rows
    assert app.cards["match"].value.cget("text") == f"{c['match']:,}"      # counts preserved
    app.show_view(VIEW_PROBLEMS)
    pump(app)
    assert table_paths(app) == {"diff.txt", "bin/data.bin", "brand_new.txt", "gone.txt"}
    assert str(app.nav[VIEW_PROBLEMS].count) == str(c["problems"])


def test_search_filter_and_empty_state(app):
    do_scan(app)
    app.show_view(VIEW_ALL)
    app.results.search_var.set("deep")
    pump(app, 0.5)
    assert table_paths(app) == {"nested/deep/file.py"}
    app.results.search_var.set("qqqq-none")
    pump(app, 0.5)
    assert table_paths(app) == set() and app.results.table.empty.winfo_ismapped()
    app.results.search_var.set("")
    pump(app, 0.5)
    assert len(table_paths(app)) == app.state.counts()["total"]


def test_selection_populates_inspector_and_survives_view_change(app):
    do_scan(app)
    app.show_view(VIEW_PROBLEMS)
    pump(app)
    t = app.results.table
    iid = t._iid_by_rel["diff.txt"]
    t.tree.selection_set(iid)
    pump(app, 0.4)
    assert app.state.selected == "diff.txt"
    shown = app.inspector.viewer.text.get("1.0", "end")
    assert "Actual (SRC)" in shown and "TWO" in shown
    assert app.inspector.name.cget("text") == "diff.txt"
    app.show_view(VIEW_ALL)
    pump(app)
    assert app.state.selected == "diff.txt" and t.tree.selection() == (t._iid_by_rel["diff.txt"],)
    app.show_view(VIEW_MATCHING)                      # not visible there, but selection kept in state
    pump(app)
    assert app.state.selected == "diff.txt"
    assert "TWO" in app.inspector.viewer.text.get("1.0", "end")


def test_matching_file_inspector_says_it_matches(app):
    do_scan(app)
    app.show_view(VIEW_MATCHING)
    pump(app)
    t = app.results.table
    t.tree.selection_set(t._iid_by_rel["same.txt"])
    pump(app, 0.4)
    assert "matches the committed Git snapshot" in app.inspector.viewer.text.get("1.0", "end")


def test_theme_toggle_restyles_in_place_and_preserves_state(app):
    do_scan(app)
    app.show_view(VIEW_PROBLEMS)
    app.results.search_var.set("txt")
    pump(app, 0.5)
    t = app.results.table
    t.tree.selection_set(t._iid_by_rel["diff.txt"])
    pump(app, 0.3)
    ids_before = (id(app.results), id(t), id(app.scan_card.src.field.entry), id(app.inspector))
    before = (app.state.src_path, app.state.dst_path, app.state.scan, app.state.view,
              app.state.search, app.state.selected, table_paths(app))
    dark_bg = app.root.cget("bg")
    dark_card = app.results.table_card.body.cget("bg")
    dark_text_tag = app.inspector.viewer.text.tag_cget("add", "background")
    app.toggle.toggle()                                # click the real toggle
    pump(app, 0.6)
    assert app.state.theme == "light" and app.toggle.mode == "light"
    assert app.root.cget("bg") != dark_bg
    assert app.results.table_card.body.cget("bg") != dark_card
    assert app.inspector.viewer.text.tag_cget("add", "background") != dark_text_tag
    assert str(app.tm.style.lookup("Guitar.Treeview", "background")) == "#FFFFFF"
    assert app.scan_card.src.field.entry.cget("bg") == "#F8F5FF"
    after = (app.state.src_path, app.state.dst_path, app.state.scan, app.state.view,
             app.state.search, app.state.selected, table_paths(app))
    assert before == after
    assert app.scan_card.src.var.get() == app.env.src and app.results.search_var.get() == "txt"
    assert t.tree.selection() == (t._iid_by_rel["diff.txt"],)
    assert ids_before == (id(app.results), id(t), id(app.scan_card.src.field.entry), id(app.inspector))
    app.set_theme("dark")
    pump(app, 0.4)
    assert app.root.cget("bg") == dark_bg


def test_no_duplicate_scans(app):
    app.scan_card.src.set_path(app.env.src)
    app.scan_card.dst.set_path(app.env.dst)
    app.start_scan()
    first = app._worker
    app.start_scan()
    assert app._worker is first
    end = time.time() + 20
    while app._scanning and time.time() < end:
        pump(app, 0.02)


def test_scan_with_invalid_repo_shows_error_not_crash(app, tmp_path):
    app.scan_card.src.set_path(app.env.src)
    plain = tmp_path / "plain"
    plain.mkdir()
    app.scan_card.dst.set_path(str(plain))
    app.start_scan()
    pump(app, 0.3)
    status = app.scan_card.status.cget("text")
    assert not app._scanning
    assert "not the root of a Git repository" in status or "No .git" in status
    assert app.state.scan is None


def test_reports_page_and_cancelled_dialog(app, monkeypatch):
    do_scan(app)
    app.show_view(VIEW_REPORTS)
    pump(app)
    from tkinter import filedialog
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: "")
    app.export("csv")
    assert "cancelled" in app.reports.msg.cget("text")
    out = os.path.join(str(app.env.tmp), "gui.csv")
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: out)
    app.export("csv")
    assert os.path.exists(out) and "Saved" in app.reports.msg.cget("text")
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: os.path.join(str(app.env.tmp), "nodir", "x.csv"))
    import tkinter.messagebox as mb
    monkeypatch.setattr(mb, "showerror", lambda *a, **k: None)
    app.export("txt")
    assert "Could not write" in app.reports.msg.cget("text")


def test_same_directory_warning(app):
    app.scan_card.src.set_path(app.env.dst)
    app.scan_card.dst.set_path(app.env.dst)
    pump(app, 0.5)
    assert "same folder" in app.scan_card.src.msg.cget("text")
    assert "same folder" in app.scan_card.dst.msg.cget("text")
