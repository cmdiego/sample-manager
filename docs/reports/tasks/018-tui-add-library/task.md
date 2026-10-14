# Task 018 — Add Libraries from the TUI

- **Status**: Done
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: User request to continue improving the TUI
- **Scope**: Add and index a sample folder from the terminal, including on a fresh install.

## 1. [Struct]

- **Primary areas**: `tui/app.py`, new add-library modal, keybindings/help.
- **Supporting areas**: Existing config/profile setup and background library scanner.
- **Ownership**: Config helpers persist roots; scanner owns indexing; the TUI validates user intent and updates navigation after completion.
- **Expected changes**: TUI app/modal/help, isolated onboarding tests, README and tracker. No schema changes.

## 2. [Interfaces]

- **User interface**: F4 / Add Folder in the command palette; paste/type a path; Add & Scan or Cancel.
- **Configuration**: Initialize missing config/database/profile files only after a valid folder is submitted. Persist the successfully indexed folder as the default root.
- **Worker interface**: Reuse the independent-connection scanner from F5.
- **Contract**: Invalid input and cancellation leave current configuration intact; existing Stage entries survive; scans do not block navigation.

## 3. [Todo]

- [x] Verify PRs #8 and #9 are present on main.
- [x] Implement path modal and discoverable Add Folder action.
- [x] Support first-run setup and persist successful root selection.
- [x] Test invalid paths, cancellation, nested search, root cycling, and reopening.
- [x] Validate and prepare a main-targeted PR with incremental commits.

## 4. [Implementation + Revert]

### Implementation Plan

1. Add a bounded modal with a path Input, inline validation and explicit Add & Scan.
2. Initialize missing storage through existing helpers, then run the existing scanner in the background.
3. Refresh roots and select the new library only after success; keep Stage persistent.
4. Exercise real Textual input against temporary configuration and file-backed SQLite.

### Revert Plan

1. Revert Task 018 TUI app, modal, bindings/help, tests and README changes.
2. Remove this report/tracker row. Config and indexed samples remain compatible with previous versions.

## 5. [Invariance]

- Existing configuration and profile contents are preserved.
- Source audio is never moved or changed.
- Escape/Cancel do not initialize config or add a root.
- F5 rescan retains its existing focus/search preservation.
- One scan runs at a time and errors leave the current library available.

## 6. [Implementation]

### Changed Files

- `tui/widgets/add_library_screen.py` — path input, quoted/expanded path validation, Enter/Add & Scan, and cancellation.
- `tui/app.py` — F4/palette discovery, deferred config/profile/DB setup, shared scan worker, root activation and preference persistence.
- `config.py` — allow the existing idempotent setup helper to receive an explicit configuration path.
- TUI bindings/help and README — document first-run onboarding and Add Folder.
- `tests/test_tui_add_library.py` — mounted first-run, reopening, invalid/cancel, duplicate-root, Stage-preservation, and scan-failure cases.

### Behavior Implemented

- F4 and Add Folder in the palette work before configuration exists. Valid submission initializes missing storage, scans without blocking, selects the resulting library, and saves it as the next startup root.
- Repeated additions rescan the same root without duplication. Existing Stage entries survive. Failed scans leave the previous root active and do not register the unsuccessful folder in config.

### Validation

- `pytest -q tests/test_tui_add_library.py tests/test_tui_rescan.py`: 6 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/`: 897 passed, 10 existing deprecation warnings.
- `git diff --check`: passed.

### Follow-ups / Risks

- Next workflow gap: tagging a focused sample without leaving the TUI.
