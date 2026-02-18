# docs/prompts/prompt_10.md
Task (Phase 10): Revert using HistoryEntry (source of truth).

Read these docs first:
- docs/05-export-revert.md (revert algorithm + edge cases)
- docs/06-ops-safety.md (confirmation gates)
- docs/03-cli.md (revert CLI + exit codes)

Scope (ONLY):
- RevertService loads HistoryEntry.plan_json and reverses ops
- idempotent, supports continue-on-error
- updates export status
- no new schema unless required

Testing required.