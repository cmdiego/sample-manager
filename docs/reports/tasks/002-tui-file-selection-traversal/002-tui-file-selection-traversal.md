# TUI File Selection & Traversal

## Goal
Make the sample browser's file selection and directory traversal work as users expect: the Enter
(Return) key selects the focused file (adds it to the persistent selection buffer), and directory
traversal works to arbitrary nesting depth with files in nested directories remaining selectable.

## Context / Motivation
Reported during manual TUI testing (issue #2). The Return key currently does nothing, and the
selection flow is only reachable via `l`/`right` opening a modal action pane. Users expect Enter
to select. Traversal must also be confirmed for deep directory trees, not just the root.

## Dependencies
- **Blocked by**: none
- **Requires feature**: none
- **Read first**: `docs/13-file-traversal-plan.md`, `src/sample_manager/tui/keybindings.py`,
  `src/sample_manager/tui/app.py`, `src/sample_manager/tui/nav_state.py`,
  `src/sample_manager/tui/data.py`

## Scope
- Bind the Enter (Return) key in `keybindings.py` `KEYMAP`.
- On a **file**, Enter adds the focused sample to the selection buffer (toggle add/remove is
  acceptable and preferable); on a **directory**, Enter descends into it.
- Verify nested-directory traversal descends to arbitrary depth and that `build_items`
  resolves `sample_id` for files in nested directories so they can be selected.
- Keep `l`/`right` behavior coherent (they may continue to open the action pane on files).

## Non-Goals
- Waveform/audio preview (owned by tui-architect separately; not part of this task).
- Multi-select rectangles, drag-and-drop, or search-ranking changes.
- Any change to the selection persistence schema.

## Design / Approach
- Add `"enter": "<action>"` to `KEYMAP`. Either reuse the existing `enter` action with
  file-vs-dir branching in `_handle_enter`, or introduce a dedicated `select_or_descend` action.
- In `app.py:_handle_enter`, branch on `item.is_dir`: dir → `enter_dir`; file → add/toggle
  selection via `TuiDataSource` (do **not** open the modal for the Enter key).
- All DB access stays in `TuiDataSource` (`data.py`); pure state transitions stay in
  `nav_state.py` (no Textual imports); `update()` keeps the `remove_children()`+`mount()` pattern.
- Confirm `_to_rel_norm` (`nav_state.py`) matches nested files to their DB `rel_path_norm` so
  `sample_id` is populated below the root; fix if nested files show "(not indexed)".

## Implementation Steps
1. Add the Enter/Return binding in `keybindings.py`.
2. Update `app.py:on_key` dispatch and `_handle_enter` so Enter selects files / descends dirs.
3. Verify/repair nested `sample_id` resolution in `nav_state.build_items`/`_to_rel_norm`.
4. Update the status-bar hint text to mention Enter = select.
5. Add/adjust tests (nav-state selection toggle, nested traversal selectability, key resolution).
6. Run `pytest tests/ -v`; confirm green with no regressions.

## Testing
- `resolve_key("enter")` returns the selection/descend action.
- Enter on a file toggles its presence in the selection buffer; Enter on a dir descends.
- A file two+ levels deep resolves a non-None `sample_id` and is selectable.
- `pytest tests/ -v` stays green (528+ passing).

## Resolved Decisions
- Enter selects files; directories still descend on Enter. Selection remains explicit
  (focus movement never changes selection) per `docs/13-file-traversal-plan.md`.
