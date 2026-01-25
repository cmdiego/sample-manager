# Chat Starter — Sample Manager

You are implementing “Sample Manager”: a Python CLI tool to scan a sample library, search/tag/select samples, create saved Arrangements (selection + profile), export to hardware-constrained layouts, and revert safely.

Non-negotiable invariants:
1) Non-destructive by default (prefer symlink/copy). Destructive ops require explicit confirmation + rollback.
2) Full reversibility via persisted operation history/manifest (History is source of truth).
3) Cross-platform paths (pathlib). Symlink strategy must degrade gracefully on Windows.
4) Arrangements are first-class: saved, editable, reusable.
5) ExportProfiles enforce constraints: folder depth, filename length, allowed chars.

Project specs are in repo docs:
- docs/00-vision.md
- docs/01-data-model.md
- docs/02-persistence.md
- docs/03-cli.md
- docs/04-arrangement.md
- docs/05-export-revert.md
- docs/06-ops-safety.md

Working rule:
- Implement one module per task + tests.
- Prefer pure functions for planning; filesystem mutations behind FilesystemOps.

Phase gating:
- Only implement the phase explicitly requested in the task prompt.
- Phase 1 is ONLY: repo scaffolding + config/init/validate CLI (no DB schema, no scanning, no arrangements, no export/revert).
- Follow docs as source of truth; do not invent features not stated in docs.

