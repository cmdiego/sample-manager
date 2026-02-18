# docs/prompts/prompt_7.md
Task (Phase 7): Arrangements (saved selection of sample IDs + profile reference).

Read these docs first:
- docs/01-data-model.md (ArrangementInstance; sample IDs are ints)
- docs/03-cli.md (arrangement commands)
- docs/02-persistence.md (arrangement tables if specified)

Scope (ONLY):
- Implement ArrangementManager + persistence for:
  - create arrangement (name + profile reference)
  - persist selected sample IDs (join table)
  - list arrangements
  - add/remove sample IDs
- Do NOT implement planning/preview (Phase 8) or export/revert.

Testing required.

Deliverables:
- arrangement manager + CLI updates + tests