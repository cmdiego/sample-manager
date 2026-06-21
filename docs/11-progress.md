# Progress

## Done
- Phase 1: scaffolding + config/init/validate CLI
- Phase 2: SQLite bootstrap + migrations + repository layer
- Phase 3: Scan MVP (scanner, sample upsert, CLI commands)
- Phase 4: Search + browse CLI (SearchEngine, tag expansion, pagination)
- Phase 5: Tagging CLI (tag service, tag/alias/parent commands, bulk ops)
- Phase 6: Profiles loader (arrangement + export profiles from YAML, CLI list/show)

## In progress

## Next
- Phase 7: Arrangements (saved selection)
- Phase 8: File traversal / navigation UX

## Phase 2 Deliverables

### New source modules (11 files)
- `src/sample_manager/normalize.py` — `norm_text`, `norm_rel_path`, `norm_abs_path`
- `src/sample_manager/db.py` — `Db` wrapper: PRAGMAs, execute/fetch, transaction CM
- `src/sample_manager/migrations.py` — schema_version + Migration 0001 (Appendix A DDL)
- `src/sample_manager/repos/__init__.py` — package re-exports
- `src/sample_manager/repos/library_root_repo.py` — `get_or_create`, `get_by_id`, `list_all`
- `src/sample_manager/repos/sample_repo.py` — `upsert` (ON CONFLICT DO UPDATE), `get_by_id`, `list_by_root`
- `src/sample_manager/repos/tag_repo.py` — create/get, shorthand, hide/unhide, list
- `src/sample_manager/repos/tag_alias_repo.py` — add/remove alias, resolve (name->shorthand->alias)
- `src/sample_manager/repos/sample_tag_repo.py` — attach (idempotent), detach, list
- `src/sample_manager/repos/tag_parent_repo.py` — add_parent (cycle-check CTE in txn), remove, list
- `src/sample_manager/tag_graph.py` — `TagGraphService`: descendants_including_self, expand_for_search

### New test files (5 files)
- `tests/test_normalize.py` — 21 tests
- `tests/test_db.py` — 18 tests
- `tests/test_migrations.py` — 13 tests
- `tests/test_repos.py` — 56 tests (all 6 repos)
- `tests/test_tag_graph.py` — 10 tests

### Modified
- `tests/conftest.py` — added `db` fixture (fresh DB with migrations per test)

### Test totals
- Phase 1: 50 tests (unchanged, no regressions)
- Phase 2: 118 new tests
- Total: 168 passed in 0.29s

## Phase 3 Deliverables

### New source modules (1 file)
- `src/sample_manager/scanner.py` — `DEFAULT_SAMPLE_EXTENSIONS`, `ScanResult` dataclass, `collect_samples` (pure), `scan_library` (orchestration + persistence)

### Modified source modules (3 files)
- `src/sample_manager/repos/sample_repo.py` — added `count_by_root`, `count_all`, `delete_stale`
- `src/sample_manager/repos/library_root_repo.py` — added `count`
- `src/sample_manager/cli.py` — added `_get_db` helper, `sample scan` command (`--rescan`, `--fast`), `sample status` command

### New test files (1 file)
- `tests/test_scanner.py` — 35 tests across 5 classes (collect_samples, scan_library integration, repo additions, CLI scan, CLI status)

### Test totals
- Phase 1: 50 tests (unchanged)
- Phase 2: 118 tests (unchanged)
- Phase 3: 35 new tests
- Total: 203 passed in 0.36s

## Phase 4 Deliverables

### New source modules (1 file)
- `src/sample_manager/search.py` — `SearchResult` dataclass, `SearchEngine` class (SQL query builder with name/path/tag filters, tag resolution + descendant expansion, AND semantics for multi-tag, pagination, sorting)

### Modified source modules (1 file)
- `src/sample_manager/cli.py` — added `_format_table` helper, `sample search` command (positional QUERY + `--name`, `--path`, `--tag`, `--sort`, `--page`, `--page-size`, `--json`), `sample browse` command (`--page`, `--page-size`, `--sort`, `--json`)

### New test files (1 file)
- `tests/test_search.py` — 50 tests across 10 classes (SearchResult, no-filters, name filter, path filter, tag filter with descendant expansion, combined filters, pagination, sorting, search CLI, browse CLI)

### Key design decisions
- Multiple `--tag` flags use AND semantics (sample must match all tags)
- Positional `QUERY` arg is shorthand for `--name`
- Unknown tags return empty results (no error)
- Tag filtering expands to descendants via `TagGraphService.expand_for_search`
- Output contract: stable columns `id, filename, rel_path, ext, size_bytes, mtime_epoch`

### Test totals
- Phase 1: 50 tests (unchanged)
- Phase 2: 118 tests (unchanged)
- Phase 3: 35 tests (unchanged)
- Phase 4: 50 new tests
- Total: 253 passed in 0.54s

## Phase 5 Deliverables

### New source modules (1 file)
- `src/sample_manager/tag_service.py` — orchestration service: `resolve_tag`, `resolve_or_create_tag`, `tag_sample`, `untag_sample`, `list_sample_tags`, `bulk_tag`, `bulk_tag_from_search`, `add_tag_alias`, `remove_tag_alias`, `add_tag_parent`, `remove_tag_parent`, `BulkResult` dataclass

### Modified source modules (1 file)
- `src/sample_manager/cli.py` — added `tag_app` subgroup with commands: `tag add`, `tag remove`, `tag list`, `tag bulk`; nested `tag_alias_app` subgroup: `tag alias add`, `tag alias remove`; nested `tag_parent_app` subgroup: `tag parent add`, `tag parent remove`

### New test files (2 files)
- `tests/test_tag_service.py` — 40 tests across 9 classes (resolve_tag, resolve_or_create_tag, tag_sample, untag_sample, list_sample_tags, bulk_tag, bulk_tag_from_search, alias service, parent service)
- `tests/test_tag_cli.py` — 25 tests across 7 classes (tag add CLI, tag remove CLI, tag list CLI, tag bulk CLI, tag alias CLI, tag parent CLI)

### Key design decisions
- `tag add` auto-creates tags via `get_or_create` (no separate create step needed)
- `tag remove` requires the tag to exist (strict resolution)
- `tag bulk --from-search` passes query as name filter to SearchEngine (up to 10000 results)
- Bulk operations are idempotent (duplicate attach/detach silently ignored)
- Tag resolution chain: name_norm -> shorthand_norm -> alias_norm (case-insensitive)
- Hidden tags excluded from resolution by default; `include_hidden` parameter available
- Cycle detection for parent edges delegates to existing `TagParentRepo` CTE check
- No new migrations needed — all tag tables existed from Phase 2

### Test totals
- Phase 1: 50 tests (unchanged)
- Phase 2: 118 tests (unchanged)
- Phase 3: 35 tests (unchanged)
- Phase 4: 50 tests (unchanged)
- Phase 5: 65 new tests (40 service + 25 CLI)
- Total: 318 passed in 0.76s

## Phase 6 Deliverables

### New source modules (1 file)
- `src/sample_manager/profiles.py` — `ArrangementProfile` and `ExportProfile` dataclasses with `from_dict()` validation, `ProfileValidationError`, YAML loaders (`load_arrangement_profiles`, `load_export_profiles`), lookup helpers (`get_arrangement_profile`, `get_export_profile`), `get_profiles_dir`, `create_example_profiles`

### Modified source modules (2 files)
- `src/sample_manager/config.py` — added `profiles_dir` to default template, `normalize_config()`, and `validate_config()` (WARN if dir missing)
- `src/sample_manager/cli.py` — added `profile_app` subgroup (`profile list`, `profile show`), `export_profile_app` subgroup (`export-profile list`, `export-profile show`); updated `init` command to create profiles directory + example files

### New test files (2 files)
- `tests/test_profiles.py` — 63 tests across 10 classes (ArrangementProfile valid/invalid, ExportProfile valid/invalid, YAML loading for both types, lookup helpers, get_profiles_dir, create_example_profiles)
- `tests/test_profile_cli.py` — 17 tests across 5 classes (profile list, profile show, export-profile list, export-profile show, init creates profiles)

### New/modified non-Python files
- `config.example.yaml` — added `profiles_dir` key
- `profiles/arrangement_profiles.yaml` — project-root example/starter (empty list + commented schema)
- `profiles/export_profiles.yaml` — project-root example/starter (empty list + commented schema)

### Key design decisions
- Profile location configurable via `profiles_dir` in config.yaml (default: `~/.sample_manager/profiles/`)
- Dataclasses with `from_dict()` factory for validation (required fields, enum values, numeric ranges)
- `ProfileValidationError(ValueError)` — catchable by existing CLI error handlers
- Graceful degradation: missing/empty YAML files return empty list (not errors)
- Duplicate profile names within a file raise `ProfileValidationError`
- `sample init` creates profiles directory + example files (idempotent — existing files not overwritten)
- No DB schema changes — profiles are YAML-only in this phase

### Test totals
- Phase 1: 50 tests (unchanged)
- Phase 2: 118 tests (unchanged)
- Phase 3: 35 tests (unchanged)
- Phase 4: 50 tests (unchanged)
- Phase 5: 65 tests (unchanged)
- Phase 6: 80 new tests (63 unit + 17 CLI)
- Total: 398 passed in 0.91s

## Log
- 2026-01-25 15:34 — generated prompt 'prompt_1' (header=10-chat-starter.md, prompt=prompt_1.md)
- 2026-01-27 22:00 — generated prompt 'prompt_2' (header=10-chat-starter.md, prompt=prompt_2.md)
- 2026-02-13 16:24 — generated prompt 'prompt_2' (header=10-chat-starter.md, prompt=prompt_2.md)
- 2026-02-13 — Phase 2 implemented: SQLite bootstrap, migrations, 6 repos, tag graph service, 118 tests
- 2026-02-13 16:55 — generated prompt 'prompt_3' (header=10-chat-starter.md, prompt=prompt_3.md)
- 2026-02-13 — Phase 3 implemented: scanner module, scan/status CLI, 35 tests, 203 total passing
- 2026-02-13 17:17 — generated prompt 'prompt_4' (header=10-chat-starter.md, prompt=prompt_4.md)
- 2026-02-13 — Phase 4 implemented: SearchEngine, search/browse CLI, 50 tests, 253 total passing
- 2026-02-13 18:04 — generated prompt 'prompt_5' (header=10-chat-starter.md, prompt=prompt_5.md)
- 2026-02-13 — Phase 5 implemented: tag service, tag/alias/parent CLI, bulk ops, 65 tests, 318 total passing
- 2026-02-13 18:23 — generated prompt 'prompt_6' (header=10-chat-starter.md, prompt=prompt_6.md)
- 2026-02-13 — Phase 6 implemented: profiles loader, profile/export-profile CLI, 80 tests, 398 total passing
- 2026-06-21 — Added file traversal plan doc for Vim-style navigation (`h/j/k/l` plus arrow-key parity)
