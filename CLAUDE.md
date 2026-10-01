# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

## Commands

```bash
# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_tag_service.py -v

# Run a single test
pytest tests/test_search.py::test_search_by_name -v

# Run the CLI
sampleman --help
sampleman init

# Launch the frontends
sampleman          # bare command → launches the Qt desktop GUI (default)
sampleman gui      # explicit — same as bare `sampleman`
sampleman tui      # legacy Textual terminal UI (fallback)

# Run the GUI (Qt) test suite (offscreen so it needs no display)
QT_QPA_PLATFORM=offscreen pytest tests/gui/ -v
```

`python -m sample_manager` also launches the Qt GUI (`__main__.py` →
`gui.app.run_gui`). Textual is still installed; it is removed only after
cross-platform Qt packaging is validated on macOS, Windows, and Linux.

## Architecture

The package lives in `src/sample_manager/` (src layout). The `sampleman` CLI entry point is `cli.py:app`. Running `sampleman` with no subcommand (and `python -m sample_manager`) launches the Qt desktop GUI.

**Layered structure:**

- `cli.py` — Typer app. Defines `_get_db()` (loads config → opens SQLite → runs migrations), then delegates to repos/services. The no-subcommand callback launches the Qt GUI; `gui` and `tui` subcommands launch the Qt GUI and the legacy Textual UI explicitly. Arrangement and selection commands are registered from `commands/arrangement_commands.py` to keep cli.py from growing too large.
- `gui/` — PySide6 Qt desktop frontend. `app.py:run_gui()` opens the DB via the shared `cli._get_db()`, builds a `LibraryBrowserService` + `BrowserController` + `MainWindow`, and enters the Qt event loop. Widgets are presentation-only (no SQL, no `Db`); background work uses `QRunnable` workers. Imports pull in no numpy/sounddevice (audio deps are lazy).
- `services/` — framework-neutral frontend services shared by the GUI and TUI: `navigation.py` (`NavState`, `build_items`) and `library_browser.py` (`LibraryBrowserService` + DTOs). No UI-framework imports.
- `tui/` — legacy Textual terminal frontend (`tui.app:SampleManagerApp`), retained as a fallback via `sampleman tui`.
- `repos/` — One repository class per table/domain. All raw SQL lives here. Repos take a `Db` instance and return `sqlite3.Row` dicts.
- Service layer — business logic on top of repos:
  - `tag_service.py` — tag/untag/bulk ops
  - `tag_graph.py` — `TagGraphService` uses recursive CTEs to traverse the tag DAG for descendant expansion
  - `search.py` — `SearchEngine` builds parameterized SQL; resolves tags via `TagAliasRepo` then expands descendants via `TagGraphService` before filtering
  - `arrangement_service.py` — builds deterministic export plans (template rendering, collision handling)
  - `export_service.py` — executes plans (copy/symlink/move)
- `db.py` — `Db` class: thin sqlite3 wrapper with `execute/fetchone/fetchall/fetchval` helpers and a `transaction()` context manager (`BEGIN IMMEDIATE`). PRAGMAs (WAL mode, foreign keys) applied on every connection.
- `migrations.py` — sequential migrations (currently 4). Applied automatically via `apply_migrations(db)` called from `_get_db()` on every command invocation.
- `config.py` — YAML config management. Config at `~/.sample_manager/config.yaml`. **Never auto-mutated** — only modified by explicit `sampleman config *` commands.
- `profiles.py` — loads arrangement and export profiles from YAML files in `~/.sample_manager/profiles/`.
- `normalize.py` — path and text normalization shared across modules.
- `scanner.py` — walks a library root directory and upserts audio file metadata into the `sample` table.

**Data model key points:**
- A sample is identified by `(library_root_id, rel_path_norm)`.
- Tags are soft-deleted (`is_hidden=1`); resolved by name, shorthand, or alias (all case-insensitive via `*_norm` columns).
- Tag search expands recursively to all descendants.
- `selection_sample` is a persistent working buffer of sample IDs (no user-facing ID).
- `export_run` + `history_entry` record every export attempt for revert support.

**Exit codes** (defined in `exit_codes.py`): 0 success, 1 general, 2 invalid args, 3 safety refusal, 4 constraint violation, 5 partial operation, 6 config validation.

## Test Fixtures

`tests/conftest.py` provides shared fixtures:
- `db` — in-memory SQLite with all migrations applied
- `tmp_home` / `tmp_config_dir` — isolated home dir via `monkeypatch.setenv("HOME", ...)`
- `cli_runner` — Typer `CliRunner` for end-to-end CLI tests

CLI tests that need config must monkeypatch `HOME` (via `tmp_home`) so they don't touch `~/.sample_manager`.

## User Files

- Config: `~/.sample_manager/config.yaml`
- Database: `~/.sample_manager/sample_manager.sqlite3`
- Profiles: `~/.sample_manager/profiles/`

## Docs

`docs/` contains the original design specs; `docs/appendix-phase2-ddl-and-ctes.md` has the canonical DDL and recursive CTE patterns that migrations and `tag_graph.py` are derived from.
