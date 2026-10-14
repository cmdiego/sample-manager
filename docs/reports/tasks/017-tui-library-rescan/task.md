# Task 017 — TUI Library Rescan

- **Status**: Done
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: Continued TUI capability audit requested by the user
- **Scope**: Index filesystem changes from the terminal without blocking navigation or losing the active search.

## 1. [Struct]

- **Primary areas**: `tui/app.py`, `tui/data.py`, keyboard/help discovery.
- **Supporting areas**: Existing `LibraryBrowserService.scan_directory()` and scanner, which own separate database connections in worker threads.
- **Expected changes**: TUI rescan action, state reconciliation, mounted tests, README, task tracker.
- **Ownership**: Scanner owns sample reconciliation; TUI owns navigation and result refresh. No schema changes.

## 2. [Interfaces]

- **User interface**: F5 and command-palette Rescan Library; progress and completion/error feedback.
- **Internal API**: `TuiDataSource.scan_directory()` delegates to the shared service; an asyncio worker runs it through `asyncio.to_thread()`.
- **Persistence**: Existing SQLite index and Stage cascade behavior.
- **Contract**: Preserve query, pane, directory, and focus where possible; recover to the root if the viewed directory disappears; reject duplicate scans.

## 3. [Todo]

- [x] Verify TUI has no scan action.
- [x] Add background rescan and discovery in key help/palette.
- [x] Reconcile browser, indexed search, and Stage after scanning.
- [x] Test responsiveness, repeated scans, pruning, and failures.
- [x] Run validation and prepare a main-targeted PR.

## 4. [Implementation + Revert]

### Implementation Plan

1. Delegate scanning to the existing shared service on a worker thread.
2. Refresh state on the event loop after commit, without re-auditioning samples.
3. Keep progress in the status line and expose completion/errors through notifications.
4. Use mounted Textual tests with a real file-backed SQLite database.

### Revert Plan

1. Revert Task 017 app/data/keybinding/help changes and its tests/README entries.
2. Remove this report and its tracker row. Existing index updates remain compatible.

## 5. [Invariance]

- The SQLite connection created on the main thread never enters the scanning thread.
- Source audio is read only; scanner reconciliation does not move files.
- One scan runs at a time; failure leaves the current view usable.
- Search text and Stage focus survive; removed sample rows disappear from Stage.
- A scan finishing for a previously active root does not switch the current root.

## 6. [Implementation]

### Changed Files

- `src/sample_manager/tui/app.py` — F5/palette action, async scanner worker, progress/results/errors, and state reconciliation.
- `src/sample_manager/tui/data.py` — delegate scan through the existing service's independent SQLite connection.
- `src/sample_manager/tui/keybindings.py`, `tui/widgets/help_screen.py` — expose Rescan in the footer and help.
- `tests/test_tui_rescan.py` — real file-backed SQLite tests for pruning, search refresh, responsiveness, root switches, retries, and deleted folders.
- `README.md` and task tracker — document the new terminal workflow.

### Behavior Implemented

- F5 or Rescan Library in the palette starts one background scan of the active indexed root. The status line retains progress despite audio polling, and notifications report completion or failure.
- Browser focus survives reordered rows when the sample still exists. Active search is rerun with its query preserved; Stage reflects cascaded deletions. Missing viewed folders fall back to the root.
- Navigation remains responsive, duplicate scans are rejected, and finishing a scan of an old root does not switch the user back to it.

### Validation

- `pytest -q tests/test_tui_rescan.py tests/test_tui_navigation.py tests/test_tui_search.py tests/test_tui_settings.py`: 19 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/`: 894 passed, 10 existing deprecation warnings.
- `git diff --check`: passed.

### Follow-ups / Risks

- Add Folder remains a CLI/GUI operation; this task refreshes the active indexed library.
- This branch includes Task 016 and will target main to avoid losing changes through a previously merged base branch.
- Remaining capability gaps: TUI tag/favorite editing, preview volume/looping, result sorting and metadata filters, and search pagination beyond 500 hits.
