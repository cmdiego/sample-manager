# PySide6 Qt GUI Migration

## Goal

Migrate the interactive frontend from Textual to PySide6 Qt Widgets without rewriting the domain.
The completed application launches a native desktop window, retains the existing browsing and
selection workflow, provides pixel-accurate waveform rendering, and leaves all Typer CLI commands
operational.

## Current Baseline

- Bare `sampleman` launches `SampleManagerApp` from `src/sample_manager/tui/app.py`.
- Textual owns application lifecycle, key dispatch, filtering, layout, and frontend coordination.
- `tui/data.py` and `tui/nav_state.py` are mostly framework-neutral but live under the wrong layer.
- `sample_manager.audio` is already independent of Textual and exposes playback snapshots and
  waveform data.
- The current four-zone interface contains Preview, Session, Browser, and Selected Files regions.
- The regression suite has 601 passing tests before this migration begins.

## Resolved Architecture Decisions

- Use **PySide6 Qt Widgets**, not QML, raylib, or an embedded web frontend.
- Use `QMainWindow` with resizable splitters and preserve the four-zone information architecture.
- Use Qt model/view classes rather than manually rebuilding item widgets.
- Keep repositories, application services, audio services, and Qt presentation as separate layers.
- Make PySide6 a standard runtime dependency because the GUI becomes the default application.
- Add `pytest-qt` to development dependencies and run GUI tests offscreen.
- Keep the TUI temporarily during parity work; remove Textual only after the final cutover gate.
- Store window geometry, splitter positions, and GUI preferences with `QSettings`; do not store
  transient UI geometry in SQLite.
- Use `QThreadPool` workers with result signals and generation IDs. Workers never mutate widgets.

## Target Package Structure

```text
src/sample_manager/
  services/
    library_browser.py      # framework-neutral browsing/selection facade
    navigation.py           # NavItem/NavState and deterministic transitions
  gui/
    __init__.py
    app.py                  # QApplication construction and run_gui()
    main_window.py          # composition, lifecycle, and top-level actions
    controller.py           # coordinates services, models, audio, and workers
    models/
      browser_model.py      # QAbstractListModel
      selection_model.py    # QAbstractListModel
    widgets/
      preview.py
      waveform.py           # QPainter pixel waveform
      browser.py
      session_summary.py
      selection.py
    workers.py              # typed QRunnable/signal bridge
    shortcuts.py
    theme.qss
tests/
  gui/
```

The exact number of modules may be compressed where code is small, but the dependency direction
must remain `gui -> services/audio/repos`, never the reverse.

## Public Interfaces

### GUI Entry Point

```python
def run_gui(argv: list[str] | None = None) -> int:
    """Construct QApplication, services, and MainWindow; return the Qt exit code."""
```

`run_gui` owns startup error dialogs and top-level resource construction. `MainWindow.closeEvent`
invalidates workers, closes `AudioPlayer`, persists `QSettings`, and closes the database.

### Framework-Neutral Browser Service

```python
class LibraryBrowserService:
    def library_roots(self) -> tuple[LibraryRoot, ...]: ...
    def list_directory(self, path: Path) -> tuple[BrowserItem, ...]: ...
    def sample_details(self, sample_id: int) -> SampleDetails | None: ...
    def selected_samples(self) -> tuple[SampleDetails, ...]: ...
    def add_to_selection(self, sample_id: int) -> None: ...
    def remove_from_selection(self, sample_id: int) -> None: ...
    def selection_summary(self) -> SelectionSummary: ...
```

Return typed, immutable DTOs. Preserve existing directory ordering, hidden-file handling, sample
IDs, and persistent selection behavior.

### Qt Models

- `BrowserListModel(QAbstractListModel)` exposes display, path, directory, sample ID, selected,
  and metadata roles.
- `SelectionListModel(QAbstractListModel)` exposes selected sample identity and display roles.
- `QSortFilterProxyModel` provides case-insensitive prefix filtering without changing source state.
- Models update with reset/row/data signals; views never query repositories directly.

## Window and Interaction Design

### Layout

- `QMainWindow` central widget contains a vertical splitter for preview/session and browser/selection
  rows; each row contains a horizontal splitter with an initial 75/25 ratio.
- Preview contains the waveform, playback indicator, filename, format, size, tags, and sample ID.
- Browser contains a filter field, path breadcrumb, and list/table view.
- Session shows selection count, total bytes, and active export destination.
- Selected Files shows the persistent selection buffer and supports activation/removal.
- A status bar reports current directory, playback state, worker/backend errors, and shortcuts.

### Input Parity

- `J/K` and Down/Up move browser focus.
- `H` and Left navigate to the parent directory.
- `L` and Right open a directory or the sample action dialog.
- Return enters a directory or toggles file selection.
- Space restarts the focused sample from frame zero.
- `A/D` add/remove the focused sample from persistent selection.
- `/` focuses the filter; Escape clears it or closes the active dialog.
- `?` opens a shortcut/help dialog; `Ctrl+P` opens the command/action palette.
- Mouse single-click focuses, double-click activates, and context menus expose equivalent actions.
- Moving focus retains the current auto-audition behavior.

## Pixel Waveform Design

- Implement `WaveformWidget(QWidget)` and draw in `paintEvent` with `QPainter`.
- Draw one signed min/max line per physical output pixel, plus zero line, played region, and playhead.
- Account for device pixel ratio and repaint only the waveform region during playback updates.
- Mouse wheel zooms horizontally around the pointer; drag pans the viewport; double-click resets to
  the full-file overview.
- Extend `WaveformService` with a range-and-width query or multiresolution peak pyramid so zooming
  never depends on a fixed 4,096-bin overview.
- Decode/peak generation runs off the GUI thread. Cached data is keyed by resolved path, size, and
  modification time. Stale focus/zoom results are discarded by generation ID.
- Waveform failure does not prevent metadata display or playback controls from functioning.

## Threading and Error Handling

- Use a bounded `QThreadPool`; avoid `asyncio` integration in the Qt frontend.
- Worker inputs and outputs are immutable DTOs. Results return through queued Qt signals.
- Every focus-dependent request carries a monotonically increasing generation ID.
- Closing the window invalidates generations and clears queued work; running tasks may finish but
  their results are ignored.
- Backend, decode, configuration, and database failures appear in the status bar or a modal startup
  dialog as appropriate. Exceptions must not escape Qt slots.

## Implementation Phases

### Phase 1 — Extract Shared Application Services

1. Move `NavItem`, `NavState`, and `build_items` into `services/navigation.py` without changing
   behavior.
2. Replace `TuiDataSource` with `LibraryBrowserService` and typed DTOs.
3. Update Textual imports to consume the new service layer temporarily.
4. Move existing pure navigation/data tests to service-focused tests and keep them green.

**Gate:** Textual still runs; all existing tests pass; service modules contain no Textual or Qt
imports.

### Phase 2 — Qt Shell and Models

1. Add PySide6 and `pytest-qt`; create `run_gui` and a minimal `QMainWindow`.
2. Implement browser and selection models plus proxy filtering.
3. Reproduce the four-zone layout, metadata preview, session summary, and status bar.
4. Add `sampleman gui` while bare `sampleman` continues launching Textual.

**Gate:** The GUI browses configured roots and persistent selections in offscreen and manual tests.

### Phase 3 — Interaction Parity

1. Implement keyboard shortcuts, mouse activation, filter behavior, parent/child traversal, action
   dialog, and help dialog.
2. Connect selection mutations to model refresh and session summary updates.
3. Preserve focused item and filter context across relevant updates.

**Gate:** Every input-parity behavior has a Qt test and matches the current frontend contract.

### Phase 4 — Audio and Pixel Waveform

1. Inject `AudioPlayer` and connect focus auto-audition and Space restart behavior.
2. Implement `QTimer` playback snapshot polling without blocking the GUI thread.
3. Implement high-DPI `QPainter` waveform rendering, zoom, pan, playhead, loading, and errors.
4. Add bounded worker execution, multiresolution peak caching, and stale-result suppression.

**Gate:** Playback and waveform remain responsive during rapid navigation and application shutdown.

### Phase 5 — Cutover and Removal

1. Run parity acceptance on macOS, Windows, and Linux.
2. Switch bare `sampleman` to `run_gui`; add a temporary explicit `sampleman tui` fallback.
3. Update README, CLI docs, progress tracker, and screenshots.
4. Package and smoke-test native artifacts with `pyside6-deploy`.
5. After one transition release, remove `sampleman tui`, Textual dependencies, TUI source, styles,
   and obsolete Textual tests.

**Gate:** GUI acceptance, packaging, and full regression suites pass before Textual deletion.

## Testing and Acceptance

### Automated

- Service tests: ordering, navigation boundaries, filtering inputs, hidden files, selected state,
  root changes, and DB failures.
- Model tests: row counts, role values, reset/data signals, proxy filtering, and selection updates.
- Widget tests: metadata, empty/loading/error states, selection summary, and shortcut dispatch.
- Waveform tests: dimensions, signed extrema, high-DPI rendering, zoom anchoring, pan bounds,
  playhead position, cache invalidation, and stale results.
- Lifecycle tests: no config, no roots, startup, shutdown during decode, audio cleanup, DB cleanup,
  and repeated window creation where supported.
- GUI integration tests use `QT_QPA_PLATFORM=offscreen` and `pytest-qt`.
- Existing CLI, repository, export, audio, and migration tests remain green.

### Manual Cross-Platform Acceptance

- Browse with keyboard and mouse; enter/leave directories; filter without losing selection.
- Auto-audition focused samples and restart with Space.
- Verify pixel waveform overview, zoom, pan, playhead, resize, and Retina/high-DPI behavior.
- Add/remove persistent selections and confirm session totals.
- Confirm startup errors are actionable and closing leaves no audio or worker process behind.
- Verify packaged application startup and audio output on macOS, Windows, and Linux.

## Non-Goals

- Database schema redesign.
- Rewriting CLI subcommands in Qt.
- Audio editing, destructive waveform manipulation, or DAW-style multitrack timelines.
- QML, raylib, browser/Electron, or mobile frontends.
- New arrangement/export behavior unrelated to exposing existing operations in the GUI.

## Rollback Strategy

- Keep Textual runnable until the final parity gate.
- Land each phase independently with a green suite.
- If Qt packaging or platform acceptance fails, retain `sampleman gui` as opt-in and leave bare
  `sampleman` on Textual until corrected.
- Do not delete TUI code or remove Textual in the same change that first switches the default.

