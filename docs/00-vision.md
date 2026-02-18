# docs/00-vision.md
# Sample Manager — Vision & Invariants

## 1) One-liner
Sample Manager is a cross-platform Python CLI that scans a music sample library, lets users search/tag/select samples, builds saved Arrangements (selection + rules), exports them into hardware-friendly directory structures, and reverts safely.

## 2) Primary goals
- Make it easy to:
  - Scan and index sample libraries
  - Search/filter and tag samples (including aliases and inheritance)
  - Create and edit Arrangements (saved selections)
  - Export Arrangements to a target directory under hardware constraints
  - Revert any export artifacts safely (History-driven)

## 3) Non-negotiable invariants (must hold always)
1) Non-destructive by default:
   - Export uses COPY or SYMLINK by default.
   - MOVE/RENAME in-place only when explicitly enabled by the user, gated by confirmation.
2) Reversibility:
   - Every filesystem operation that mutates state must be recorded as History.
   - Revert uses History (source of truth), never guesswork.
3) Cross-platform:
   - Use pathlib for paths.
   - Symlink strategy must degrade gracefully on Windows (copy fallback or clear error).
4) Arrangements are first-class:
   - Saved, named, editable.
   - Selection is stored as Sample IDs (SQLite row ids).
5) ExportProfiles enforce constraints:
   - max folder depth, max filename length, allowed characters.
   - violations either auto-fix (truncate/sanitize) or fail depending on policy.

## 4) Non-goals (explicitly out of scope for MVP)
- Audio similarity search / embeddings
- Auto key/BPM detection in early phases
- GUI/TUI (CLI-first; architecture supports later frontends)
- Automatic hardware flashing (assume user copies export directory manually)

## 5) Glossary
- Library Root: a directory the user scans (source library).
- Sample: a file plus metadata and tags. In DB, uniquely identified by (library_root_id, rel_path_norm).
- Tag: a label that can be applied to samples.
- Tag Alias: alternative names for a Tag (globally unique by alias_norm).
- Tag Parent (inheritance edge): a child -> parent relationship for tags; inheritance graph is a DAG (cycles forbidden).
- ArrangementProfile: rules describing layout + naming template(s).
- ArrangementInstance (Arrangement): a saved selection of Sample IDs plus a chosen profile.
- ExportProfile: hardware constraints (name length, allowed chars, depth) and policies.
- Plan: a pure, deterministic set of intended file operations (src→dst) with warnings/collisions.
- ExportRun: a recorded export execution attempt (later phase).
- HistoryEntry: persisted record of an executed Plan (for revert).

## 6) Design philosophy
- Plan first, then execute:
  - Preview is rendering a Plan.
  - Apply/export is executing a Plan.
  - Revert is executing inverse operations from History.
- Keep pure logic testable:
  - Planning, sanitization, collision handling are pure functions.
  - Filesystem effects behind a small interface and covered with tempdir tests.
- DB invariants are explicit (Phase 2):
  - Case-insensitive uniqueness via stored *_norm columns.
  - Tag inheritance is a DAG; cycles forbidden by app-level checks inside a transaction.
  - Tags are soft-deleted via tag.is_hidden (never hard-delete by default).

## 7) Phase gating
- Implement one phase at a time.
- Phase 1: config/init/validate CLI only.
- Phase 2: SQLite schema + migrations + repos (no scanning/search/arrangements/export/revert yet).