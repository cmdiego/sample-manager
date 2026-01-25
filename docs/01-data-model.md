# Data Model

## 1) ID strategy
- Use UUIDv4 strings for all primary entities:
  - sample_id, tag_id, arrangement_id, profile_id, export_profile_id, export_id, history_id
- IDs are stable across rescans; samples keep a stable ID derived by persistence layer:
  - Preferred: store sample_id in DB and match files by (device+inode) when possible, else by canonical path hash.
  - Simpler MVP: sample_id is DB-generated and rescans update by canonical absolute path.

## 2) Entities

### Sample
Fields:
- id: str (uuid)
- path: str (absolute canonical path)
- rel_path: str (path relative to library root)
- filename: str
- ext: str
- size_bytes: int
- mtime_epoch: int
- sha256: str? (optional, expensive; computed only when requested)
- pack_id: str? (optional)
- inferred:
  - category: str? (kick/snare/loop/etc)
  - bpm: int? (optional)
  - key: str? (optional)
- user:
  - notes: str?
  - rating: int? (0-5)
- created_at_epoch, updated_at_epoch: int

Constraints:
- path unique within a library root (MVP)
- ext normalized lowercase
- category from controlled vocab if configured (else freeform)

### SamplePack (optional in MVP; can be derived from folder)
Fields:
- id: str
- name: str
- vendor: str?
- root_rel_path: str? (relative to library root)
- created_at_epoch

### Tag
Fields:
- id: str
- name: str (unique, case-insensitive)
- kind: str ("user" | "auto")
- created_at_epoch

### ArrangementProfile
Fields:
- id: str
- name: str (unique)
- description: str?
- layout_mode: str ("monolithic" | "hierarchical")
- layout_rules: json (see docs/04-arrangement.md)
- naming_template: str (template language; see docs/04-arrangement.md)
- collision_policy: str ("fail" | "suffix" | "dedupe_hash")
- selection_defaults: json? (optional)
- created_at_epoch, updated_at_epoch

### ArrangementInstance (Arrangement)
Fields:
- id: str
- name: str (unique)
- profile_id: str
- sample_ids: list[str] (stored as join table)
- frozen_plan_json: json? (optional: store computed plan snapshot)
- created_at_epoch, updated_at_epoch

Notes:
- Selection is the truth; plan can be recomputed deterministically.

### ExportProfile
Fields:
- id: str
- name: str (unique)
- max_depth: int
- max_filename_len: int
- allowed_charset: str (e.g., "ascii_safe")
- illegal_chars: str (regex or explicit set)
- replace_char: str (default "_")
- case_policy: str ("preserve" | "lower" | "upper")
- path_sep_policy: str ("os" | "posix") for export dir layout rendering
- on_violation: str ("autofix" | "fail")
- created_at_epoch, updated_at_epoch

### ExportRun (Export)
Fields:
- id: str
- arrangement_id: str
- export_profile_id: str
- export_dir: str (absolute path)
- mode: str ("copy" | "symlink" | "move")  # move only with explicit opt-in
- status: str ("planned" | "applied" | "reverted" | "partial" | "failed")
- created_at_epoch, updated_at_epoch

### HistoryEntry
Fields:
- id: str
- export_id: str
- plan_json: json (full plan + resolved paths)
- stats_json: json (counts, conflicts)
- errors_json: json? (if any)
- created_at_epoch

## 3) Relationships (logical)
- Sample <-> Tag: many-to-many
- ArrangementInstance -> ArrangementProfile: many-to-one
- ArrangementInstance <-> Sample: many-to-many (selection)
- ExportRun -> ArrangementInstance: many-to-one
- ExportRun -> ExportProfile: many-to-one
- ExportRun -> HistoryEntry: one-to-many (for multi-step ops; MVP: one entry)

## 4) Controlled vocab (optional config)
- categories: kick, snare, clap, hat, perc, fx, vocal, loop, oneshot, melodic, bass, chord, synth, etc.
- key format: "C", "Cm", "C#min", etc. (freeform allowed if parsing fails)
