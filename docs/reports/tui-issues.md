# TUI Issues Log

Issues found during manual testing. Each issue is assigned a number, a status, and a description of the fix applied.

| # | Status | Description | Fix |
|---|--------|-------------|-----|
| 1 | ✅ Fixed | `TopDisplayWidget` border used `$text` — invalid Textual CSS color variable | Changed to `white` in `styles/app.tcss` |
| 2 | ✅ Fixed | File selection & traversal: Enter (Return) key was unbound and didn't select the focused file; nested-dir file `sample_id` resolution unverified | Bound Return→`select_or_descend` (file toggles selection, dir descends) in `keybindings.py`/`app.py`; verified nested `sample_id` resolution. See `tasks/002-tui-file-selection-traversal/` |
| 3 | ✅ Fixed | Help shortcut `?` was dead: `KEYMAP` mapped `?`→`show_help` but `app.py:on_key` had no handler and no help screen existed | Added `HelpScreen` modal (derives keys from `KEYMAP`), wired `show_help`; fixed `?`→`question_mark` key name. See `tasks/003-tui-help-shortcut/` |
