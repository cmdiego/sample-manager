# docs/06-ops-safety.md
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
- Any command that mutates filesystem state should support:
  - --dry-run (no filesystem changes)
  - --json (machine-readable plan/preview)
- Preview output is derived from a Plan, not from executing filesystem ops.

## 4) Logging
- Log all operations:
  - scans
  - migrations / schema bootstraps
  - tag changes (add/remove/alias/parent edges)
  - exports
  - reverts
- Support verbosity levels:
  - quiet / normal / verbose / debug
- Logs can write to file (configurable)

DB-alignment notes (UPDATED):
- Include integer IDs (sample_id, tag_id, export_id) when available.

## 5) Filesystem abstraction
- All filesystem effects must be behind a small interface (FilesystemOps):
  - mkdirs
  - copy
  - symlink
  - remove
  - move (gated)
  - existence checks
- This enables:
  - testability with temp dirs
  - dry-run planning
  - consistent error handling

## 6) Test strategy requirements
- Use temporary directories and temporary DB files.
- Never touch real user paths in tests.
- Deterministic plan tests must not depend on filesystem ordering.
- Use HOME monkeypatch for config tests.