# Task Reports

Main tracker for `sample_manager` task reports.

Every task gets one durable report:

```text
docs/reports/tasks/<NNN>-<task-slug>/task.md
```

Reports created with the Codex `task` skill use this section order:

1. `[Struct]`
2. `[Interfaces]`
3. `[Todo]`
4. `[Implementation + Revert]`
5. `[Invariance]`
6. `[Implementation]`

## Status Tracker

| Task | Status | Created | Report | Notes |
| --- | --- | --- | --- | --- |
| 002 — TUI File Selection & Traversal | ✅ Fixed | 2026-07-07 | [task.md](002-tui-file-selection-traversal/task.md) | TUI issue-driven task. |
| 003 — TUI Help Shortcut | ✅ Fixed | 2026-07-07 | [task.md](003-tui-help-shortcut/task.md) | TUI issue-driven task. |
| 004 — Audio Analysis: First Steps | ✅ Done | 2026-07-07 | [task.md](004-audio-analysis-first-steps/task.md) | Audio domain setup and analysis first steps. |
| 005 — Audio: Media Player, Cover-Art Extraction & Waveform Data | 🔍 Planned | 2026-07-07 | [task.md](005-audio-player-and-artwork/task.md) | Planned next audio work. |
| 006 — TUI: Waveform & Cover-Art Display | 🔍 Planned | 2026-07-07 | [task.md](006-tui-waveform-and-artwork-display/task.md) | Planned TUI display work. |
| 007 — Migrate Textual TUI to PySide6 Qt GUI | Phase 5 cutover complete; Textual removal pending | 2026-07-07 | [task.md](007-qt-gui-migration/task.md) | Cross-platform packaging validation remains. |
| 008 — Virtual Arrangement Workspace and Browser QoL | Planned | 2026-07-07 | [task.md](008-arrangement-workspace-qol/task.md) | Assigned arrangement/browser quality-of-life work. |
| 009 — JSON GUI Testbench | In Progress | 2026-07-08 | [task.md](009-json-gui-testbench/task.md) | Movement runtime and `--simulation` shell implemented. |
| 010 — Search, Drag and Drop, and Focus | ✅ Done | 2026-10-13 | [task.md](010-search-drag-and-focus/task.md) | GUI search/Stage fixes, `.wave` indexing, and TUI filter repair. |
| 011 — GUI Library Management | ✅ Done | 2026-10-13 | [task.md](011-library-management/task.md) | Root picker and nonblocking add/rescan workflow. |
| 012 — TUI Navigation and Stage Focus | ✅ Done | 2026-10-13 | [task.md](012-tui-navigation/task.md) | Make Tab and root cycling usable. |
| 013 — GUI First-Run Setup | ✅ Done | 2026-10-13 | [task.md](013-gui-first-run/task.md) | Launch without prior CLI initialization. |
| 014 — GUI Seek and Hermetic Lifecycle Fixture | ✅ Done | 2026-10-14 | [task.md](014-seek-and-e2e-fixture/task.md) | Waveform clicks seek; lifecycle tests use generated audio. |
| 015 — TUI Search Mode Transition | ✅ Done | 2026-10-14 | [task.md](015-tui-search-mode-transition/task.md) | Search cancels waveform navigation without seeking. |
| 016 — TUI Settings and Library Search | ✅ Done | 2026-10-14 | [task.md](016-tui-settings-search/task.md) | F2 settings, root-wide search, and modal keyboard fixes. |
| 017 — TUI Library Rescan | ✅ Done | 2026-10-14 | [task.md](017-tui-library-rescan/task.md) | F5 scans in the background and refreshes Browser, search, and Stage. |
| 018 — Add Libraries from the TUI | ✅ Done | 2026-10-14 | [task.md](018-tui-add-library/task.md) | F4 adds and indexes sample folders, including first run. |
| 019 — TUI Sample Tags | ✅ Done | 2026-10-14 | [task.md](019-tui-sample-tags/task.md) | F6 tag editing, search refresh, and TUI lifecycle fixes. |
| 020 — TUI Leader Command Panel | ✅ Done | 2026-10-14 | [task.md](020-tui-leader-commands/task.md) | Discoverable commands through backslash/F1 and grouped executable hints. |

## Maintenance Rules

- Add a row whenever a new task report is issued.
- Update the row whenever the task report status changes.
- Keep the task title, status, created date, and report link aligned with the task report.
- Keep notes short; detailed rationale belongs in the task report.
