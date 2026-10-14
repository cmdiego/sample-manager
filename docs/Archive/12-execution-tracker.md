# Execution Tracker

Purpose: drive iterative delivery while we keep testing the app.

## Current Goals
- Prioritize foundational functionality before full TUI implementation.
- Complete arrangement/export/revert core flows first.
- Keep a limited, read-only TUI spike as an optional parallel track to validate UX/tooling.
- Define a shared file-traversal model with Vim-style movement and arrow-key parity.

## Priority Order
1. Complete core CLI/domain functionality (`arrangement`, `export`, `revert`).
2. Stabilize service/repo interfaces and JSON output contracts.
3. Build TUI on top of stable APIs.

## Workflow Loop (repeat each cycle)
1. Pick 1-2 scoped items from "Active Queue".
2. Implement with tests first (or in lockstep).
3. Run focused tests, then full suite.
4. Record outcomes in "Session Log".
5. Move completed items to "Done".

## Active Queue

### High-priority additions
- [x] Add selection workflow from `browse`/`search` results (select/unselect sample IDs)
- [x] Add CLI commands for selection buffer management (`selection add/remove/list/clear`)
- [ ] Allow piping/feeding `search --json` IDs directly into arrangement create/add flows
- [ ] Add result-level affordances: quick select/unselect by current query (`--from-search`)
- [ ] Add file traversal navigation with `h/j/k/l` and arrow-key equivalents
- [x] Add tests for selection buffer persistence + idempotent select/unselect behavior
- [x] Add `sampleman arrangement show <name>` with stable JSON output contract
- [x] Add `sampleman arrangement add <name>` with idempotent attach semantics
- [x] Add `sampleman arrangement remove <name>` with clear not-found reporting
- [x] Add `sampleman arrangement preview <name>` deterministic ordering + collision diagnostics
- [x] Implement `sampleman export ... --confirm` safety gate and dry-run mode
- [x] Implement `sampleman revert --export-id <id>` with partial-failure reporting (`ERROR_PARTIAL_OPERATION`)
- [x] Add migration for `export_run` and `history_entry` tables
- [x] Add export/revert service layer (separate from CLI) with transaction boundaries
- [x] Add integration tests for export/revert rollback and crash recovery
- [x] Add golden tests for deterministic plan output bytes (same input => same output)

### Missing functionality
- [x] Implement `sampleman arrangement list`
- [x] Implement `sampleman arrangement create <name> --profile <profile-name> [--from-search ...] [--from-ids ...]`
- [x] Implement `sampleman arrangement show <name>`
- [x] Implement `sampleman arrangement add <name> ...`
- [x] Implement `sampleman arrangement remove <name> ...`
- [x] Implement `sampleman arrangement preview <name> [--export-profile ...] [--format ...]`
- [x] Implement `sampleman export <arrangement-name> --to <dir> --export-profile <name> [--mode ...]`
- [x] Implement `sampleman revert --export-id <id>`

### TUI track (defer full build until core is stable)
- [ ] TUI spike (read-only): browse/search/status screens only
- [ ] TUI navigation model: focused-item movement, parent/child traversal, and keybinding parity
- [ ] Evaluate TUI library + architecture fit with current service/repo layer
- [ ] Define TUI data adapters against stable JSON/service contracts
- [ ] Implement mutation flows in TUI only after CLI core export/revert is complete

### Data/model work needed for arrangements/export
- [x] Add arrangement/export tables + migrations
- [x] Add arrangement/export repositories
- [ ] Define immutable/export history payload format
- [x] Add idempotency + recovery behavior for partial export/revert

### Refactor candidates
- [x] Split `src/sample_manager/cli.py` into modular command files (`commands/config.py`, `commands/tag.py`, etc.)
- [ ] Standardize CLI output helpers (table/json/error envelope)
- [ ] Consolidate DB bootstrap patterns (`_get_db`, config checks) into shared utility
- [ ] Improve typing coverage for service/repo boundaries
- [ ] Add clearer domain-layer interfaces between CLI and services

### Test expansion
- [x] Add arrangement unit tests (planner + selection semantics)
- [x] Add arrangement CLI tests
- [x] Add export/revert integration tests (temp dirs + collision/rollback cases)
- [ ] Add regression tests for tag inheritance + search AND semantics together
- [ ] Add performance smoke test for large scan/search datasets

## Delivered In Sprint
- Added `selection` workflow commands: `add/remove/list/clear` with `--from-search`.
- Extended `arrangement` commands: `show`, `add`, `remove`, `preview`, and `create --from-selection`.
- Added safe `export` and `revert` flows with `--dry-run`/`--confirm` gates.
- Added deterministic plan builder and execution/revert service layer.
- Added migration `0004` with `export_run` + `history_entry` tables (schema version now 4).
- Added/expanded repos for arrangement detail ops and export/history persistence.
- Refactored arrangement/selection/export/revert command registration into `src/sample_manager/commands/arrangement_commands.py`.
- Full test suite status after changes: `433 passed`.

## Guardrails
- Keep commands backward compatible unless explicitly breaking.
- Keep migrations additive and reversible where practical.
- Prefer deterministic ordering in all list/plan outputs.
- Require tests for every new command path and error branch.

## Session Log

### 2026-02-18
- Created this execution tracker.
- Confirmed missing arrangement/export CLI functionality is documented but not implemented.
- Implemented `sampleman arrangement list` (CLI + repo + migration + tests).
- Implemented `sampleman arrangement create` with initial sampleman selection via `--from-search` and/or `--from-ids`.
- Aligned roadmap: foundation-first delivery, with optional read-only TUI spike before full TUI.
- Implemented persistent selection buffer with `sampleman selection add/remove/list/clear` and `--from-search` selection paths.
- Implemented `arrangement show/add/remove/preview`, `create --from-selection`, and `export`/`revert` safety workflows with history persistence.
- Added command-module refactor for arrangement/selection/export/revert in `src/sample_manager/commands/arrangement_commands.py`.
- Added export/history persistence (`export_run`, `history_entry`) and validated with full suite (`433 passed`).

### 2026-06-21
- Added the file traversal planning goal to the tracker.
- Clarified the navigation workstream as shared `h/j/k/l` plus arrow-key equivalents.

## Done
- `sampleman arrangement list`
- `sampleman arrangement create`
- `sampleman arrangement show`
- `sampleman arrangement add`
- `sampleman arrangement remove`
- `sampleman arrangement preview`
- `sampleman export` (with `--dry-run` / `--confirm`)
- `sampleman revert --export-id` (with partial-error semantics)
- `sampleman selection add/remove/list/clear`
