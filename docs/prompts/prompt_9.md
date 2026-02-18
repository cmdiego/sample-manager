# docs/prompts/prompt_9.md
Task (Phase 9): Export + History recording.

Read these docs first:
- docs/05-export-revert.md (export flow + history)
- docs/06-ops-safety.md (confirmations, filesystem abstraction)
- docs/03-cli.md (export CLI)

DB alignment:
- export_id and history_entry.id are ints; history_entry.plan_json is source of truth for revert.

Scope (ONLY):
- FilesystemOps abstraction
- ExportService executes Plan
- Persist ExportRun + HistoryEntry
- no revert logic

Testing required.