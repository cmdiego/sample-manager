# docs/01-data-model.md
# Data Model

## 1) ID strategy (UPDATED)
- Use SQLite INTEGER PRIMARY KEY row ids for core entities:
  - library_root.id, sample.id, tag.id, tag_alias.id
  - (later phases) arrangement.id, profile.id, export_profile.id, export_run.id, history_entry.id
- Sample identity (uniqueness key) is:
  - (library_root_id, rel_path_norm)
- Hashing strategy:
  - sha256 is optional and expensive; computed only on demand in a later phase (not required for Phase 2).

## 2) Entities (UPDATED)

### LibraryRoot
Fields:
- id: int
- path: str (display/original)
- path_norm: str (normalized, unique)
- created_at: str (sqlite datetime)

Constraints:
- path_norm unique

### Sample
Fields:
- id: int
- library_root_id: int
- rel_path: str (relative to library root, display)
- rel_path_norm: str (normalized relative path, used for identity)
- filename: str
- ext: str?
- size_bytes: int?
- mtime_epoch: int?
- sha256: str? (optional; later)
- pack_id: int? (optional; later)
- inferred (later):
  - category: str?
  - bpm: int?
  - key: str?
- user (later):
  - notes: str?
  - rating: int? (0-5)
- created_at: str
- updated_at: str

Constraints:
- unique (library_root_id, rel_path_norm)
- ext normalized lowercase recommended

Notes:
- Absolute path at runtime:
  - abs_path = join(library_root.path, rel_path)

### SamplePack (optional; later)
Fields:
- id: int
- name: str
- vendor: str?
- root_rel_path: str? (relative to library root)

### Tag (UPDATED: display + normalized + soft delete)
Fields:
- id: int
- name_display: str
- name_norm: str (unique; case-insensitive)
- shorthand_display: str? (optional)
- shorthand_norm: str? (unique when not null; case-insensitive)
- is_hidden: bool (0/1)  # soft delete
- is_category: bool (0/1) # optional flag
- created_at: str
- updated_at: str

Constraints:
- name_norm unique
- shorthand_norm unique (nullable)

Tag semantics:
- is_hidden=1 means tag is not shown in normal lists/resolution unless include_hidden=true.

### TagAlias (UPDATED: global uniqueness)
Fields:
- id: int
- tag_id: int
- alias_display: str
- alias_norm: str (unique globally; case-insensitive)
- created_at: str

Constraints:
- alias_norm unique globally

### SampleTag (many-to-many)
Fields:
- sample_id: int
- tag_id: int
- created_at: str
Primary key:
- (sample_id, tag_id)

### TagParent (inheritance DAG) (UPDATED)
Represents directed edges: child -> parent

Fields:
- child_tag_id: int
- parent_tag_id: int
- created_at: str
Primary key:
- (child_tag_id, parent_tag_id)

Constraints:
- child_tag_id != parent_tag_id
- Graph must be a DAG (cycles forbidden by app-level check)

Tag inheritance semantics:
- Searching/filtering for a tag expands to include descendants (parent matches descendants only).

### ArrangementProfile (later; unchanged conceptually, IDs become int)
Fields:
- id: int
- name: str (unique)
- description: str?
- layout_mode: str ("monolithic" | "hierarchical")
- layout_rules: json (see docs/04-arrangement.md)
- naming_template: str (see docs/04-arrangement.md)
- collision_policy: str ("fail" | "suffix" | "dedupe_hash")
- selection_defaults: json? (optional)
- created_at, updated_at: str

### ArrangementInstance (Arrangement) (later; IDs become int)
Fields:
- id: int
- name: str (unique)
- profile_id: int
- sample_ids: list[int] (stored as join table)
- frozen_plan_json: json? (optional snapshot)
- created_at, updated_at: str

Notes:
- Selection is the truth; plan can be recomputed deterministically.

### ExportProfile (later; IDs become int)
Fields:
- id: int
- name: str (unique)
- max_depth: int
- max_filename_len: int
- allowed_charset: str
- illegal_chars: str (regex or explicit set)
- replace_char: str (default "_")
- case_policy: str ("preserve" | "lower" | "upper")
- path_sep_policy: str ("os" | "posix")
- on_violation: str ("autofix" | "fail")
- created_at, updated_at: str

### ExportRun (later; IDs become int)
Fields:
- id: int
- arrangement_id: int
- export_profile_id: int
- export_dir: str (absolute)
- mode: str ("copy" | "symlink" | "move")  # move only with explicit opt-in
- status: str ("planned" | "applied" | "reverted" | "partial" | "failed")
- created_at, updated_at: str

### HistoryEntry (later; IDs become int)
Fields:
- id: int
- export_id: int
- plan_json: json
- stats_json: json
- errors_json: json?
- created_at: str

## 3) Relationships (logical) (UPDATED)
- Sample <-> Tag: many-to-many via sample_tag
- TagAlias -> Tag: many-to-one
- TagParent: edges between Tag rows (child → parent)
- ArrangementInstance -> ArrangementProfile: many-to-one
- ArrangementInstance <-> Sample: many-to-many (selection)
- ExportRun -> ArrangementInstance: many-to-one
- ExportRun -> ExportProfile: many-to-one
- ExportRun -> HistoryEntry: one-to-many (MVP: one entry)

## 4) Controlled vocab (optional config)
- categories: kick, snare, clap, hat, perc, fx, vocal, loop, oneshot, melodic, bass, chord, synth, etc.
- key format: "C", "Cm", "C#min", etc. (freeform allowed if parsing fails)

## 5) Normalization rules (UPDATED)
All case-insensitive comparisons are implemented by storing normalized columns.

Recommended string norm for tag-like strings:
- strip
- to lower
- collapse internal whitespace to single spaces

Example:
- "  Kick  Drum " -> "kick drum"

Path normalization:
- library_root.path_norm: normalized absolute path string (platform-safe canonicalization)
- sample.rel_path_norm: normalized relative path string (stable within root)