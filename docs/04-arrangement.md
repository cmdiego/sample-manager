# Arrangement & Naming Rules

## 1) Overview
Arrangement planning is pure logic: given (samples, arrangement_profile, arrangement_selection, export_profile),
compute a deterministic Plan of operations (src->dst).

### Definitions
- bucket: output folder for a sample (e.g., "KICKS")
- category_map: mapping category -> bucket folder name

## 2) Template language (naming_template)
Templates generate a *relative path* under export_dir.

Example:
- "{bucket}/{pack_short}_{category}_{key}_{bpm}_{index}"

### Supported placeholders
- {bucket}        derived from profile rules + sample.category (or default)
- {category}      sample.category or "unknown"
- {pack}          sample pack name (or inferred from rel_path segment)
- {pack_short}    abbreviated pack name (first N chars or configured)
- {vendor}        optional
- {key}           "NA" if missing
- {bpm}           "NA" if missing
- {index}         integer assigned per bucket/category (stable ordering)
- {name}          base filename without extension (sanitized)
- {ext}           file extension without dot

### Rules
- Template output MUST NOT be absolute.
- Must not contain ".."
- Path separators are normalized to "/" during planning.
- Extension handling:
  - Plan includes destination filename with original ext unless template overrides.

## 3) Layout modes

### Monolithic
- Depth target: typically 1-2 folders deep.
- bucket is determined by category_map; default_bucket if missing.

### Hierarchical
- Example depth: vendor/pack/category/...
- layout_rules_json defines a list of path segments:
  - ["vendor", "pack", "category"]
- Each segment may map from sample fields or inferred values.

## 4) Sanitization & constraint enforcement
Sanitization happens in two passes:
1) OS-safe baseline:
   - remove NUL, strip trailing dots/spaces on Windows
   - normalize unicode (NFC recommended)
2) ExportProfile constraints:
   - illegal_chars regex replaced with replace_char
   - case_policy applied
   - max_filename_len enforced (truncate base name, preserve ext)

If export_profile.on_violation == "fail", any violation yields errors and Plan marked invalid.

## 5) Collision handling
Collision = two samples map to the same relative destination path.

collision_policy:
- "fail": plan invalid
- "suffix": append "_{n}" before extension deterministically
- "dedupe_hash": append "_{short_hash}" before extension

Collision resolution must be deterministic given same inputs.

## 6) Plan contract
Plan is the unified abstraction for preview/export.

### PlanOperation
Fields:
- op_id: str
- kind: "copy" | "symlink" | "move" | "mkdir"
- src_abs: str? (None for mkdir)
- dst_abs: str
- dst_rel: str  (relative path under export_dir)
- sample_id: str? (None for mkdir)
- notes: str? (e.g., "sanitized", "truncated", "collision_suffix")

### Plan
Fields:
- plan_id: str
- arrangement_id: str
- export_profile_id: str?
- export_dir: str?
- operations: list[PlanOperation]
- collisions: list[{dst_rel, sample_ids}]
- warnings: list[str]
- errors: list[str]
- stats: {num_samples, num_ops, num_collisions, num_warnings}

Plan validity:
- valid iff errors is empty

## 7) Determinism requirements
Given the same (selection, profile, export_profile, export_dir, library snapshot),
compute_plan must generate identical dst_rel ordering and collision resolutions.
Stable ordering basis:
- sort by sample.rel_path then sample.filename (or sample_id if stable)
