# docs/prompts/prompt_3.md
Task (Phase 3): Scanner + `sample scan` + `sample status` (DB-aligned).

Read these docs first:
- docs/03-cli.md (scan/status behavior)
- docs/02-persistence.md (Phase 2 schema; PRAGMAs; sample identity)
- docs/01-data-model.md (Sample uniqueness key)

Scope (ONLY):
- Implement scanning a library root directory and persisting results to SQLite via Phase 2 repos.
- Implement CLI:
  - `sample scan <path> [--rescan] [--fast]`
  - `sample status`
- Do NOT implement browse/search UI beyond minimal counts (Phase 4).

Scanner requirements (DB-aligned):
- library_root:
  - ensure LibraryRoot row exists (path_norm unique)
- sample identity:
  - compute rel_path (relative to library root)
  - compute rel_path_norm (stable)
  - upsert by (library_root_id, rel_path_norm)
- capture metadata: filename, ext, size_bytes, mtime_epoch
- no hashing in Phase 3 unless explicitly requested (still deferred)

Status requirements:
- print counts: library roots, samples (and optionally last scan time if tracked)

Testing (required):
- tmp dirs with fake sample files
- scan inserts expected count
- rescan updates mtime/size via upsert

Deliverables:
- scanner module + CLI wiring updates + tests