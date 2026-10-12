from guitar.ignore_rules import IgnoreRules


def test_patterns():
    r = IgnoreRules.from_text("*.log\nbuild/\n!keep.log\n/root_only.txt\n", "t")
    assert r.is_ignored("a.log") and r.is_ignored("sub/a.log")
    assert not r.is_ignored("keep.log")
    assert r.is_ignored("build/x.o") and r.is_ignored("build", is_dir=True)
    assert r.is_ignored("root_only.txt") and not r.is_ignored("sub/root_only.txt")
    assert not r.is_ignored("src/main.py")


def test_git_dir_always_ignored_and_empty_rules():
    r = IgnoreRules.from_text(None)
    assert not r.active and r.is_ignored(".git/config") and not r.is_ignored("a.txt")


def test_comments_and_blank_lines():
    r = IgnoreRules.from_text("# comment\n\n*.tmp\n")
    assert r.is_ignored("x.tmp") and not r.is_ignored("# comment")


def test_nested_gitignore_is_documented_unsupported(env):
    """Nested .gitignore files are NOT honoured (documented limitation)."""
    from conftest import write
    from guitar.scanner import scan
    write(env.dst, "sub/.gitignore", "*.tmp\n")
    write(env.src, "sub/a.tmp", "x")
    res = scan(env.src, env.dst)
    assert "sub/a.tmp" in {r.rel_path for r in res.results}
