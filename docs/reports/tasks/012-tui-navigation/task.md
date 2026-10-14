# Task 012 — TUI Navigation and Stage Focus

- **Status**: Done
- **Created**: 2026-10-13
- **Owner**: Codex
- **Origin**: user request to continue toward a stable personal tool
- **Scope**: Make TUI Tab navigation real, support switching indexed roots, and keep large directory browsing responsive.

## 1. [Struct]

- **Primary area**: `src/sample_manager/tui/app.py` and the selected-file widget.
- **Supporting areas**: `src/sample_manager/tui/keybindings.py`, `src/sample_manager/tui/data.py`, `src/sample_manager/services/navigation.py`, and TUI tests.
- **Current ownership boundaries**: `NavState` owns browser directory and cursor; the TUI app owns keyboard routing; the selection widget renders Stage rows; the data adapter resolves indexed sample details and paths.
- **Files expected to change**: TUI app/widgets/keybindings/data, navigation helper, tests, README, and this report/tracker.
- **Files expected to remain untouched**: scanner, database schema, GUI widgets, audio backend, and export code.

## 2. [Interfaces]

- **User-facing interface**: Tab cycles Browser and Stage; j/k moves inside the active pane; Return/d remove a Stage sample; r cycles indexed roots; help/status identify these controls.
- **Internal API/interface**: the app tracks active pane and Stage cursor, while `TuiDataSource` supplies the path for a selected sample; `build_items` can form indexed keys from the known root in constant time.
- **Persistence/config interface**: selection remains in the existing selection table; the configured default root determines TUI startup when indexed.
- **Events/signals/commands**: raw Textual key events route through `KEYMAP`; no schema change.
- **Tests as interface contracts**: TUI keyboard/widget tests and full pytest suite.

## 3. [Todo]

- [x] Inspect TUI keyboard, selection rendering, and root state.
- [x] Implement active Browser/Stage focus and useful Stage actions.
- [x] Honor default root, add a root-cycle key, and handle missing roots cleanly.
- [x] Remove directory indexing's repeated full-map lookup.
- [x] Add focused tests and run the complete suite.
- [x] Finalize report/tracker and push a PR.

## 4. [Implementation + Revert]

### Implementation Plan

1. Track the active pane and Stage cursor in the TUI; render a visible cursor and route movement/removal to its selected sample ID.
2. Load all indexed roots and select the configured default when available; use `r` to cycle roots while preserving the persistent Stage.
3. Pass the known root into directory item construction so indexed sample lookup is direct; test duplicate filenames in distinct directories.
4. Update help/status text and validate interactions.

### Revert Plan

1. Restore TUI key routing and selected-list rendering before Task 012.
2. Remove direct-root lookup arguments and new TUI tests.
3. Restore README/tracker content and delete this report; no data migration is needed.

## 5. [Invariance]

- Browser directory history and cursor survive switching to Stage and back.
- Stage remains persistent across library roots; removal is by sample ID.
- A filter query cannot accidentally consume Tab or transport keys.
- GUI browsing and the existing `build_items` callers still resolve indexed samples correctly.

## 6. [Implementation]

### Changed Files

- `src/sample_manager/tui/app.py`, `src/sample_manager/tui/data.py`, `src/sample_manager/tui/keybindings.py` — active pane and Stage cursor, root cycling/default selection, selected sample path, and accurate key routing/status.
- `src/sample_manager/tui/widgets/selection_list.py`, `src/sample_manager/tui/widgets/file_tree.py`, `src/sample_manager/tui/styles/app.tcss`, `src/sample_manager/tui/widgets/help_screen.py` — cursor rendering, active pane border, literal bracketed filenames, and updated help. The file list no longer reuses an empty-state widget ID during asynchronous removal.
- `src/sample_manager/services/navigation.py`, `src/sample_manager/services/library_browser.py` — direct indexed path lookup from a known root and graceful empty listings for removed folders.
- `tests/test_tui_navigation.py` — mounted Textual pilot plus root/default, duplicate-name, missing-folder, and filename-rendering checks.
- `README.md`, `docs/reports/tasks/README.md` — workflow and tracker updates.

### Behavior Implemented

Tab cycles Browser and Stage; Stage shows a cursor and supports arrows, `d`, and Return for removal. Browser history survives pane switches. `r` cycles available indexed roots, and startup honors the configured default. Directory listing now computes normalized relative paths directly from the current root, avoiding repeated full-index scans for each file. A mounted pilot exposed a `DuplicateIds` crash during rapid empty-state refreshes; the placeholder no longer uses a colliding widget ID.

### Validation

- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`: 876 passed, 10 Qt/audioread deprecation warnings.
- `git diff --check`: passed.

### Follow-ups / Risks

- TUI typeahead remains current-folder scoped; full-root search is provided by the GUI.
- TUI root cycling is session-only; the GUI picker writes the configured default.
