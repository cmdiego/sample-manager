Task (008 — Virtual Arrangement Workspace and Browser QoL): implement the staged, non-destructive
Arrangement editor described in the Task 008 plan.

Read first:
- `docs/reports/tasks/008-arrangement-workspace-qol/008-arrangement-workspace-qol.md`
- `docs/reports/tasks/008-arrangement-workspace-qol/task.md`
- `docs/00-vision.md`
- `docs/04-arrangement.md`
- `docs/06-ops-safety.md`
- `src/sample_manager/repos/arrangement_repo.py`
- `src/sample_manager/arrangement_service.py`
- `src/sample_manager/gui/`

Execution rules:
- Implement one phase at a time and pass its gate before continuing.
- Treat all directories as virtual Arrangement metadata. Never mutate source-library files.
- Preserve `arrangement_sample` as membership truth and maintain compatibility for existing rows.
- Preserve `Selection` as the internal domain/API name but use `Stage` for all GUI-facing copy.
- Use the concise GUI action vocabulary `Add`, `Remove`, and `Commit`; Commit means transferring
  staged samples into the active Arrangement.
- Repository owns SQL; framework-neutral service owns validation/transactions; Qt owns rendering and
  input only.
- Use Qt model/view APIs and context-sensitive shortcuts; do not manually rebuild tree widgets.
- Delete/Backspace must never delete from the source browser.
- Recursive folder removal requires an impact summary and confirmation.
- Every bulk mutation is atomic; undo uses inverse arrangement metadata operations.
- Existing arrangements without virtual folders must produce unchanged export plans.

Required deliverables:
- Migration 0005, fresh-schema parity, repository APIs, immutable DTOs, and
  `ArrangementWorkspaceService`.
- Folder-aware deterministic export planning.
- Arrangement tab with active arrangement selector, tree model/view, create/rename/move/remove,
  drag/drop, multi-select, context menus, toolbar, and command-palette actions.
- Shortcut contract: Cmd+Shift+N, Cmd+Return, Delete/Backspace, F2, Cmd+A, Cmd+F, Cmd+Z,
  Cmd+Shift+Z, Space, Return, and Escape with platform equivalents.
- Browser substring/global search, debounce, result counts, breadcrumbs/history, extended
  selection, and bulk Selection/Arrangement actions.
- Arrangement search preserving matching ancestors and Next/Previous match navigation.
- Unit, migration, repository, planner, Qt model, GUI interaction, undo, and source-safety tests.
- Updated user, data-model, arrangement, CLI, and help documentation.

Validation required:
- Run the full suite after every phase.
- Run GUI tests with `QT_QPA_PLATFORM=offscreen`.
- Hash/compare the source library fixture before and after arrangement workflows.
- Manually verify shortcuts, multi-selection, drag/drop, recursive confirmation, undo/redo, and
  export preview on macOS, Windows, and Linux.

Stop conditions:
- Do not implement source filesystem create/delete/move operations.
- Do not continue past a phase with migration, planner compatibility, atomicity, safety, or GUI
  regressions.
- Do not silently flatten or detach descendants when folder removal confirmation is cancelled.
