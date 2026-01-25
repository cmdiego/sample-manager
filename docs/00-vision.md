# Sample Manager — Vision & Invariants

## 1) One-liner
Sample Manager is a cross-platform Python CLI that scans a music sample library, lets users search/tag/select samples, builds saved Arrangements (selection + rules), exports them into hardware-friendly directory structures, and reverts safely.

## 2) Primary goals
- Make it easy to:
  - Scan and index sample libraries
  - Search/filter and tag
  - Create and edit Arrangements (saved selections)
  - Export Arrangements to a target directory under hardware constraints
  - Revert any temporary structure created during export

## 3) Non-negotiable invariants (must hold always)
1) Non-destructive by default:
   - Export uses COPY or SYMLINK by default.
   - MOVE/RENAME in-place only when explicitly enabled by the user.
2) Reversibility:
   - Every operation that changes filesystem state must be recorded as History.
   - Revert uses History (source of truth), never guesswork.
3) Cross-platform:
   - pathlib for paths
   - symlink strategy degrades gracefully on Windows
4) Arrangements are first-class:
   - Saved, named, editable
   - Selection is stored as Sample IDs
5) ExportProfiles enforce constraints:
   - max folder depth, max filename length, allowed characters
   - violations either auto-fix (truncate/sanitize) or fail depending on policy

## 4) Non-goals (explicitly out of scope for MVP)
- Audio similarity search / embeddings
- Auto key/BPM detection
- GUI/TUI (CLI-first; architecture supports later frontends)
- Automatic hardware flashing (assume user copies export directory manually)

## 5) Glossary
- Library Root: the directory the user scans (source library).
- Sample: a file (wav/aiff/flac/mp3…) plus metadata and tags.
- ArrangementProfile: rules describing layout + naming template(s).
- ArrangementInstance (Arrangement): a saved selection of Sample IDs plus a chosen profile.
- ExportProfile: hardware constraints (name length, allowed chars, depth) and policies.
- Plan: a pure, deterministic set of intended file operations (src→dst) with warnings/collisions.
- HistoryEntry: persisted record of an executed Plan (for revert).

## 6) Design philosophy
- Plan first, then execute:
  - Preview is rendering a Plan.
  - Apply/export is executing a Plan.
  - Revert is executing inverse operations from History.
- Keep pure logic testable:
  - Planning, sanitization, collision handling are pure functions.
  - Filesystem effects behind a small interface and covered with tempdir tests.
