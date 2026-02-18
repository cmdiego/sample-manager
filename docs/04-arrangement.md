# docs/04-arrangement.md
# Arrangement & Naming Rules

## 1) Overview
Arrangement planning is pure logic: given (samples, arrangement_profile, arrangement_selection, export_profile),
compute a deterministic Plan of operations (src->dst).

DB-alignment notes (UPDATED):
- sample_id is a SQLite integer ID.
- sample.rel_path is stored relative to library_root.
- Absolute source path is derived at runtime:
  - abs_path = join(library_root.path, sample.rel_path)

### Definitions
- bucket: output folder for a sample (e.g., "KICKS")
- category_map: mapping category -> bucket folder name

## 2) Template language (naming_template)
Templates generate output relative paths. Tokens are replaced from sample + arrangement context.

Example:
"{category}/{pack_short}_{type}_{key}_{bpm}_{index}"

Supported tokens (MVP):
- {category}
- {pack}
- {pack_short}
- {type}
- {key}
- {bpm}
- {index}
- {name} (original filename without extension)

Rules:
- Missing tokens resolve to empty string or a safe placeholder.
- Whitespace collapsed; multiple separators collapsed (implementation-defined but deterministic).

## 3) Layout modes
- monolithic:
  - output grouped into a small fixed set of buckets (KICKS/SNARES/etc)
- hierarchical:
  - output uses nested folders (e.g., vendor/pack/category)

## 4) Sanitization & constraint enforcement
ExportProfile provides:
- max_depth
- max_filename_len
- allowed charset / illegal chars
- replace_char
- case_policy
- on_violation: autofix | fail

Sanitization rules:
- Replace illegal chars with replace_char
- Enforce case policy
- Truncate filenames safely (preserve extension)
- Ensure path depth <= max_depth (if fail: error; if autofix: flatten or shorten path deterministically)

## 5) Collision handling
Collision policies (ArrangementProfile or ExportProfile):
- fail: error if two samples map to same dst
- suffix: append "_001", "_002" style suffix deterministically
- dedupe_hash: append short stable hash suffix (derived from src rel_path_norm)

## 6) Plan contract
A Plan is deterministic and pure; it contains:
- plan_id (optional)
- operations: list of operations each containing:
  - sample_id (int)
  - src_abs_path (string)
  - dst_rel_path (string)
  - mode_hint (copy/symlink/move; execution chooses final mode)
- warnings: list[str] or structured issues
- errors: list[str] or structured issues
- stats: counts and collision info

## 7) Determinism requirements
- Same inputs -> same Plan output bytes (including ordering)
- Operation ordering must be stable:
  - sort by (dst_rel_path, src_abs_path) or (sample_id) consistently
- Sanitization and collision suffixing must not depend on filesystem state