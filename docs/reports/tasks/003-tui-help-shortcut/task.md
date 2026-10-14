# Task 003 — TUI Help Shortcut

- **Status**: ✅ Fixed
- **Origin**: TUI issue #3 (user request during manual testing)
- **Assigned agent**: tui-architect
- **Created**: 2026-07-07
- **Plan**: N/A (single focused feature — see prompt.md)

## Problem / Objective
Add a help shortcut in the TUI that shows the available commands/keybindings and how to use the
TUI. The `?` key is already intended for this but is currently dead.

## Root Cause
`src/sample_manager/tui/keybindings.py` `KEYMAP` maps `"?" → "show_help"` (line 25), but
`src/sample_manager/tui/app.py:on_key` (lines 231–257) has **no `elif action == "show_help"`
branch** and there is no help screen. So pressing `?` does nothing.

## Files Involved
- `src/sample_manager/tui/app.py` — add `show_help` dispatch + push help screen
- new `src/sample_manager/tui/widgets/help_screen.py` — `HelpScreen(ModalScreen)` listing keys/usage
- `src/sample_manager/tui/styles/app.tcss` — help screen styling (all CSS here, no inline)

## Resolution
- New `src/sample_manager/tui/widgets/help_screen.py`: `HelpScreen(ModalScreen)` that builds its
  content from `KEYMAP` + `ACTION_CATEGORIES` + `ACTION_DESCRIPTIONS` (single source of truth — no
  hardcoded second copy). Dismissed by `escape`/`q`/`question_mark`; calls `event.stop()` before
  `dismiss()` so the key doesn't bubble and re-open the overlay. No inline CSS.
- `app.py`: imports `HelpScreen`; `show_help` action now pushes it.
- Root-cause note: `?` was also dead because Textual reports it as `question_mark` — fixed in
  `keybindings.py` under task 002. Help CSS added to `styles/app.tcss`.

## Validation
- Full suite (orchestrator-run, combined with audio task): **580 passed, 0 failed**.

## Regression Test
- Shipped with the fix: `tests/test_tui_pilot.py` — Pilot tests that `?` opens help and
  `escape`/`?`/`q` dismiss back to the browser, plus content/category assertions.

## Links
- Prompt: `prompt.md`
- Issue log row: `docs/reports/tui-issues.md` #3
