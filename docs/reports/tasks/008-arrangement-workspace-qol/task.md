# Task 008 — Virtual Arrangement Workspace and Browser QoL

- **Status**: Planned
- **Origin**: User request (arrangement directories and browsing QoL, 2026-07-07)
- **Assigned agent**: orchestrator (coordinates persistence, services, Qt GUI, safety, and tests)
- **Created**: 2026-07-07
- **Plan**: `008-arrangement-workspace-qol.md`

## Problem / Objective

Add a first-class Qt Arrangement workspace where users can organize arrangement samples into
virtual folders, create and rename folders, search, multi-select, move, and remove files or folder
subtrees efficiently. All operations modify arrangement metadata only and must never create,
move, rename, or delete source-library files.

## Confirmed Product Boundary

- Directories are virtual destination folders stored against an Arrangement.
- Removing a file detaches it from the Arrangement only.
- Removing a folder detaches all arrangement samples in its subtree and removes the virtual folder
  subtree after a confirmation summarizing impact.
- Source-library filesystem deletion is explicitly out of scope.
- Delete/Backspace is inactive in the source browser and active only in the Arrangement workspace.

## Dependencies

- Task 007 Qt GUI and framework-neutral services.
- Existing `arrangement`, `arrangement_sample`, profile, search, and export-plan behavior.
- New SQLite migration for virtual folders and arrangement item placement.
- No audio-domain changes are required.

## Expected Areas

- `migrations.py` and arrangement repository/service — virtual folder persistence and transactions.
- `gui/models/` and `gui/widgets/` — arrangement tree, active arrangement selector, search, and
  multi-selection.
- `gui/main_window.py`, shortcuts, dialogs, and command palette — context-sensitive actions.
- Arrangement planner — use virtual folder placement when producing destination paths.
- Tests and documentation — migration, repository, service, model, GUI, planning, safety, and undo.

## Resolution

Pending implementation through the phase gates in the plan.

## Validation

- Full existing suite remains green.
- Source-library fixture trees are byte-for-byte unchanged by all arrangement operations.
- Migration works for fresh and existing databases.
- Qt behavior passes with `QT_QPA_PLATFORM=offscreen`.

## Links

- Plan: `008-arrangement-workspace-qol.md`
- Implementation prompt: `prompt.md`
- Safety invariants: `docs/00-vision.md`, `docs/06-ops-safety.md`
- Arrangement rules: `docs/04-arrangement.md`

