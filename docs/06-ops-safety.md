# Safety, Confirmations, Logging

## 1) Safety defaults
- Default export mode: copy
- Default destructive operations: disabled
- Default revert: requires explicit --confirm
- Dry-run is available where filesystem changes are possible.

## 2) Confirmation gates
Required confirmation for:
- export --mode move
- operations that overwrite existing files
- revert (always unless config.confirmations=false)

CLI should return exit code 3 for safety refusal (missing --confirm).

## 3) Dry-run / Preview
- Preview = compute Plan and render as:
  - table (default)
  - json
- Preview must include:
  - counts of operations
  - collisions
  - sanitization/truncation notes
  - constraint violations

## 4) Logging
Two layers:
- user-facing console messages (info/warn/error)
- audit log file (structured JSON lines)

Audit events (examples):
- scan_started, scan_finished
- arrangement_created, arrangement_updated
- plan_computed
- export_applied, export_partial, export_failed
- revert_started, revert_finished, revert_partial

Each event includes:
- timestamp
- library_root_id
- export_id / arrangement_id (when relevant)
- counts + error summaries

## 5) Filesystem abstraction
All filesystem mutations go through a small interface:
- mkdir_p(path)
- copy_file(src, dst)
- symlink_file(src, dst)
- move_file(src, dst)
- remove_file(dst)
- remove_dir_if_empty(path)

Benefits:
- unit tests can mock this interface for plan-level logic
- integration tests can run with temp dirs

## 6) Test strategy requirements
- Pure logic tests:
  - template rendering
  - sanitization/truncation
  - collision handling determinism
- Integration tests:
  - tempdir export copy/symlink
  - revert idempotency
  - partial failure behavior
