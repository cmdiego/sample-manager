# Task 013 — GUI First-Run Setup

- **Status**: Done
- **Created**: 2026-10-13
- **Owner**: Codex
- **Origin**: user request to continue toward a stable personal tool
- **Scope**: Let the GUI start from a fresh install and guide users to add their first sample folder.

## 1. [Struct]

- **Primary area**: `src/sample_manager/gui/app.py` startup path and `src/sample_manager/gui/main_window.py` empty state.
- **Supporting areas**: `src/sample_manager/config.py`, `src/sample_manager/profiles.py`, and GUI tests.
- **Current ownership boundaries**: config owns default paths and initialization; profiles creates starter files; the GUI entry point opens the DB and creates the window; the window presents library controls.
- **Files expected to change**: GUI app/window, tests, README, and task documentation.
- **Files expected to remain untouched**: CLI command behavior, scanner, database schema, audio, and arrangement/export logic.

## 2. [Interfaces]

- **User-facing interface**: launching `sampleman`/`sampleman gui` works without a prior `sampleman init`; an empty GUI points to Add Folder.
- **Internal API/interface**: startup calls existing idempotent config/profile setup before `_get_db`.
- **Persistence/config interface**: create default config and example profile files only when absent; preserve existing user files.
- **Events/signals/commands**: no new keyboard shortcut or schema.
- **Tests as interface contracts**: isolated-home startup tests, empty-window assertions, and full pytest suite.

## 3. [Todo]

- [x] Inspect current GUI entry and CLI initialization behavior.
- [x] Initialize missing config/profile files at GUI startup.
- [x] Show a clear first-library action in an empty window.
- [x] Add isolated tests that protect existing config content.
- [x] Run the suite, document results, and open a PR.

## 4. [Implementation + Revert]

### Implementation Plan

1. Reuse `ensure_config_exists`, `get_profiles_dir`, and `create_example_profiles` in the GUI entry point before opening the database.
2. Present a first-run status message when the root picker has no indexed folders.
3. Test fresh and existing config paths without reading or writing the developer's home directory.

### Revert Plan

1. Remove the startup setup call and empty-library message from GUI code.
2. Remove Task 013 tests and restore README/tracker entries.
3. Delete this report; no database migration or data rollback is required.

## 5. [Invariance]

- Existing config and profile files are not overwritten.
- GUI simulation-temp stays isolated and never creates user config.
- CLI commands other than GUI preserve their current explicit setup behavior.
- After setup, GUI still opens through the shared `_get_db` migration path.

## 6. [Implementation]

### Changed Files

- `src/sample_manager/gui/app.py` — call idempotent config/profile setup before the shared DB opener, after the temporary-simulation early return.
- `src/sample_manager/gui/main_window.py` — explain Add Folder in an empty indexed-library state.
- `tests/gui/test_first_run.py` — use isolated config paths to verify fresh setup, file preservation, empty-window guidance, and simulation isolation.
- `README.md`, `docs/reports/tasks/README.md` — document first launch and task status.

### Behavior Implemented

The GUI can now open without `sampleman init`. It creates the default config and starter profile files, migrates the database through the existing `_get_db` path, and presents Add Folder when there are no indexed roots. Reopening preserves existing config and profiles. `--simulation-temp` returns before setup and stays isolated.

### Validation

- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/gui/test_first_run.py`: 3 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`: 874 passed, 10 Qt/audioread deprecation warnings.
- `git diff --check`: passed.

### Follow-ups / Risks

- A folder must still be chosen before the empty GUI can search or preview samples.
