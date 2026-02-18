# Execution Tracker

Purpose: drive iterative delivery while we keep testing the app.

## Workflow Loop (repeat each cycle)
1. Pick 1-2 scoped items from "Active Queue".
2. Implement with tests first (or in lockstep).
3. Run focused tests, then full suite.
4. Record outcomes in "Session Log".
5. Move completed items to "Done".

## Active Queue

### Missing functionality
- [x] Implement `sample arrangement list`
- [x] Implement `sample arrangement create <name> --profile <profile-name> [--from-search ...] [--from-ids ...]`
- [ ] Implement `sample arrangement show <name>`
- [ ] Implement `sample arrangement add <name> ...`
- [ ] Implement `sample arrangement remove <name> ...`
- [ ] Implement `sample arrangement preview <name> [--export-profile ...] [--format ...]`
- [ ] Implement `sample export <arrangement-name> --to <dir> --export-profile <name> [--mode ...]`
- [ ] Implement `sample revert --export-id <id>`

### Data/model work needed for arrangements/export
- [ ] Add arrangement/export tables + migrations
- [ ] Add arrangement/export repositories
- [ ] Define immutable/export history payload format
- [ ] Add idempotency + recovery behavior for partial export/revert

### Refactor candidates
- [ ] Split `src/sample_manager/cli.py` into modular command files (`commands/config.py`, `commands/tag.py`, etc.)
- [ ] Standardize CLI output helpers (table/json/error envelope)
- [ ] Consolidate DB bootstrap patterns (`_get_db`, config checks) into shared utility
- [ ] Improve typing coverage for service/repo boundaries
- [ ] Add clearer domain-layer interfaces between CLI and services

### Test expansion
- [ ] Add arrangement unit tests (planner + selection semantics)
- [ ] Add arrangement CLI tests
- [ ] Add export/revert integration tests (temp dirs + collision/rollback cases)
- [ ] Add regression tests for tag inheritance + search AND semantics together
- [ ] Add performance smoke test for large scan/search datasets

## Guardrails
- Keep commands backward compatible unless explicitly breaking.
- Keep migrations additive and reversible where practical.
- Prefer deterministic ordering in all list/plan outputs.
- Require tests for every new command path and error branch.

## Session Log

### 2026-02-18
- Created this execution tracker.
- Confirmed missing arrangement/export CLI functionality is documented but not implemented.
- Implemented `sample arrangement list` (CLI + repo + migration + tests).
- Implemented `sample arrangement create` with initial sample selection via `--from-search` and/or `--from-ids`.

## Done
- `sample arrangement list`
- `sample arrangement create`
