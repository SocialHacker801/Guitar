# Guitar — Git Integrity Studio

A premium violet desktop tool (Python + Tkinter) that checks whether the files in a
**source folder (SRC)** are byte-for-byte identical to the **latest committed Git snapshot
(HEAD)** of a **repository folder (DST)**.

Guitar is **strictly read-only**: it never modifies files, stages changes, creates commits or
resets the repository.

## Requirements
* Python 3.9+ (with Tkinter — included in the python.org Windows installer)
* Git installed and on `PATH` (GitPython drives the `git` executable)
* `GitPython`, `pathspec` (see `requirements.txt`)

## Windows PowerShell setup
```powershell
cd path\to\guitar_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
python -m pip install -r requirements.txt
```

## Launch
```powershell
python main.py          # or:  python -m guitar
```

## Run the tests
```powershell
python -m pytest                      # full suite (GUI tests need a display; they self-skip otherwise)
python -m compileall -q guitar tests  # compilation check
```
On headless Linux: `xvfb-run -a python -m pytest`.

## Using Guitar
1. Pick **SRC** (original files) and **DST** (the Git repository root). Each selector is fully
   independent; both accept pasted paths, including long Windows paths (`\\?\` prefix is applied
   internally). A warning appears if both resolve to the same physical folder.
2. Press **Scan** (`F5` / `Ctrl+R`). Scanning runs in a background thread; the UI stays responsive
   and a second scan cannot be started while one runs.
3. Browse the views — they filter the existing results and never rescan:
   * **All Files** – every scanned result.
   * **Matching Files** – files whose content equals Git HEAD exactly (real rows, search, details).
   * **Problems** – mismatches, uncommitted files, files missing from SRC, inspection errors.
   * **Reports** – export CSV / TXT (all files, problems only, or the current view) and see scan notes.
4. Select a row to open **Problem Details**: paths, HEAD baseline, status explanation, sizes,
   SHA-256 hashes, first differing line (text) or byte offset + hex dump (binary), expected-vs-actual
   lines, and a unified diff. Unreadable files show the real exception.
5. Click a summary card to jump to the relevant view. Click table headers to sort.

Shortcuts: `F5`/`Ctrl+R` scan · `Ctrl+F` search · `Ctrl+T` toggle theme · `Esc` clear search.

## Theme system
*Dark Violet* and *Light Lavender* are defined once in `guitar/theme.py` (colour tokens, fonts,
spacing). The sun/moon switch re-skins the live widgets **in place** (panels, sidebar, inputs,
buttons, table, selection, scrollbars, diff viewer, status colours). Nothing is destroyed or
recreated, so SRC/DST paths, results, filters, search text, selection and scroll positions are
preserved. The last theme and folders are remembered in `~/.guitar/settings.json`
(override the folder with the `GUITAR_CONFIG_DIR` environment variable).

## Comparison semantics
| Status | Meaning |
|---|---|
| MATCH | SRC bytes == blob committed in HEAD (line endings and encoding included) |
| MISMATCH | Both exist, bytes differ (first differing line/byte reported) |
| NOT COMMITTED | In SRC, not in the HEAD tree (new, untracked, or only staged) |
| MISSING FROM SOURCE | In the HEAD tree, absent from SRC |
| ERROR | Could not be inspected (permissions, I/O error, directory-vs-file conflict …) |

* Baseline is the **HEAD commit tree** — not the index, not the working tree of DST.
* SRC and DST paths are resolved independently (`SRC/rel` and `DST/rel`).
* Empty, binary (NUL in first 8000 bytes), Unicode-named and nested files are supported.
* A repository with **no commits** reports every SRC file as NOT COMMITTED (with a note).
* Files are compared by streaming 1 MiB chunks, so large files do not need to fit in memory.

## `.gitignore` support — actual limitations
* Only the **root** `.gitignore` is honoured (read from HEAD if committed, else from DST),
  interpreted with `pathspec.GitIgnoreSpec`.
* **Not supported:** nested `.gitignore` files, `.git/info/exclude`, global `core.excludesFile`.
  Guitar therefore does **not** claim full Git-native ignore compatibility.
* Tracked files are never ignored (same as Git). Rules only hide *untracked* SRC files; skipped
  paths are listed on the Reports page and in TXT reports.

## Other known limitations
* Symlinks inside SRC are read as the files they point to (a symlink blob in HEAD is compared with
  the link target only when SRC also has a symlink). Directory symlinks are not followed.
* Submodules are ignored. Bare repositories are rejected. DST must be the repository **root**.
* Case-insensitive file systems: paths are matched exactly as stored in Git; a case-only rename
  appears as MISSING + NOT COMMITTED. macOS NFD/NFC normalisation differences are not reconciled.
* The inspector shows at most 8 MiB per side and diffs a 4000-line window of very large files;
  hashes and first-difference data are still computed for the entire file.
* CSV cells starting with `= + - @` are prefixed with `'` to prevent spreadsheet formula injection.

## Project layout
```
main.py                  entry point
guitar/
  theme.py               design system (tokens, fonts, spacing)
  models.py state.py     data models and GUI-independent application state
  git_backend.py         read-only GitPython wrapper (HEAD tree + blob streams)
  ignore_rules.py        root .gitignore filtering (limitations documented)
  scanner.py             scan + streaming comparison engine
  details.py             Problem Details / diff generation
  reports.py             CSV / TXT export (atomic writes)
  settings.py paths.py   persistence, long-path helpers
  gui/                   app window, widgets, icons, results table, inspector, panels
tests/                   pytest suite (engine, state, details, reports, real Tk GUI tests)
LICENSE                  MIT license
```

## Contributing
**Contributions are welcome!** Bug reports, feature ideas, documentation fixes and pull
requests are all appreciated.

1. Fork the repository and create a feature branch (`git checkout -b feature/my-change`).
2. Set up the environment as described in *Windows PowerShell setup* above.
3. Keep Guitar **read-only** with respect to user files and repositories — changes must never
   write to SRC or DST, stage, commit or reset.
4. Add or update tests for your change and make sure the whole suite passes
   (`python -m pytest`, plus `python -m compileall -q guitar tests`).
5. Keep colours, fonts and spacing in `guitar/theme.py` rather than hardcoding them in widgets.
6. Open a pull request describing what changed and why. For larger changes, please open an
   issue first to discuss the approach.

When reporting a bug, include your OS, Python and Git versions, and the steps to reproduce.

## License
Released under the **MIT License** — see the [LICENSE](LICENSE) file for details.
