Task (007 — Migrate Textual TUI to PySide6 Qt GUI): implement the staged Qt Widgets migration
described in the Task 007 plan.

Read first:
- `docs/reports/tasks/007-qt-gui-migration/007-qt-gui-migration.md`
- `docs/reports/tasks/007-qt-gui-migration/task.md`
- `docs/00-vision.md`
- `src/sample_manager/tui/`
- `src/sample_manager/audio/`
- `src/sample_manager/repos/`
- `src/sample_manager/cli.py`

Execution rules:
- Implement one plan phase at a time and satisfy its gate before proceeding.
- Preserve the existing CLI, database schema, repositories, selection semantics, audio API, and
  non-destructive project invariants.
- Extract framework-neutral services before adding Qt-dependent presentation code.
- Use PySide6 Qt Widgets and Qt model/view classes; do not use QML, raylib, Electron, or web views.
- Qt widgets must not issue SQL, decode audio, or perform blocking filesystem/audio work.
- Use bounded `QThreadPool` work, queued result signals, and generation IDs for stale-result
  suppression. Never mutate widgets from worker threads.
- Build the waveform with `QPainter`, physical-pixel-aware min/max envelopes, zoom, pan, and
  playhead rendering. Do not reuse terminal glyph rendering.
- Preserve keyboard parity: `hjkl`/arrows, Return, Space restart, `a/d`, `/`, Escape, `?`, and
  `Ctrl+P`; add equivalent mouse actions.
- Keep Textual as a fallback until all parity, regression, and packaging gates pass.

Required deliverables:
- Framework-neutral browser/navigation service layer and immutable DTOs.
- `sample_manager.gui` package with application entry point, main window, controller, Qt models,
  widgets, workers, shortcuts, stylesheet, and settings persistence.
- Pixel waveform with asynchronous multiresolution data, zoom/pan, and playback cursor.
- `sampleman gui` transition command, then default-launch cutover only at the Phase 5 gate.
- Offscreen Qt tests using `pytest-qt`, retained domain/CLI tests, and cross-platform acceptance
  notes.
- Updated README, CLI docs, progress tracker, screenshots, and deployment configuration.

Validation required:
- Run the complete pytest suite after every phase; do not reduce existing coverage.
- Run GUI tests with `QT_QPA_PLATFORM=offscreen`.
- Manually verify keyboard, mouse, playback, waveform, selection, startup errors, and shutdown.
- Smoke-test `pyside6-deploy` artifacts on macOS, Windows, and Linux before removing Textual.

Stop conditions:
- Do not remove Textual when any parity behavior, target platform, package build, or regression test
  is failing.
- Do not silently change CLI output or persistence contracts to simplify GUI implementation.
- Record unresolved platform or packaging issues in `task.md` and leave the TUI fallback enabled.

