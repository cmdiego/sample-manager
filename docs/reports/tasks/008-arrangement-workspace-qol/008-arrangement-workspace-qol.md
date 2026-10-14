# Virtual Arrangement Workspace and Browser QoL

## Goal

Provide a safe, keyboard-efficient Arrangement editor in the Qt GUI. Users can organize samples
into virtual destination folders, search both the library and arrangement, perform single or bulk
selection operations, and undo arrangement edits without mutating source audio files.

## Current State

- Arrangements are available through CLI/repository APIs but have no Qt workspace.
- `arrangement_sample` stores membership only; it has no virtual parent folder or display order.
- The Qt browser displays one source directory and supports a prefix filter and persistent
  Selection buffer.
- Source browser rows are single-selection and arrangement operations are not context-sensitive.
- Export planning derives paths entirely from the Arrangement Profile naming template.

## Resolved Decisions

- `arrangement_sample` remains the source of truth for one sample membership per arrangement.
- Add virtual folder placement to arrangement metadata; never duplicate or copy source paths.
- Use an implicit arrangement root rather than storing a root folder row.
- Folder names are unique case-insensitively among siblings.
- The same sample may appear only once in an arrangement because the existing composite primary key
  remains authoritative.
- Removing a folder recursively removes arrangement memberships below it, then removes the folder
  subtree in one transaction.
- Recursive removal requires confirmation; single-file detach does not.
- Undo/redo is session-local but applies real inverse repository operations immediately.
- GUI widgets never issue SQL or mutate the filesystem.
- Export paths prepend the virtual folder path before profile-generated filenames; ExportProfile
  constraints and collision handling still run over the final destination path.
- The existing Selection domain remains unchanged, but all GUI-facing copy calls it **Stage** to
  communicate its Git-like role before samples are committed to an Arrangement.

## Persistence Model

Add migration `0005_arrangement_virtual_folders`.

### `arrangement_folder`

```text
id              INTEGER PRIMARY KEY
arrangement_id  INTEGER NOT NULL REFERENCES arrangement(id) ON DELETE CASCADE
parent_id       INTEGER NULL REFERENCES arrangement_folder(id) ON DELETE CASCADE
name            TEXT NOT NULL
name_norm       TEXT NOT NULL
sort_order      INTEGER NOT NULL DEFAULT 0
created_at      TEXT NOT NULL
updated_at      TEXT NOT NULL
```

Constraints and indexes:

- Root sibling uniqueness: `(arrangement_id, name_norm)` where `parent_id IS NULL`.
- Nested sibling uniqueness: `(arrangement_id, parent_id, name_norm)` where `parent_id IS NOT NULL`.
- Index `(arrangement_id, parent_id, sort_order, name_norm)` for tree loading.
- Service validation prevents cycles and cross-arrangement parents.

### `arrangement_sample` Additions

```text
folder_id   INTEGER NULL REFERENCES arrangement_folder(id) ON DELETE SET NULL
sort_order  INTEGER NOT NULL DEFAULT 0
```

Existing memberships migrate to the implicit root (`folder_id = NULL`) with stable order by
sample ID. Fresh-schema DDL and incremental migration must produce the same shape.

## Application Interfaces

Introduce a framework-neutral `ArrangementWorkspaceService` over `ArrangementRepo`.

```python
class ArrangementWorkspaceService:
    def list_arrangements(self) -> tuple[ArrangementSummary, ...]: ...
    def tree(self, arrangement_id: int) -> ArrangementTree: ...
    def create_folder(self, arrangement_id: int, parent_id: int | None, name: str) -> Folder: ...
    def rename_folder(self, folder_id: int, name: str) -> Folder: ...
    def move_folders(self, folder_ids: tuple[int, ...], parent_id: int | None) -> None: ...
    def add_samples(self, arrangement_id: int, sample_ids: tuple[int, ...], folder_id=None) -> int: ...
    def move_samples(self, arrangement_id: int, sample_ids: tuple[int, ...], folder_id=None) -> None: ...
    def remove_samples(self, arrangement_id: int, sample_ids: tuple[int, ...]) -> RemovalResult: ...
    def remove_folder_tree(self, folder_id: int) -> RemovalSnapshot: ...
    def restore(snapshot: RemovalSnapshot) -> None: ...
```

DTOs are immutable and contain IDs, names, parent IDs, sort order, sample metadata, and descendant
counts. Repository methods own SQL; service methods own validation and transactions.

## Export Planning Contract

- Each sample receives a normalized virtual folder path from its folder ancestry.
- Render the Arrangement Profile template exactly as today, then prepend the virtual folder path.
- Normalize separators and reject `.`/`..`, absolute paths, empty folder names, and path traversal.
- Run ExportProfile depth, character, filename, case, collision, and violation policies against the
  combined destination path.
- Existing arrangements with no folders produce byte-for-byte equivalent plans.

## Qt Workspace

### Placement

- Replace the bottom-right Stage region with a tabbed panel: **Stage** and
  **Arrangement**.
- Arrangement tab contains an active-arrangement combo, New Arrangement action, tree search field,
  toolbar, and `QTreeView`.
- Use `ArrangementTreeModel(QAbstractItemModel)` with stable custom roles for node type, folder ID,
  sample ID, path, and descendant count.
- Enable `ExtendedSelection`, standard Shift-range selection, and Cmd-toggle selection.
- Drag samples from Browser/Stage into arrangement folders and move arrangement nodes within
  the tree. Reject cycles and cross-arrangement internal moves.

### Folder and File Actions

- Create folder at root or under the focused folder.
- Inline rename virtual folders; reject empty, duplicate, traversal, and separator-containing names.
- Add one or multiple selected library samples to the focused arrangement folder.
- Move selected arrangement samples/folders to another virtual folder.
- Remove one or multiple samples from the arrangement.
- Remove a folder subtree only after a dialog reports folder and sample counts.
- Empty-folder removal still requires confirmation when multiple folders are affected.
- Context menus and command palette expose every keyboard action.

## Shortcut Contract

Shortcuts are context-sensitive and act on the pane with active focus.

| Shortcut | Browser / Stage | Arrangement tree |
|---|---|---|
| `Cmd+Shift+N` | No action | Create virtual folder under focused folder/root |
| `Cmd+Return` | **Commit** staged/selected rows to active arrangement/root | No action |
| `Delete` / `Backspace` | Never delete source files | Detach selected files or confirm folder subtree removal |
| `F2` | No action | Rename focused virtual folder |
| `Cmd+A` | Select all visible rows | Select all visible arrangement nodes |
| `Cmd+F` | Focus browser search | Focus arrangement search |
| `Cmd+Z` | No action | Undo last arrangement edit |
| `Cmd+Shift+Z` | No action | Redo last arrangement edit |
| `Space` | Existing audio transport behavior | Preview focused arrangement sample |
| `Return` | Existing browser activation | Expand/collapse folder or preview sample |
| `Escape` | Clear search/selection context | Clear search, cancel rename, or clear selection |

On macOS, Cmd maps to `Meta`; provide Ctrl equivalents on Windows/Linux through Qt standard key
sequences where available.

## Browsing and Search QoL

### Source Browser

- Change the current prefix-only filter to case-insensitive substring matching.
- Add a scope selector: current directory or indexed library.
- Debounce global indexed search by 150 ms and route it through a framework-neutral search service.
- Display result count, active scope, and a clear button.
- Preserve focused sample by ID when the result set changes; otherwise focus the nearest row.
- Add breadcrumbs with clickable ancestors and Back/Forward navigation history.
- Support extended multi-selection without changing persistent Selection automatically.

### Arrangement Search

- Filter by sample filename or virtual folder name.
- Preserve ancestor folders for matching descendants.
- Display match counts and provide Next/Previous match actions.
- Search changes presentation only; it never alters arrangement membership.

### Bulk Selection Actions

- Add selected browser rows to persistent Stage.
- Remove selected rows from persistent Stage.
- **Commit** selected browser/Stage rows to the active arrangement folder.
- Detach selected arrangement files in one transaction.
- Mixed folder/file removal computes and displays a deduplicated impact summary before execution.

## Undo/Redo

- Implement framework-neutral command objects with `execute()` and `undo()` for create folder,
  rename folder, move nodes, add samples, remove samples, and remove subtree.
- Qt wraps these commands with `QUndoStack` actions and exposes labels such as
  `Undo Remove 12 Samples`.
- Removal snapshots contain only arrangement metadata and sample IDs, never audio bytes.
- Clear the undo stack when switching active arrangements or after an external CLI mutation is
  detected.

## Safety and Failure Behavior

- No `unlink`, `rmdir`, `rename`, `move`, or source `mkdir` calls are permitted in this feature.
- Browser Delete/Backspace is explicitly a no-op and has no destructive context-menu entry.
- All bulk mutations run in one database transaction and roll back completely on error.
- Removing the last sample does not delete the Arrangement.
- Missing indexed source files remain visible as unavailable arrangement entries and can be
  detached normally.
- Export remains plan-first and non-destructive by default.

## Implementation Phases

### Phase 1 — Persistence and Service

1. Add migration 0005 and fresh-schema parity.
2. Extend `ArrangementRepo` with folder CRUD, tree queries, placement, and transactional subtree
   removal/restore primitives.
3. Add immutable DTOs and `ArrangementWorkspaceService` validation.
4. Update export planning for optional virtual folder prefixes.

**Gate:** migration/repository/service/planner tests pass; existing folderless plans are unchanged.

### Phase 2 — Arrangement Qt Model and Basic Editor

1. Implement `ArrangementTreeModel` and Arrangement tab.
2. Add active-arrangement selection, create folder, rename, add samples, and single detach.
3. Add context menus, toolbar actions, and command palette entries.

**Gate:** a user can build and persist a nested virtual arrangement without source filesystem
changes.

### Phase 3 — Multi-Selection, Bulk Removal, and Undo

1. Enable extended selection and bulk commands.
2. Add recursive removal impact dialog and transactional command.
3. Add move/drag-drop plus undo/redo command stack.

**Gate:** all bulk operations are atomic, reversible in-session, and safely confirmed.

### Phase 4 — Search and Navigation QoL

1. Add browser substring/global search, debounce, result counts, and breadcrumbs/history.
2. Add arrangement ancestor-preserving search and match navigation.
3. Finalize context-sensitive shortcut routing and cross-platform key equivalents.

**Gate:** keyboard, mouse, search, multi-select, and focus-preservation acceptance tests pass.

### Phase 5 — Documentation and Cross-Platform Acceptance

1. Update README, CLI/data-model/arrangement docs, GUI help, and screenshots.
2. Run full regression and offscreen GUI suites.
3. Manually validate macOS, Windows, and Linux shortcut mapping and drag/drop.

**Gate:** source libraries remain unchanged and all target-platform acceptance checks pass.

## Testing

- Migration from pre-0005 databases and fresh database schema parity.
- Folder sibling uniqueness, nesting, cycle prevention, cross-arrangement rejection, and ordering.
- Add/move/detach sample transactions and recursive removal/restore snapshots.
- Export path compatibility, virtual prefixes, depth constraints, sanitization, and collisions.
- Qt model indexes, parent/child behavior, roles, reset/data/move signals, and drag/drop MIME data.
- Context-sensitive shortcuts, extended selection, dialogs, search debounce, result counts, and
  focus preservation under `QT_QPA_PLATFORM=offscreen`.
- Undo/redo for every mutation and stack clearing on arrangement switch.
- Safety test hashes the source fixture tree before and after every mutation workflow.
- Full existing suite remains green.

## Non-Goals

- Creating, renaming, moving, or deleting source-library files or directories.
- Duplicating a sample more than once in one arrangement.
- Audio editing, waveform editing, or DAW timeline behavior.
- Persistent cross-session undo history in this increment.
- Sharing arrangement trees between arrangements.

## Rollback

- Migration is additive; existing arrangement membership remains valid at root.
- Folder-aware planning is conditional, so old arrangements retain existing output.
- GUI phases land behind the Arrangement tab without replacing source browsing.
- If a later phase fails, retain completed persistence/service behavior and disable incomplete GUI
  actions rather than deleting migrated metadata.
