# Task 020 — TUI Leader Command Panel

- **Status**: Done
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: User request for discoverable commands through a leader key
- **Scope**: Add a persistent, grouped command popup with executable key hints and complete shortcut documentation.

## 1. [Struct]

- **Primary areas**: `tui/keybindings.py`, `tui/app.py`, new `tui/widgets/commands_screen.py`.
- **Supporting areas**: Existing Help screen, Textual pilot tests, README.
- **Ownership**: Keybinding metadata owns command descriptions and groups; the modal presents commands; the app dispatches actions against current UI state.
- **Expected changes**: TUI presentation/routing and tests. Audio services, repositories, schema and GUI remain untouched.

## 2. [Interfaces]

- **User-facing**: Backslash leader and F1 open a grouped command panel; letters, arrows, Enter and mouse choose actions; Escape returns/closes. No timeout.
- **Internal**: A shared action dispatcher serves normal bindings and leader actions. Waveform bindings become explicit metadata so Help cannot silently omit them.
- **Persistence/config**: None.
- **Events**: Modal returns an action name; the app validates availability and executes it after dismissal.
- **Contracts**: All app actions discoverable; unavailable actions explain why; menu keystrokes never leak into Browser/search; existing modal text entry owns its keys.

## 3. [Todo]

- [x] Inspect existing routing, Help and mounted tests.
- [x] Add command metadata, context bindings and shared dispatch.
- [x] Implement grouped leader popup and visible entry hints.
- [x] Test execution, cancellation, search, first run, waveform and modal isolation.
- [x] Inspect terminal layout at 80×24 and run the full suite.
- [x] Finalize documentation and incremental commits for PR publication.

## 4. [Implementation + Revert]

### Implementation Plan

1. Define grouped leader entries and waveform key metadata alongside existing bindings.
2. Build an OptionList modal with mnemonic selection, breadcrumbs, direct shortcut hints and unavailable reasons.
3. Route popup and direct commands through one dispatcher, preserving search/Stage state on dismissal.
4. Add mounted workflow tests, update README, validate and open a PR against main.

### Revert Plan

1. Revert the Task 020 implementation commits on `codex/tui-leader-commands`.
2. Remove `commands_screen.py` and its pilot tests; restore app/keybinding/help/README changes from the parent commit.
3. No data migration or configuration rollback is required.

## 5. [Invariance]

- Space/Ctrl+Space retain transport behavior; search typing and pasted queries work.
- Existing dialogs keep their input and never trigger commands behind them.
- Browser, Stage, settings, library indexing and tags use their existing services.
- Canceling the panel preserves search query, focused item, selection and waveform cursor.
- First-run access to setup, Help and Quit remains available.

## 6. [Implementation]

### Changed Files

- `tui/keybindings.py` — complete command groups, shared shortcut formatting and explicit waveform context bindings.
- `tui/widgets/commands_screen.py` — grouped leader modal with keyboard/mouse actions, live prerequisite checks and persistent instructions.
- `tui/app.py` — backslash/F1 entry, availability explanations, shared command dispatcher and visible hints.
- `tui/widgets/help_screen.py` — shared shortcut metadata including previously missing waveform controls.
- `tests/test_tui_commands.py` — nine mounted/metadata regressions covering discovery, execution, cancellation, modes and first run.
- `README.md` — leader sequences and text-entry behavior.

### Behavior Implemented

- Backslash or F1 opens all seven command groups without a timeout. Letter mnemonics, arrows/Return and mouse selection share the same execution path.
- Unavailable actions remain visible with reasons; activation checks current state before dismissal and again before dispatch.
- Escape/Backspace returns to groups, then closes. Backslash/F1 closes immediately. Search text, Stage focus and waveform cursor survive cancellation.
- Normal dialogs retain literal backslash input. Search reserves the leader; pasted queries may contain literal backslashes.
- Waveform shortcuts now appear in Help and use the same table as event routing.
- Backslash/F1 switches from full Help to the command popup without stacking help views; Escape returns to the original Browser/search state.

### Validation

- `.venv/bin/python -m pytest -q tests/test_tui_commands.py`: 9 passed.
- Existing keybinding/help/navigation pilot subset: 32 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/`: 913 passed, 10 existing deprecation warnings; repeated after the Help transition fix with the same result.
- `git diff --check`: passed.
- Exported and inspected root/waveform popup screenshots at 80×24; dialog is 76×22, with scrollable entries and fixed instructions. Temporary screenshots are outside the repository.

### Follow-ups / Risks

- Initial cancellation test failures were caused by issuing keys before deferred app initialization finished; mounted tests now wait for initial refresh before exercising workflows.
- No known blockers. Implemented on `codex/tui-leader-commands` for a PR against `main`.
