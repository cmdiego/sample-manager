# Task 019 — TUI Sample Tags

- **Status**: In Progress
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

- [ ] Implement a bounded tag-management modal and discovery.
- [ ] Reuse tag service and expose real sample tags in Preview.
- [ ] Keep editing attached to its original sample and refresh tag-search results.
- [ ] Test aliases, idempotence, Stage subjects, empty input, and removal.
- [ ] Validate and prepare a main-targeted PR with incremental commits.

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

- Pending.

### Behavior Implemented

- Pending.

### Validation

- Pending.

### Follow-ups / Risks

- Dedicated favorites, preview volume/looping, metadata filtering, and sorting remain future workflow improvements.
- Branch includes Task 018 and will target main so merging in either order carries dependencies safely.
