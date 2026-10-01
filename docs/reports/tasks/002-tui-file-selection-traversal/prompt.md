Task (002 — TUI File Selection & Traversal): make Enter select the focused file and confirm nested-directory traversal.

Read these docs first:
- docs/reports/tasks/002-tui-file-selection-traversal/002-tui-file-selection-traversal.md
- docs/13-file-traversal-plan.md
- src/sample_manager/tui/keybindings.py
- src/sample_manager/tui/app.py
- src/sample_manager/tui/nav_state.py
- src/sample_manager/tui/data.py

Scope (ONLY):
- Bind the Enter (Return) key in KEYMAP (keybindings.py).
- Enter on a file adds/toggles it in the selection buffer; Enter on a directory descends into it.
- Verify nested-directory traversal to arbitrary depth; ensure files in nested directories
  resolve a sample_id (build_items/_to_rel_norm) so they are selectable.
- Update the status-bar hint to mention Enter = select. Do not open the ActionPane on Enter.

Deliverables:
- keybindings.py + app.py changes; any nav_state.py fix for nested sample_id resolution.
- Unit tests for key resolution, Enter selection semantics, and nested-file selectability.

Constraints:
- CSS only in styles/app.tcss; DB access only via TuiDataSource; pure logic (no Textual) in
  nav_state.py; update() via remove_children()+mount() (never refresh()).

Testing required. Run pytest tests/ -v and report results; no reduction in passing tests.
