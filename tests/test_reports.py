import csv
import os

import pytest

from guitar.reports import CSV_COLUMNS, ReportError, export_csv, export_txt
from guitar.scanner import scan


def test_csv_report(env, tmp_path):
    res = scan(env.src, env.dst)
    out = tmp_path / "r.csv"
    n = export_csv(res.results, str(out))
    assert n == len(res.results)
    with open(out, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys()) == CSV_COLUMNS
    d = {r["relative_path"]: r for r in rows}
    assert d["diff.txt"]["status"] == "MISMATCH" and d["diff.txt"]["first_diff_line"] == "2"
    assert d["bin/data.bin"]["first_diff_byte"] == "300" and d["bin/data.bin"]["content_type"] == "binary"
    assert d["gone.txt"]["status"] == "MISSING FROM SOURCE" and d["gone.txt"]["head_sha256"]
    assert d["same.txt"]["source_path"].endswith("same.txt") and d["same.txt"]["destination_path"].endswith("same.txt")
    assert d["unic\u00f6de/na\u00efve \u6587\u4ef6.txt"]["status"] == "MATCH"


def test_txt_report(env, tmp_path):
    res = scan(env.src, env.dst)
    out = tmp_path / "r.txt"
    export_txt(res, [r for r in res.results if r.status.is_problem], str(out), "Problems only")
    t = out.read_text(encoding="utf-8")
    assert "Git Integrity Report" in t and "[MISMATCH] diff.txt" in t
    assert "First differing line : 2" in t and "SKIPPED BY .gitignore" in t and "[IGNORED] debug.log" in t
    assert "MATCHING FILES" not in t                        # scope was problems only


def test_export_error_is_clean(env, tmp_path):
    res = scan(env.src, env.dst)
    bad = tmp_path / "no-such-dir" / "r.csv"
    with pytest.raises(ReportError):
        export_csv(res.results, str(bad))
    with pytest.raises(ReportError):
        export_txt(res, res.results, str(bad))


def test_csv_formula_injection_neutralised(env, tmp_path):
    res = scan(env.src, env.dst)
    res.results[0].rel_path = "=HYPERLINK(\"x\")"
    out = tmp_path / "i.csv"
    export_csv(res.results[:1], str(out))
    with open(out, newline="", encoding="utf-8-sig") as fh:
        assert next(csv.DictReader(fh))["relative_path"].startswith("'=")


def test_no_temp_files_left_behind(env, tmp_path):
    res = scan(env.src, env.dst)
    export_csv(res.results, str(tmp_path / "ok.csv"))
    assert [p for p in os.listdir(tmp_path) if p.endswith(".tmp")] == []
