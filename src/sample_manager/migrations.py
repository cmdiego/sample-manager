"""Schema migrations for Sample Manager SQLite database.

Manages schema_version table and applies sequential migrations.
Migration 0001 DDL is copied verbatim from docs/appendix-phase2-ddl-and-ctes.md (Appendix A).
"""

from __future__ import annotations

from .db import Db


def ensure_schema_version(db: Db) -> int:
    """Create schema_version table if missing, seed with 0 if empty, return current version.

    Per docs/02-persistence.md §3 and Appendix A.1.
    """
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    db.execute(
        "INSERT INTO schema_version(version) "
        "SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM schema_version)"
    )
    db.conn.commit()
    version = db.fetchval("SELECT version FROM schema_version")
    return version


def apply_migrations(db: Db) -> int:
    """Apply all pending migrations sequentially.

    Returns the final schema version after applying migrations.
    """
    current = ensure_schema_version(db)

    migrations = [
        _migration_0001,
        _migration_0002,
        _migration_0003,
        _migration_0004,
        _migration_0005,
        _migration_0006,
    ]

    for target_version, migrate_fn in enumerate(migrations, start=1):
        if current < target_version:
            migrate_fn(db)
            current = target_version

    return current


# ---------------------------------------------------------------------------
# Migration 0001 — Phase 2 initial schema
# DDL copied verbatim from docs/appendix-phase2-ddl-and-ctes.md Appendix A
# ---------------------------------------------------------------------------

_MIGRATION_0001_SQL = """\
-- A.2 library_root
CREATE TABLE IF NOT EXISTS library_root (
  id            INTEGER PRIMARY KEY,
  path          TEXT NOT NULL,
  path_norm     TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  CONSTRAINT uq_library_root_path_norm UNIQUE (path_norm)
);

-- A.3 sample
CREATE TABLE IF NOT EXISTS sample (
  id              INTEGER PRIMARY KEY,
  library_root_id INTEGER NOT NULL,
  rel_path        TEXT NOT NULL,
  rel_path_norm   TEXT NOT NULL,
  filename        TEXT NOT NULL,
  ext             TEXT,
  size_bytes      INTEGER,
  mtime_epoch     INTEGER,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_sample_library_root
    FOREIGN KEY (library_root_id) REFERENCES library_root(id)
    ON DELETE CASCADE,

  CONSTRAINT uq_sample_path UNIQUE (library_root_id, rel_path_norm)
);

CREATE INDEX IF NOT EXISTS idx_sample_library_root ON sample(library_root_id);
CREATE INDEX IF NOT EXISTS idx_sample_rel_path_norm ON sample(rel_path_norm);
CREATE INDEX IF NOT EXISTS idx_sample_filename ON sample(filename);

-- A.4 tag
CREATE TABLE IF NOT EXISTS tag (
  id                INTEGER PRIMARY KEY,
  name_display       TEXT NOT NULL,
  name_norm          TEXT NOT NULL,
  shorthand_display  TEXT,
  shorthand_norm     TEXT,
  is_hidden          INTEGER NOT NULL DEFAULT 0,
  is_category        INTEGER NOT NULL DEFAULT 0,
  created_at         TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at         TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT uq_tag_name_norm UNIQUE (name_norm),
  CONSTRAINT uq_tag_shorthand_norm UNIQUE (shorthand_norm),
  CONSTRAINT ck_tag_is_hidden CHECK (is_hidden IN (0,1)),
  CONSTRAINT ck_tag_is_category CHECK (is_category IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_tag_is_hidden ON tag(is_hidden);
CREATE INDEX IF NOT EXISTS idx_tag_name_norm ON tag(name_norm);
CREATE INDEX IF NOT EXISTS idx_tag_shorthand_norm ON tag(shorthand_norm);

-- A.5 tag_alias
CREATE TABLE IF NOT EXISTS tag_alias (
  id            INTEGER PRIMARY KEY,
  tag_id        INTEGER NOT NULL,
  alias_display TEXT NOT NULL,
  alias_norm    TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_tag_alias_tag
    FOREIGN KEY (tag_id) REFERENCES tag(id)
    ON DELETE CASCADE,

  CONSTRAINT uq_tag_alias_norm UNIQUE (alias_norm)
);

CREATE INDEX IF NOT EXISTS idx_tag_alias_tag_id ON tag_alias(tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_alias_norm ON tag_alias(alias_norm);

-- A.6 sample_tag
CREATE TABLE IF NOT EXISTS sample_tag (
  sample_id  INTEGER NOT NULL,
  tag_id     INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_sample_tag_sample
    FOREIGN KEY (sample_id) REFERENCES sample(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_sample_tag_tag
    FOREIGN KEY (tag_id) REFERENCES tag(id)
    ON DELETE CASCADE,

  CONSTRAINT pk_sample_tag PRIMARY KEY (sample_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_sample_tag_tag_id ON sample_tag(tag_id);
CREATE INDEX IF NOT EXISTS idx_sample_tag_sample_id ON sample_tag(sample_id);

-- A.7 tag_parent
CREATE TABLE IF NOT EXISTS tag_parent (
  child_tag_id  INTEGER NOT NULL,
  parent_tag_id INTEGER NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_tag_parent_child
    FOREIGN KEY (child_tag_id) REFERENCES tag(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_tag_parent_parent
    FOREIGN KEY (parent_tag_id) REFERENCES tag(id)
    ON DELETE CASCADE,

  CONSTRAINT pk_tag_parent PRIMARY KEY (child_tag_id, parent_tag_id),
  CONSTRAINT ck_tag_parent_not_self CHECK (child_tag_id <> parent_tag_id)
);

CREATE INDEX IF NOT EXISTS idx_tag_parent_parent ON tag_parent(parent_tag_id);
CREATE INDEX IF NOT EXISTS idx_tag_parent_child ON tag_parent(child_tag_id);
"""


def _migration_0001(db: Db) -> None:
    """Apply Migration 0001: create all Phase 2 tables and indexes.

    Runs DDL inside a transaction and updates schema_version to 1 (Appendix A.8).
    """
    with db.transaction():
        # executescript can't be used here (it issues implicit COMMIT)
        # Instead, execute each statement individually within the transaction.
        for statement in _split_sql_statements(_MIGRATION_0001_SQL):
            db.execute(statement)

        # A.8 final step
        db.execute("UPDATE schema_version SET version = 1")


# ---------------------------------------------------------------------------
# Migration 0002 — Phase 7 arrangement tables
# ---------------------------------------------------------------------------

_MIGRATION_0002_SQL = """\
CREATE TABLE IF NOT EXISTS arrangement (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  name_norm     TEXT NOT NULL,
  profile_name  TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT uq_arrangement_name_norm UNIQUE (name_norm)
);

CREATE INDEX IF NOT EXISTS idx_arrangement_name_norm ON arrangement(name_norm);

CREATE TABLE IF NOT EXISTS arrangement_sample (
  arrangement_id INTEGER NOT NULL,
  sample_id      INTEGER NOT NULL,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_arrangement_sample_arrangement
    FOREIGN KEY (arrangement_id) REFERENCES arrangement(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_arrangement_sample_sample
    FOREIGN KEY (sample_id) REFERENCES sample(id)
    ON DELETE CASCADE,

  CONSTRAINT pk_arrangement_sample PRIMARY KEY (arrangement_id, sample_id)
);

CREATE INDEX IF NOT EXISTS idx_arrangement_sample_arrangement_id
ON arrangement_sample(arrangement_id);
CREATE INDEX IF NOT EXISTS idx_arrangement_sample_sample_id
ON arrangement_sample(sample_id);
"""


def _migration_0002(db: Db) -> None:
    """Apply Migration 0002: create arrangement tables."""
    with db.transaction():
        for statement in _split_sql_statements(_MIGRATION_0002_SQL):
            db.execute(statement)

        db.execute("UPDATE schema_version SET version = 2")


# ---------------------------------------------------------------------------
# Migration 0003 — Selection buffer table
# ---------------------------------------------------------------------------

_MIGRATION_0003_SQL = """\
CREATE TABLE IF NOT EXISTS selection_sample (
  sample_id      INTEGER PRIMARY KEY,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_selection_sample_sample
    FOREIGN KEY (sample_id) REFERENCES sample(id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_selection_sample_created_at
ON selection_sample(created_at);
"""


def _migration_0003(db: Db) -> None:
    """Apply Migration 0003: create persistent selection buffer table."""
    with db.transaction():
        for statement in _split_sql_statements(_MIGRATION_0003_SQL):
            db.execute(statement)

        db.execute("UPDATE schema_version SET version = 3")


# ---------------------------------------------------------------------------
# Migration 0004 — Export run + history tables
# ---------------------------------------------------------------------------

_MIGRATION_0004_SQL = """\
CREATE TABLE IF NOT EXISTS export_run (
  id                   INTEGER PRIMARY KEY,
  arrangement_id       INTEGER NOT NULL,
  export_profile_name  TEXT NOT NULL,
  export_dir           TEXT NOT NULL,
  mode                 TEXT NOT NULL,
  status               TEXT NOT NULL,
  created_at           TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at           TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_export_run_arrangement
    FOREIGN KEY (arrangement_id) REFERENCES arrangement(id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_export_run_arrangement_id
ON export_run(arrangement_id);
CREATE INDEX IF NOT EXISTS idx_export_run_status
ON export_run(status);

CREATE TABLE IF NOT EXISTS history_entry (
  id          INTEGER PRIMARY KEY,
  export_id   INTEGER NOT NULL,
  plan_json   TEXT NOT NULL,
  stats_json  TEXT NOT NULL,
  errors_json TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_history_entry_export
    FOREIGN KEY (export_id) REFERENCES export_run(id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_entry_export_id
ON history_entry(export_id);
"""


def _migration_0004(db: Db) -> None:
    """Apply Migration 0004: create export and history tables."""
    with db.transaction():
        for statement in _split_sql_statements(_MIGRATION_0004_SQL):
            db.execute(statement)

        db.execute("UPDATE schema_version SET version = 4")


# ---------------------------------------------------------------------------
# Migration 0005 — Virtual arrangement folders and sample placement
# ---------------------------------------------------------------------------

_MIGRATION_0005_SQL = """\
CREATE TABLE IF NOT EXISTS arrangement_folder (
  id              INTEGER PRIMARY KEY,
  arrangement_id  INTEGER NOT NULL,
  parent_id       INTEGER NULL,
  name            TEXT NOT NULL,
  name_norm       TEXT NOT NULL,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_arrangement_folder_arrangement
    FOREIGN KEY (arrangement_id) REFERENCES arrangement(id)
    ON DELETE CASCADE,

  CONSTRAINT fk_arrangement_folder_parent
    FOREIGN KEY (parent_id) REFERENCES arrangement_folder(id)
    ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_arrangement_folder_root_sibling
ON arrangement_folder(arrangement_id, name_norm)
WHERE parent_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_arrangement_folder_nested_sibling
ON arrangement_folder(arrangement_id, parent_id, name_norm)
WHERE parent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_arrangement_folder_tree_loading
ON arrangement_folder(arrangement_id, parent_id, sort_order, name_norm);

ALTER TABLE arrangement_sample ADD COLUMN folder_id INTEGER NULL
  REFERENCES arrangement_folder(id) ON DELETE SET NULL;

ALTER TABLE arrangement_sample ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_arrangement_sample_folder_id
ON arrangement_sample(folder_id);
"""


def _migration_0005(db: Db) -> None:
    """Apply Migration 0005: add virtual folders and sample placement to arrangements."""
    with db.transaction():
        for statement in _split_sql_statements(_MIGRATION_0005_SQL):
            db.execute(statement)

        db.execute("UPDATE schema_version SET version = 5")


# ---------------------------------------------------------------------------
# Migration 0006 — Scan-time audio analysis (v2 milestone 2)
# ---------------------------------------------------------------------------

_MIGRATION_0006_SQL = """\
CREATE TABLE IF NOT EXISTS sample_analysis (
  sample_id         INTEGER PRIMARY KEY,
  size_bytes        INTEGER NOT NULL,
  mtime_ns          INTEGER NOT NULL,
  analysis_version  INTEGER NOT NULL,
  sample_rate       INTEGER NOT NULL,
  channels          INTEGER NOT NULL,
  frames            INTEGER NOT NULL,
  duration_seconds  REAL NOT NULL,
  peak              REAL NOT NULL,
  rms               REAL NOT NULL,
  loudness_lufs     REAL NULL,
  short_term_max_lufs REAL NULL,
  peak_levels       TEXT NOT NULL,
  peaks             BLOB NOT NULL,
  analyzed_at       TEXT NOT NULL DEFAULT (datetime('now')),

  CONSTRAINT fk_sample_analysis_sample
    FOREIGN KEY (sample_id) REFERENCES sample(id)
    ON DELETE CASCADE
);
"""


def _migration_0006(db: Db) -> None:
    """Apply Migration 0006: store peak pyramids and loudness per sample.

    Rows are valid only while ``(size_bytes, mtime_ns)`` match the file on
    disk; ``analysis_version`` invalidates rows when the algorithm changes.
    """
    with db.transaction():
        for statement in _split_sql_statements(_MIGRATION_0006_SQL):
            db.execute(statement)

        db.execute("UPDATE schema_version SET version = 6")


def _split_sql_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL string into individual statements.

    Handles comments and empty lines. Simple splitter on semicolons
    (sufficient for DDL without triggers or complex constructs).
    """
    statements = []
    for raw in sql.split(";"):
        # Remove comments and strip
        lines = []
        for line in raw.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("--"):
                lines.append(line)
            elif not stripped:
                # Keep empty lines that are between content (whitespace only)
                pass
        cleaned = "\n".join(lines).strip()
        if cleaned:
            statements.append(cleaned)
    return statements
