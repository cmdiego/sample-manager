# Task 022 — Corner Leader Hints

- **Status**: In Progress
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
- [ ] Add compact labels, next-key rows, right/bottom anchoring and transparent overlay.
- [ ] Verify size, prefix navigation, outside dismissal and existing execution behavior.
- [ ] Inspect rendered terminal layouts, run full suite, commit and publish PR.

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

- Pending implementation.

### Behavior Implemented

- Pending implementation.

### Validation

- Pending mounted tests, screenshot inspection and full suite.

### Follow-ups / Risks

- The previous waveform PR is still open; this branch starts at merged main so the presentation fix can be reviewed independently.
