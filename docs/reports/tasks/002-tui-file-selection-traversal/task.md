# Task 002 — TUI File Selection & Traversal

- **Status**: ✅ Fixed
- **Origin**: TUI issue #2 (user manual testing)
- **Assigned agent**: tui-architect
- **Created**: 2026-07-07
- **Plan**: 002-tui-file-selection-traversal.md

## Problem / Objective
Two related TUI browser problems:
- (a) **Nested directory traversal** — descending through multiple directory levels must work,
  and files inside nested directories must resolve their `sample_id` so they can be selected.
- (b) **Enter selects a file** — pressing the Enter (Return) key on a focused file must add it
  to the selection buffer. Today Enter does nothing.

Expected behavior: Enter on a **file** selects (adds to selection buffer); Enter on a
**directory** descends into it. Nested traversal works to arbitrary depth with correct focus
restore on going back.

## Root Cause
- `src/sample_manager/tui/keybindings.py` `KEYMAP` (lines 9–33) has **no `"enter"` entry** — the
  Return key is unbound, so `resolve_key("enter")` returns `None` and `app.py:on_key` ignores it.
  (`app.py:217` even lists `"enter"` as a fall-through nav key, but nothing handles it.)
- `src/sample_manager/tui/app.py:_handle_enter()` (lines 273–295) activates a **file** by pushing
  the `ActionPane` modal instead of selecting it.
- Nested traversal is structurally supported by `NavState.enter_dir()` + `dir_stack`
  (`nav_state.py:73–104`); the fragile point is `build_items`/`_to_rel_norm` (`nav_state.py:118–179`)
  resolving `sample_id` for files below the root — must be verified so nested files are selectable.

## Files Involved
- `src/sample_manager/tui/keybindings.py` — add Return-key binding
- `src/sample_manager/tui/app.py` — `on_key` dispatch + `_handle_enter` selection semantics
- `src/sample_manager/tui/nav_state.py` — verify nested `sample_id` resolution / add toggle helper if needed
- `src/sample_manager/tui/styles/app.tcss` — only if any style change is required

## Resolution
- `keybindings.py`: added `"enter": "select_or_descend"` (Return). Also fixed a latent bug — Textual
  reports `?`/`/` by key *name*, so `"?"`/`"/"` were dead; changed to `"question_mark"`/`"slash"`.
  Added `ACTION_DESCRIPTIONS` + `ACTION_CATEGORIES` metadata (also feeds the help screen).
- `app.py`: added `select_or_descend` dispatch → `_handle_select_or_descend()`: directory descends
  via `enter_dir`; file **toggles** selection via `TuiDataSource` (no modal). `l`/`→` keep the
  existing ActionPane behavior. Status bar now shows `Return select` / `? help`.
- Nested traversal verified: files 2+ levels deep resolve `sample_id` (tests over
  `build_items`/`_to_rel_norm`, including same-filename collision and false-match guards).

## Validation
- Full suite (orchestrator-run, combined with audio task): **580 passed, 0 failed**.

## Regression Test
- Shipped with the fix: `tests/test_tui_keybindings.py` (Enter→select_or_descend, `question_mark`
  →show_help, metadata coverage) and `tests/test_nav_state.py` (nested `sample_id` resolution,
  `_to_rel_norm` cases).

## Links
- Plan: `002-tui-file-selection-traversal.md`
- Prompt: `prompt.md`
- Issue log row: `docs/reports/tui-issues.md` #2
