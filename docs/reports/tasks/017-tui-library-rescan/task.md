# Task 017 — TUI Library Rescan

- **Status**: In Progress
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
- [ ] Add background rescan and discovery in key help/palette.
- [ ] Reconcile browser, indexed search, and Stage after scanning.
- [ ] Test responsiveness, repeated scans, pruning, and failures.
- [ ] Run validation and open a main-targeted PR.

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

- Pending.

### Behavior Implemented

- Pending.

### Validation

- Pending.

### Follow-ups / Risks

- Add Folder remains a CLI/GUI operation; this task refreshes the active indexed library.
- This branch includes Task 016 and will target main to avoid losing changes through a previously merged base branch.
