# docs/02-persistence.md
# Persistence (Updated for Phase 2 SQLite)

## 1) What lives where
- YAML config: user preferences and defaults (paths, profile locations, default mode).
- SQLite: authoritative state (library index, tags, arrangements, exports, history).

## 2) Initialization & config mutation policy (IMPORTANT)

### 2.1 Create config on first run (safe auto-population)
If `~/.sample_manager/config.yaml` does not exist:
- Create the data directory (`~/.sample_manager/`)
- Write a default `config.yaml` template with safe defaults
- Do NOT add discovered library roots automatically
- Print a short message indicating the path created and how to edit it

Recommended explicit command:
- `sampleman init` — creates config + data dir if missing (idempotent)

### 2.2 Never silently rewrite user config
After the config exists:
- The tool MUST NOT rewrite `config.yaml` automatically during normal operations (scan/export/revert).
- Config changes happen only via explicit user actions (e.g., `sampleman config set ...`, `sampleman config add-root ...`).

Operational state MUST NOT be stored in YAML:
- scan results, tags, arrangements, exports, history belong in SQLite.

### 2.3 SQLite connection settings (UPDATED: must apply per connection)
On every SQLite connection:
- PRAGMA foreign_keys = ON
- PRAGMA journal_mode = WAL
- PRAGMA synchronous = NORMAL
- PRAGMA temp_store = MEMORY

### 2.4 Validate config paths when config already exists
- Normalize ~ and env vars
- Validate db_path parent exists (may create parent dir)
- Validate library_roots are existing directories
- Validate default_library_root exists and matches a configured root
- Default: warn and continue; strict mode fails with exit code 6
- Validation must not mutate YAML automatically

## 3) Schema versioning (UPDATED)
SQLite schema is managed through a minimal migration system:
- Table: schema_version(version INTEGER NOT NULL)
- Migration 0001 sets version to 1 after applying the initial schema
- Future migrations increment version and are applied sequentially

## 4) Phase 2 schema (Migration 0001) — canonical tables (UPDATED)
Phase 2 establishes:
- schema_version
- library_root (path + path_norm unique)
- sample (unique by library_root_id + rel_path_norm)
- tag (display + normalized uniqueness + soft delete)
- tag_alias (global normalized uniqueness)
- sample_tag (many-to-many)
- tag_parent (DAG edges; cycles forbidden by app-level check)

DB invariants (must be enforced):
- Case-insensitive uniqueness via stored *_norm columns (unique constraints on norms).
- Tags are soft deleted via tag.is_hidden=1 (default queries exclude hidden unless requested).
- Tag inheritance is a DAG:
  - forbid cycles by reachability check using a recursive CTE
  - run check + insert inside the same transaction.

## 5) Indexing strategy (Phase 2)
- sample indexes:
  - idx_sample_library_root
  - idx_sample_rel_path_norm
  - idx_sample_filename
- tag indexes:
  - idx_tag_is_hidden
  - idx_tag_name_norm
  - idx_tag_shorthand_norm
- tag_alias indexes:
  - idx_tag_alias_tag_id
  - idx_tag_alias_norm
- join table indexes:
  - idx_sample_tag_tag_id
  - idx_sample_tag_sample_id
  - idx_tag_parent_parent
  - idx_tag_parent_child

## 6) On-demand features (NOT Phase 2)
- Content hashing (sha256) computed only when explicitly requested
- Audio-derived metadata (key/BPM) deferred

## 7) Backups / portability
- SQLite DB file is portable.
- YAML config is portable but may contain absolute paths; user may need to update on new machine.