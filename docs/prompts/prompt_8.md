# docs/prompts/prompt_8.md
Task (Phase 8): Planning engine (deterministic Plan) + `arrangement preview`.

Read these docs first:
- docs/04-arrangement.md (template, sanitization, collisions, Plan contract)
- docs/03-cli.md (preview command)
- docs/06-ops-safety.md (dry-run principles)

DB alignment:
- sample_id is an int; src path is derived from library_root.path + sample.rel_path

Scope (ONLY):
- compute_plan() -> Plan (pure, deterministic)
- preview command renders Plan (table/json)
- no filesystem export or revert

Testing required (determinism, collisions, truncation, illegal chars).