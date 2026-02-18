# docs/prompts/prompt_4.md
Task (Phase 4): Search + Browse CLI (SQL-backed, tag semantics updated).

Read these docs first:
- docs/03-cli.md (browse/search commands and flags)
- docs/02-persistence.md (schema + indexes; tag inheritance semantics)
- docs/01-data-model.md (TagAlias, TagParent DAG)

Scope (ONLY):
- Implement SearchEngine for querying samples by:
  - name pattern (LIKE/glob; regex optional)
  - path fragments (rel_path)
  - tags (Phase 5 adds tagging CLI, but search must support tag filters once tags exist)
- Implement tag filtering semantics:
  - filtering by a tag expands to include all descendant tags (parent matches descendants only)
  - use TagGraphService.expand_for_search(tag_ids)
- Implement CLI:
  - `sample search ... [--json]`
  - `sample browse ...` with pagination
- Do NOT implement tagging mutations (Phase 5), arrangements, export, revert.

Output contract:
- Table output: stable columns (id, filename, rel_path, ext, size_bytes, mtime_epoch)
- JSON output: stable schema with items + paging

Testing (required):
- Insert fixture samples + tags + sample_tag
- Verify search by name works
- Verify tag filter expands descendants
- Verify pagination behavior

Deliverables:
- search module + CLI updates + tests