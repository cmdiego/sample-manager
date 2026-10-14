# Task 011 — GUI Library Management

- **Status**: Done
- **Created**: 2026-10-13
- **Owner**: Codex
- **Origin**: user request to continue improving Sample Manager after PR #2
- **Scope**: Make indexed library roots selectable and let the GUI add or rescan folders without freezing browsing.

## 1. [Struct]

- **Primary area**: `src/sample_manager/gui/main_window.py` and its application wiring.
- **Supporting areas**: `src/sample_manager/services/library_browser.py`, `src/sample_manager/scanner.py`, `src/sample_manager/db.py`, and GUI tests.
- **Current ownership boundaries**: the scanner owns filesystem indexing; the service exposes database-backed roots; the controller owns the active root and browser model; the window owns user controls and background-job feedback.
- **Files expected to change**: GUI window/application/worker code, small database or service interface for a worker connection, GUI tests, README, and this report/tracker.
- **Files expected to remain untouched**: audio engine, arrangement/export schemas, and sample metadata migrations.

## 2. [Interfaces]

- **User-facing interface**: toolbar library picker, Add Folder, and Rescan actions with progress and result feedback.
- **Internal API/interface**: a background worker opens its own SQLite connection, calls `scan_library`, then returns the scan summary to the GUI thread; the controller reloads the selected root.
- **Persistence/config interface**: scanner registers roots and samples in the existing database. The normal GUI records newly added folders in user config; isolated tests can omit this callback.
- **Events/signals/commands**: root picker changes call `BrowserController.load_root`; scan controls disable while a job runs; worker completion refreshes roots and browser state.
- **Tests as interface contracts**: offscreen Qt tests for root switching, successful/failed scans, and responsive controls, plus full pytest suite.

## 3. [Todo]

- [x] Inspect existing root, scan, GUI, and TUI pathways.
- [x] Add a visible root picker and make switching preserve a valid browser state.
- [x] Add nonblocking Add Folder and Rescan operations with truthful status.
- [x] Preserve GUI-added folders in user config without touching test config.
- [x] Add interaction tests and probe the JSON GUI shell.
- [x] Run full validation and update this report and tracker.

## 4. [Implementation + Revert]

### Implementation Plan

1. Expose the database path to scan jobs and run each scan with a separate SQLite connection on a Qt worker.
2. Add a toolbar root picker and scan actions; refresh root choices and browser contents after completion, while reporting errors without switching roots.
3. Wire config persistence only in the real GUI entry point, cover the workflow with offscreen tests, and document the controls.

### Revert Plan

1. Remove Task 011 toolbar, scan callbacks, and worker wiring from GUI files.
2. Remove the scanner connection interface and Task 011 tests.
3. Restore README and tracker content and delete this report; no schema or sample-data migration is required.

## 5. [Invariance]

- Switching roots never displays files outside the selected root.
- Scans use existing sample identity and selection rules, and they do not block the Qt event loop.
- A failed scan leaves the active root, search, and selection usable.
- Tests never write the developer's real configuration or library.

## 6. [Implementation]

### Changed Files

- `src/sample_manager/db.py`, `src/sample_manager/services/library_browser.py` — expose a connection target and open an independent scanner connection for Qt worker jobs.
- `src/sample_manager/gui/main_window.py`, `src/sample_manager/gui/controller.py`, `src/sample_manager/gui/app.py` — add toolbar controls, startup default, background scan, result/error feedback, and browser/Stage refresh.
- `src/sample_manager/gui/simulation.py`, `tests/gui/scenarios/search-escape-from-field.json` — route JSON keyboard input to the focused child, matching real search behavior.
- `tests/gui/test_library_management.py` — cover adding, rescanning, switching, startup default, missing roots, errors, and config persistence.
- `README.md`, `docs/reports/tasks/README.md` — document the new controls and task status.

### Behavior Implemented

The GUI presents every indexed library root in a toolbar. Add Folder scans a new root and selects it. Rescan reconciles the current root, including `.wave` files and removed files. Scans run in a Qt worker using a separate SQLite connection, leaving the browser responsive. The selected root is recorded as the configured default in the real GUI entry point; simulation and tests do not touch user config. A missing root cannot leave the picker pointing at a different root than the browser.

### Validation

- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`: 871 passed, 10 Qt/audioread deprecation warnings.
- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/gui/test_library_management.py tests/gui/test_json_scenarios.py`: covered by the full suite.
- `sampleman --simulation-temp` search/Escape JSON smoke: passed after correcting focused-key delivery.
- `git diff --check`: passed.

### Follow-ups / Risks

- Initial app setup still needs `sampleman init` because `_get_db()` requires config. Add Folder covers library indexing after that setup.
- Additional TUI navigation improvements remain outside this GUI-focused task.
