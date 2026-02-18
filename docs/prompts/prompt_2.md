# docs/prompts/prompt_2.md
Task (Phase 2): SQLite bootstrap + migrations + repository layer (UPDATED DB design).

Read these docs first (source of truth):
- docs/02-persistence.md (Appendix A + B see file `appendix-phase2-ddl-and-ctes.md`; canonical DDL + CTEs)
- docs/01-data-model.md (IDs are ints; sample identity is (library_root_id, rel_path_norm))
- docs/06-ops-safety.md (safe behavior principles, even though Phase 2 is DB-only)

Scope (ONLY):
- Implement DB connection PRAGMAs (must run per-connection):
  - foreign_keys=ON
  - journal_mode=WAL
  - synchronous=NORMAL
  - temp_store=MEMORY
- Implement minimal migrations system using schema_version(version INTEGER NOT NULL):
  - create schema_version if missing and insert 0 row if empty
  - apply Migration 0001 exactly as in docs/02 Appendix A
  - update schema_version to 1 at end of migration
- Implement Db wrapper (sqlite3 stdlib) + minimal repo layer for:
  - library_root
  - sample
  - tag
  - tag_alias
  - sample_tag
  - tag_parent
- Implement TagGraphService for:
  - descendants_including_self(root_tag_id)
  - expand_for_search(tag_ids) (parent matches descendants only)
- Do NOT implement scanning/search/arrangements/export/revert CLI features in this phase.

Rules / invariants:
- SQLite IDs are INTEGER PRIMARY KEY; treat them as ints everywhere.
- Case-insensitive uniqueness must be done via stored *_norm columns:
  - tag.name_norm unique
  - tag.shorthand_norm unique (nullable)
  - tag_alias.alias_norm unique globally
- Tag soft delete:
  - tag.is_hidden = 1 marks hidden; normal list/resolve excludes hidden unless include_hidden=True
- Tag inheritance:
  - tag_parent edges are child -> parent and form a DAG
  - cycles must be forbidden via recursive CTE cycle-check (docs/02 Appendix B)
  - cycle check and insert must occur within a single transaction
- Samples:
  - stored relative to library root
  - unique key is (library_root_id, rel_path_norm)
  - hashing is NOT required in Phase 2 (defer)

Implementation expectations (suggested layout; adjust as needed):
- src/sample_manager/db.py
  - connect/open (path from config)
  - apply PRAGMAs
  - execute/fetch helpers
  - transaction context manager (BEGIN ... COMMIT/ROLLBACK)
- src/sample_manager/migrations.py
  - ensure_schema_version()
  - apply_migrations()
  - migration_0001()
- src/sample_manager/normalize.py
  - norm_text(s): lower/strip/collapse whitespace
  - norm_rel_path(p): stable normalized relative path
  - norm_abs_path(p): stable normalized absolute path (for library_root.path_norm)
- src/sample_manager/repos/
  - library_root_repo.py
  - sample_repo.py
  - tag_repo.py
  - tag_alias_repo.py
  - sample_tag_repo.py
  - tag_parent_repo.py
- src/sample_manager/tag_graph.py
  - TagGraphService with recursive CTE queries for descendants and cycle-check support

Repo behavior requirements:
- LibraryRootRepo:
  - get_or_create(path) -> LibraryRootRow
  - store path_norm (unique)
- SampleRepo:
  - upsert by (library_root_id, rel_path_norm)
  - update size_bytes/mtime_epoch/filename/ext and updated_at
- TagRepo:
  - create/get by name_norm
  - set shorthand (with uniqueness)
  - hide/unhide via is_hidden
  - list(include_hidden=False)
- TagAliasRepo:
  - add alias (global unique alias_norm)
  - remove alias
  - resolve(alias_or_name) -> tag_id (name/shorthand/alias; case-insensitive)
- SampleTagRepo:
  - attach (idempotent via INSERT OR IGNORE)
  - detach
  - list tags for sample
- TagParentRepo:
  - add_parent(child, parent) with:
    - reject self-edge
    - run cycle-check CTE
    - insert edge in same transaction if safe
  - remove edge
  - list parents/children
- TagGraphService:
  - descendants_including_self(tag_id)
  - expand_for_search(tag_ids): union all descendants (parents match descendants only)

Testing (required):
- Use tmp_path DB per test.
- Validate schema exists by inspecting sqlite_master.
- Validate unique constraints: tag name_norm, shorthand_norm, alias_norm.
- Validate soft delete is_hidden behavior (list/resolve respects include_hidden).
- Validate sample upsert updates metadata.
- Validate sample_tag attach idempotency.
- Validate tag_parent descendants query works and cycle insertion is rejected.

Deliverables:
- Implementation under src/sample_manager/
- Tests under tests/
- Keep changes restricted to Phase 2 scope
- Summarize files created/modified and provide commands to run tests