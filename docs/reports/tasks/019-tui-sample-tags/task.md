# Task 019 — TUI Sample Tags

- **Status**: Done
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: Continued TUI workflow improvement requested by the user
- **Scope**: Add/remove sample tags from Browser or Stage, show tags in Preview, and refresh indexed tag searches.

## 1. [Struct]

- **Primary areas**: TUI tag modal, app actions, and data adapter.
- **Supporting areas**: Existing `tag_service` resolution/attachment APIs and indexed search.
- **Ownership**: Reuse tag-service persistence and alias resolution; widgets present current attachments and emit explicit add/remove intent.
- **Expected changes**: TUI data/app/modal, action pane and preview, tests, docs. No database schema changes.

## 2. [Interfaces]

- **User interface**: F6 / Tags in the command palette / Edit Tags in a file's action pane.
- **Editing**: Add a name or existing alias; remove a selected tag from this sample; changes apply immediately; Close/Escape ends editing.
- **Persistence**: Existing tag/sample_tag rows; removing an attachment never deletes the shared tag.
- **Contract**: Edit the sample captured when the modal opens even if background refresh changes focus. Active tag queries and Preview update after changes without auditioning.

## 3. [Todo]

- [x] Implement a bounded tag-management modal and discovery.
- [x] Reuse tag service and expose real sample tags in Preview.
- [x] Keep editing attached to its original sample and refresh tag-search results.
- [x] Test aliases, idempotence, Stage subjects, empty input, and removal.
- [x] Validate and prepare a main-targeted PR with incremental commits.

## 4. [Implementation + Revert]

### Implementation Plan

1. Add adapter operations around existing tag-service APIs, validating empty/hidden tag input before writes.
2. Show attached visible tags in the modal and Preview; explicitly communicate immediate changes.
3. Capture sample IDs for modal/action-pane callbacks and rerun active indexed searches after mutation.
4. Exercise real Textual input against SQLite, including user names containing markup characters.

### Revert Plan

1. Revert Task 019 TUI data/app/modal/action/preview and documentation changes.
2. Remove this report and tracker row. Existing tag attachments remain valid for CLI/GUI readers.

## 5. [Invariance]

- Tag alias/shorthand resolution stays compatible with CLI semantics.
- Hidden tags remain hidden and are not silently restored or overwritten.
- Removing a tag affects only the captured sample.
- Sample audio and Stage membership remain unchanged by tagging.
- Modal input cannot trigger Browser actions or transport keys.

## 6. [Implementation]

### Changed Files

- `tui/widgets/tags_screen.py` — immediate Add/Remove actions, alias/name input, current tag list, errors and Close/Escape.
- `tui/data.py` — tag-service adapter, visible tags in sample metadata, hidden/empty-name guards, and handling a sample pruned between reads.
- `tui/app.py` — F6/palette/keyboard action, captured sample subjects for file actions, active-query refresh, and safe polling/status updates during teardown.
- Action pane, Preview, keybindings/help and README — tag discovery and literal rendering of user names.
- `tests/test_tui_tags.py` — aliases, idempotence, removal scope, tag queries, Stage/captured subjects, hidden/empty/stale writes, and teardown/read races.
- `tests/test_tui_add_library.py` — first-run Help and Quit regression.

### Behavior Implemented

- F6, t, Sample Tags in the palette, and Edit tags in the file action pane manage a captured sample's visible tags. Existing aliases resolve consistently with the CLI. Preview and active tag queries update immediately without auditioning.
- Hidden tags remain hidden; removal detaches only from this sample. Names with spaces, commas and brackets remain literal.
- Fixed a reproduced audio polling callback after child widgets had unmounted. The timer is stopped during teardown and late view updates are ignored.
- A final first-run pilot reproduced Help and Quit being ignored before a root exists. Application commands now work before sample-navigation state is loaded.

### Validation

- Tag-input tests: 4 passed; teardown/read-race plus search tests: 8 passed.
- First-run Help/Quit test failed before the routing fix, then passed with the navigation/search group (10 tests).
- Inspected a rendered Textual screenshot of the tag editor at 80×24, including literal bracketed tag names and visible action buttons.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/`: 904 passed, 10 existing deprecation warnings.
- `git diff --check origin/main`: passed.

### Follow-ups / Risks

- Dedicated favorites, preview volume/looping, metadata filtering, and sorting remain future workflow improvements.
- Branch includes Task 018 and will target main so merging in either order carries dependencies safely.
