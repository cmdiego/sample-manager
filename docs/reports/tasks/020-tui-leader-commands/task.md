# Task 020 — TUI Leader Command Panel

- **Status**: In Progress
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
- [ ] Add command metadata, context bindings and shared dispatch.
- [ ] Implement grouped leader popup and visible entry hints.
- [ ] Test execution, cancellation, search, first run, waveform and modal isolation.
- [ ] Inspect terminal layout at 80×24 and run the full suite.
- [ ] Finalize documentation, incremental commits and PR.

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

- Pending implementation.

### Behavior Implemented

- Planning complete; no implementation yet.

### Validation

- Pending focused pilots, terminal layout inspection and full pytest suite.

### Follow-ups / Risks

- Textual priority bindings and modal bubbling need mounted tests to prevent duplicate actions or hidden-browser changes.
