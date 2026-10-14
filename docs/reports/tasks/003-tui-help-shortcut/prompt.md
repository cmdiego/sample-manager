Task (003 — TUI Help Shortcut): make `?` open a help overlay showing keybindings and how to use the TUI.

Read these docs first:
- docs/reports/tasks/003-tui-help-shortcut/task.md
- src/sample_manager/tui/keybindings.py
- src/sample_manager/tui/app.py
- src/sample_manager/tui/widgets/action_pane.py  (existing ModalScreen pattern to follow)

Scope (ONLY):
- Add a `HelpScreen(ModalScreen)` widget listing the KEYMAP actions grouped by category
  (movement, selection, filter, app) plus a short "how to use" blurb.
- Wire the `show_help` action in app.py:on_key to push the help screen; dismiss on `?`/escape/q.
- Derive the displayed bindings from keybindings.py KEYMAP so help stays in sync — do not
  hardcode a second copy of the bindings.

Deliverables:
- src/sample_manager/tui/widgets/help_screen.py
- app.py dispatch change; CSS in styles/app.tcss.
- A Pilot test that `?` opens help and dismissing returns to the browser.

Constraints:
- CSS only in styles/app.tcss (no inline DEFAULT_CSS); follow the ActionPane modal pattern;
  no business logic duplication.

Testing required. Run pytest tests/ -v and report results; no reduction in passing tests.
