# Sample Manager — Phase 2 Appendix: DDL + Recursive CTEs

This file contains the canonical Phase 2 SQLite **Migration 0001 DDL** and the canonical **recursive CTE queries** used for tag inheritance and cycle checks.

---

# Appendix A — Migration 0001 DDL (Exact SQL)

> Implement this DDL exactly.

## A.1 schema_version

```sql
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL
);

INSERT INTO schema_version(version)
SELECT 0
WHERE NOT EXISTS (SELECT 1 FROM schema_version);
```

## A.2 library_root

```sql
CREATE TABLE IF NOT EXISTS library_root (
  id            INTEGER PRIMARY KEY,
  path          TEXT NOT NULL,
  path_norm     TEXT NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  CONSTRAINT uq_library_root_path_norm UNIQUE (path_norm)
);
```

## A.3 sample (path-based identity)

```sql
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
```

## A.4 tag (display + normalized uniqueness + soft delete)

```sql
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
```

## A.5 tag_alias (globally unique normalized alias)

```sql
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
```

## A.6 sample_tag (many-to-many)

```sql
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
```

## A.7 tag_parent (inheritance DAG edges: child -> parent)

```sql
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
```

## A.8 Migration final step

```sql
UPDATE schema_version SET version = 1;
```

---

# Appendix B — Canonical Recursive CTE Queries

## B.1 Descendants of a tag (including itself)

```sql
WITH RECURSIVE
  descendants(tag_id) AS (
    SELECT :root_tag_id
    UNION
    SELECT tp.child_tag_id
    FROM tag_parent tp
    JOIN descendants d ON d.tag_id = tp.parent_tag_id
  )
SELECT tag_id FROM descendants;
```

## B.2 Cycle check before inserting edge (child -> parent)

Reject the edge if parent is already a descendant of child:

```sql
WITH RECURSIVE
  descendants(tag_id) AS (
    SELECT :child_tag_id
    UNION
    SELECT tp.child_tag_id
    FROM tag_parent tp
    JOIN descendants d ON d.tag_id = tp.parent_tag_id
  )
SELECT 1
FROM descendants
WHERE tag_id = :parent_tag_id
LIMIT 1;
```

Notes:
- The cycle check must run in the same transaction as the edge insert.
- If the query returns a row, reject the edge (it would create a cycle).
