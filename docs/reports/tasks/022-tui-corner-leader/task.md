# Task 022 — Corner Leader Hints

- **Status**: Done
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: User correction with a Neovim-style command hint reference
- **Scope**: Replace the large centered leader menu presentation with compact next-key hints in the lower-right corner.

## 1. [Struct]

- **Primary area**: `tui/widgets/commands_screen.py`.
- **Supporting areas**: Keybinding labels, mounted command tests, README.
- **Ownership**: Existing command tree and dispatcher retain execution; the popup owns presentation and sequence navigation.
- **Expected changes**: Leader presentation and tests; no persistence or audio changes.

## 2. [Interfaces]

- **User-facing**: Backslash shows compact next-key hints at the lower right, with no screen dimming. Entering a group updates the hints and prefix. `?` remains full Help.
- **Internal**: Existing CommandsScreen callback returns the selected action.
- **Persistence/config**: None.
- **Events**: Existing letters/arrows/Return, Escape/Backspace, mouse selection; outside click closes the popup.
- **Contracts**: Browser stays visible, keyboard sequences execute once, cancellation preserves focus/search.

## 3. [Todo]

- [x] Inspect existing leader implementation and user reference.
- [x] Add compact labels, next-key rows, right/bottom anchoring and transparent overlay.
- [x] Verify size, prefix navigation, outside dismissal and existing execution behavior.
- [x] Inspect rendered terminal layouts, run full suite and prepare committed changes for PR publication.

## 4. [Implementation + Revert]

### Implementation Plan

1. Reuse command routing while replacing the centered dialog with a content-sized corner popup.
2. Show one line per next key, with the active prefix in the border title and contextual prerequisites below.
3. Add geometry/input regressions and inspect terminal screenshots before publication.

### Revert Plan

1. Revert Task 022 popup/label changes and its tests/README updates.
2. Restore the centered CommandsScreen from the branch parent; no data rollback is required.

## 5. [Invariance]

- Full shortcut Help remains available through `?`.
- Leader command sequences, availability checks and direct shortcuts retain their meanings.
- Search, Stage focus and dialog text ownership survive cancellation.
- Keep all commands discoverable and long groups scrollable on small terminals.

## 6. [Implementation]

### Changed Files

- `tui/widgets/commands_screen.py` — transparent, content-sized lower-right popup, next-key rows and prefix border title; contextual status and outside-click dismissal.
- `tests/test_tui_commands.py` — corner geometry/transparency, prefix, outside click and small-terminal scrolling; retained existing execution/input regressions.
- `README.md` — corner hint behavior.

### Behavior Implemented

- Leader/F1 shows one row per continuation; group names use a `+` marker, letters and arrows execute the existing command tree, and active sequences update the border title.
- Underlying Browser stays visible without dimming. Prerequisite explanations appear only for highlighted/unavailable actions. Full Help remains a separate `?` action.
- Escape/Backspace navigates back, leader/F1 closes, and outside clicks dismiss without reaching Browser.

### Validation

- Command tests: 12 passed.
- Full suite before integrating the preceding waveform fix: 916 passed, 10 existing deprecation warnings.
- Inspected root/group screenshots at 80×24. Root popup is 56×10 at coordinates (23,12), above the footer; smaller groups shrink with their content.
- Geometry tested at 80×24 and 120×40; all hints remain reachable by scrolling at 40×12.
- Full combined suite after integrating the preceding waveform fix: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/` — 921 passed, 10 existing deprecation warnings.
- `git diff --check origin/main...HEAD`: passed.

### Follow-ups / Risks

- Includes the preceding waveform-fix commits from PR #13 so the local branch retains both improvements. PR targets main; merging #13 first reduces its diff to the leader-popup work.
- Integration required resolving only adjacent task tracker rows; both reports are retained. No known blockers.
