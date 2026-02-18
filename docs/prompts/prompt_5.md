# docs/prompts/prompt_5.md
Task (Phase 5): Tagging system (UPDATED: aliases + inheritance DAG + soft delete).

Read these docs first:
- docs/03-cli.md (tag commands + semantics)
- docs/02-persistence.md (tag/tag_alias/sample_tag/tag_parent schema + CTEs)
- docs/01-data-model.md (normalized uniqueness, is_hidden)

Scope (ONLY):
- Implement tag mutation CLI and services:
  - Create tags (name_display + name_norm)
  - Set shorthand (optional; shorthand_norm unique)
  - Add/remove aliases (alias_norm global unique)
  - Attach/detach tags to samples
  - Manage parent edges (child -> parent) with cycle forbid
- Implement CLI:
  - `sample tag add <sample-id> <tag>`
  - `sample tag remove <sample-id> <tag>`
  - `sample tag bulk --from-search "<query>" --add <tag> [--remove <tag>]`
  - (If included in docs/03) tag alias commands and parent-edge commands:
    - `sample tag alias add <tag> <alias>`
    - `sample tag alias remove <alias>`
    - `sample tag parent add <child> <parent>`
    - `sample tag parent remove <child> <parent>`
  - If docs/03 does not include these extra commands, implement the underlying service APIs anyway for Phase 6+.

Semantics requirements:
- Tag resolution is case-insensitive and may resolve via:
  1) tag.name_norm
  2) tag.shorthand_norm
  3) tag_alias.alias_norm
- Soft delete:
  - hide/unhide tags via is_hidden; default list/resolve excludes hidden unless include_hidden=True
- Parent edges:
  - enforce DAG; cycles forbidden using CTE check in same transaction
- Bulk operations must be idempotent (no duplicates)

Testing (required):
- Tag uniqueness by name_norm
- shorthand uniqueness (nullable unique)
- alias uniqueness (global)
- alias resolution to tag_id
- sample_tag attach idempotent
- parent-edge descendants expansion
- cycle insert rejected

Deliverables:
- services + CLI updates + tests