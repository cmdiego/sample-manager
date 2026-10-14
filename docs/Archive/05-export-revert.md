# docs/05-export-revert.md
# Export & Revert

## 1) Export workflow (high-level)
Inputs:
- arrangement_name or arrangement_id
- export_dir (target)
- export_profile
- mode: copy | symlink | move (move requires explicit opt-in)

DB-alignment notes (UPDATED):
- IDs are SQLite ints.
- ExportRun and HistoryEntry are persisted in SQLite.
- HistoryEntry.plan_json is the source of truth for revert.

Steps:
1) Load Arrangement + Sample selection from DB (selection uses sample_id ints).
2) Compute Plan using ArrangementEngine (docs/04-arrangement.md).
3) If Plan invalid -> fail with errors.
4) Preview (optional) is printing Plan.
5) Apply filesystem operations (copy/symlink/move).
6) Persist ExportRun + HistoryEntry(plan_json, stats_json, errors_json).
7) Return export_id.

## 2) Revert workflow (high-level)
Inputs:
- export_id (or last export)

Steps:
1) Confirm user intent (unless confirmations disabled).
2) Load HistoryEntry(plan_json) for the export.
3) Compute inverse operations (reverse order).
4) Execute inverse operations:
   - remove created symlinks/copied files
   - restore moved/renamed files if move mode was used
5) Record status:
   - reverted / partial / failed
6) Return exit code:
   - 0 success
   - 5 partial revert (if partial semantics used)
   - 1 unexpected error

## 3) Edge cases & policies
- Missing files during export:
  - record as error; continue or fail based on policy
- Existing destination file:
  - require confirmation or fail depending on policy
- Partial export:
  - HistoryEntry records per-op results; revert uses what actually happened
- Revert idempotency:
  - second revert should be safe (no-op removals tolerated)

## 4) History JSON shape (plan_json)
HistoryEntry.plan_json stores:
- export_id
- export_dir
- export_profile_id/name
- plan (operations, warnings, errors)
- execution results (optional):
  - per operation: success/failure + message

Notes:
- Plan remains deterministic; history captures actual execution outcomes.