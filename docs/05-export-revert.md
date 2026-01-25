# Export & Revert

## 1) Export workflow (high-level)
Inputs:
- arrangement_name or arrangement_id
- export_dir (target)
- export_profile
- mode: copy | symlink | move (move requires explicit opt-in)

Steps:
1) Load Arrangement + Sample selection from DB.
2) Compute Plan using ArrangementEngine (docs/04-arrangement.md).
3) If Plan invalid -> fail with errors.
4) Preview (optional) is printing Plan.
5) Apply:
   - Create directories (mkdir ops)
   - Execute file ops (copy/symlink/move)
   - Collect stats + errors
6) Persist ExportRun + HistoryEntry(plan_json, stats_json, errors_json)
7) Return export_id.

### Apply rules
- Idempotency:
  - If dst exists and matches expected artifact:
    - copy: allow overwrite only with --force (default: fail)
    - symlink: if correct link already exists, treat as success
- Use atomic strategies where possible:
  - write temp then rename for copies (optional)
- Always record partial failures.

## 2) Revert workflow (high-level)
Revert uses HistoryEntry.plan_json for the selected export_id (or last export).

Modes:
- Default assumes export_dir is a sandbox of artifacts:
  - For copy/symlink: revert = delete artifacts created in export_dir
- If move was used:
  - revert must move files back to original locations
  - must handle collisions on restore

Steps:
1) Resolve export_id (explicit or last).
2) Load ExportRun + HistoryEntry.
3) Safety confirmation:
   - require --confirm unless config disables confirmations
4) Execute inverse operations in reverse order:
   - reverse mkdirs after file removals
   - reverse copy/symlink by deleting dst
   - reverse move by moving dst back to src
5) On missing files:
   - if --continue-on-error: record error and proceed
   - else: stop and mark partial
6) Update ExportRun.status:
   - reverted | partial | failed

## 3) Edge cases & policies

### Missing artifacts during revert
- If dst missing: record warning/error, continue based on flag.

### External modifications
- If dst exists but differs:
  - copy: if hash mismatch and no --force-delete, fail or warn (configurable)
  - symlink: if link points elsewhere, warn and skip unless --force

### Restore collisions (move-mode revert)
If original src path is now occupied:
- policy:
  - fail
  - suffix_restore: move restored file to src + ".restored_{n}"
- must be deterministic and reported.

### Partial success guarantee
Revert must be safe to re-run:
- If some artifacts already deleted, re-run should succeed (or produce only warnings).

## 4) History JSON shape (plan_json)
History stores:
- export_dir
- resolved absolute src/dst paths for each op
- operation ordering and notes
This avoids recomputing anything during revert.
