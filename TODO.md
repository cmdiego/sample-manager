## Implementation Plan (Sequential Checklist)

> Goal: build Sample Manager in thin, testable vertical slices to minimize rework and keep agent prompts small.

### Phase 0 — Project scaffolding
- [ ] Create Python package layout: `src/sample_manager/`
- [ ] Add `pyproject.toml` (deps: `typer`, `pyyaml`, `pytest`; optional: `pydantic`)
- [ ] Add `tests/` and configure `pytest`
- [ ] Add minimal `README.md` sections: install, run, commands
- [ ] (Optional) Add tooling: `ruff`, `black`, `mypy`

---

### Phase 1 — Config + init/validate (foundation)
- [ ] Implement OS-specific data dir resolution: `~/.sample_manager/` (Windows: `%USERPROFILE%\.sample_manager\`)
- [ ] Implement `ConfigLoader`:
  - [ ] Create default `config.yaml` if missing (template from `docs/02-persistence.md`)
  - [ ] Load YAML and normalize paths (expand `~`, env vars, absolute paths)
  - [ ] Validate configured paths (per `docs/02-persistence.md` §2.4)
- [ ] Implement CLI commands (Typer):
  - [ ] `sample init`
  - [ ] `sample config validate [--strict] [--json]`
  - [ ] `sample config show [--json]`
  - [ ] `sample config set <key> <value>`
  - [ ] `sample config add-root <path> [--set-default]`
  - [ ] `sample config remove-root <path>`
  - [ ] `sample config set-default <path>`
- [ ] Add tests:
  - [ ] Missing config → created
  - [ ] Invalid library roots → warn; strict → exit code 6
  - [ ] `db_path` parent handling (create or warn, per chosen policy)

---

### Phase 2 — SQLite bootstrap + repository layer
- [ ] Implement `Db` wrapper:
  - [ ] Connect using `db_path`
  - [ ] Enable `PRAGMA foreign_keys = ON`
- [ ] Implement schema bootstrap/migrations using DDL from `docs/02-persistence.md`
- [ ] Implement minimal repository layer:
  - [ ] `LibraryRootRepo` (get-or-create by path)
  - [ ] `SampleRepo` (upsert by library_root_id + path)
  - [ ] `TagRepo` + `SampleTagRepo`
  - [ ] `ArrangementProfileRepo`
  - [ ] `ArrangementRepo` + `ArrangementSampleRepo`
  - [ ] `ExportProfileRepo`
  - [ ] `ExportRunRepo`
  - [ ] `HistoryRepo`
- [ ] Add tests:
  - [ ] DB bootstrap creates tables
  - [ ] Sample upsert round-trip works

---

### Phase 3 — Scan MVP (first usable workflow)
- [ ] Implement `Scanner`:
  - [ ] Walk library root recursively with `pathlib`
  - [ ] Filter sample extensions (configurable list)
  - [ ] Extract metadata: rel_path, filename, ext, size, mtime
  - [ ] (Optional) basic category inference from filename/path keywords
- [ ] Persist scan results:
  - [ ] Create/resolve `library_root_id`
  - [ ] Upsert samples in batches
- [ ] Implement CLI commands:
  - [ ] `sample scan <path> [--rescan] [--fast]`
  - [ ] `sample status` (counts; last scan time if tracked)
- [ ] Add tests:
  - [ ] Scan tempdir inserts correct samples
  - [ ] Rescan updates changed metadata

---

### Phase 4 — Search + browse
- [ ] Implement `SearchEngine` (SQL-backed):
  - [ ] Name search (LIKE/glob; regex later if needed)
  - [ ] Filter by category
  - [ ] Filter by tag (join)
- [ ] Implement CLI commands:
  - [ ] `sample search ... [--json]`
  - [ ] `sample browse [--page N --page-size M] [--sort ...]`
- [ ] Add tests:
  - [ ] Search by name/category/tag returns stable results

---

### Phase 5 — Tagging (manual + bulk)
- [ ] Implement tag operations:
  - [ ] `sample tag add <sample-id> <tag>`
  - [ ] `sample tag remove <sample-id> <tag>`
  - [ ] `sample tag bulk --from-search "<query>" --add <tag> [--remove <tag>]`
- [ ] (Optional) auto-tag heuristic helper (filename patterns)
- [ ] Add tests:
  - [ ] Add/remove tag updates join table
  - [ ] Bulk tagging is idempotent

---

### Phase 6 — Profiles (arrangement/export)
- [ ] Implement profile loaders:
  - [ ] Load `profiles/arrangement_profiles.yaml`
  - [ ] Load `profiles/export_profiles.yaml`
  - [ ] Validate required fields
- [ ] (Optional) persist profiles into SQLite (sync on startup or explicit command)
- [ ] Implement CLI commands:
  - [ ] `sample profile list/show`
  - [ ] `sample export-profile list/show`
- [ ] Add tests:
  - [ ] Profile parsing + validation
  - [ ] Export constraints loaded correctly

---

### Phase 7 — Arrangements (saved selection)
- [ ] Implement `ArrangementManager`:
  - [ ] Create arrangement from search results or explicit IDs
  - [ ] Add/remove sample IDs
  - [ ] List/show arrangements
- [ ] Implement CLI commands:
  - [ ] `sample arrangement create ...`
  - [ ] `sample arrangement add/remove ...`
  - [ ] `sample arrangement list`
- [ ] Add tests:
  - [ ] Arrangement create persists selection
  - [ ] Add/remove updates selection deterministically

---

### Phase 8 — Planning (Plan is the core abstraction)
- [ ] Implement template rendering (`naming_template`) per `docs/04-arrangement.md`:
  - [ ] Placeholder substitution + bucket mapping
  - [ ] Stable `{index}` assignment
- [ ] Implement sanitization + constraints:
  - [ ] illegal char replacement + case policy
  - [ ] filename length truncation preserving extension
- [ ] Implement collision policies: fail / suffix / dedupe_hash
- [ ] Implement `ArrangementEngine.compute_plan(...) -> Plan` (pure, deterministic)
- [ ] Implement CLI command:
  - [ ] `sample arrangement preview <name> [--export-profile <name>] [--format table|json]`
- [ ] Add tests (high priority):
  - [ ] Determinism (same inputs → same outputs)
  - [ ] Collisions resolved per policy
  - [ ] Sanitization/truncation correctness

---

### Phase 9 — Export + History
- [ ] Implement filesystem abstraction `FilesystemOps` (docs/06)
- [ ] Implement `ExportService.apply(plan, mode)`:
  - [ ] mkdir ops
  - [ ] copy/symlink (move only with explicit confirmation)
  - [ ] idempotency rules
- [ ] Persist `ExportRun` + `HistoryEntry.plan_json` + stats/errors
- [ ] Implement CLI commands:
  - [ ] `sample export <arrangement> --to <dir> --export-profile <name> [--mode ...] [--confirm]`
  - [ ] `sample export last`
- [ ] Add tests:
  - [ ] Export creates expected files in tempdir
  - [ ] History is saved and linked to export_id

---

### Phase 10 — Revert (must be rock solid)
- [ ] Implement `RevertService.revert(export_id | last)`:
  - [ ] Load `HistoryEntry.plan_json`
  - [ ] Reverse operations in reverse order
  - [ ] `--continue-on-error` behavior
  - [ ] Update export status reverted/partial/failed
- [ ] Implement CLI commands:
  - [ ] `sample revert --export-id <id> [--confirm] [--continue-on-error]`
  - [ ] `sample revert last [--confirm]`
- [ ] Add tests:
  - [ ] Revert deletes artifacts for copy/symlink exports
  - [ ] Revert is idempotent (run twice → OK)
  - [ ] Partial failure behavior works as specified

---

### Phase 11 — Hardening + UX polish
- [ ] Ensure consistent JSON schemas for all `--json` outputs
- [ ] Improve error messages and align exit codes (docs/03)
- [ ] Add `--force` where appropriate (export overwrite / revert force-delete)
- [ ] Performance:
  - [ ] Batch DB writes on scan
  - [ ] Verify indexes support common searches
- [ ] (Optional) Minimal CI: run tests on push
