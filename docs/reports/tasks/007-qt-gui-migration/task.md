# Task 007 — Migrate Textual TUI to PySide6 Qt GUI

- **Status**: Phase 5 cutover complete; Textual removal pending (cross-platform packaging validation)
- **Origin**: User request (Qt GUI migration, 2026-07-07)
- **Assigned agent**: orchestrator (coordinates GUI, audio, testing, and documentation work)
- **Created**: 2026-07-07
- **Plan**: `007-qt-gui-migration.md`

## Problem / Objective

Replace the Textual terminal frontend with a cross-platform PySide6 Qt Widgets desktop GUI while
preserving the existing CLI, database behavior, keyboard workflow, selection semantics, audio
player, and waveform analysis. The GUI must remove terminal-cell rendering limits and provide a
pixel-rendered, zoomable waveform.

## Scope Boundary

- **GUI owns**: Qt application lifecycle, window layout, models, widgets, shortcuts, dialogs,
  pixel waveform painting, GUI settings, and frontend worker/result coordination.
- **Application services own**: framework-neutral browsing, navigation, sample details, selection,
  and session-summary operations extracted from the current TUI package.
- **Audio owns**: decoding, playback state, waveform envelope generation, and reusable peak data.
- **Repositories own**: all SQLite access. Qt widgets must never issue SQL directly.
- **CLI remains supported**: existing Typer subcommands and their output contracts are not part of
  the GUI rewrite.

## Dependencies

- Existing `sample_manager.audio` player and waveform APIs.
- Existing repository and selection APIs.
- PySide6 runtime dependency and `pytest-qt` development dependency.
- No database migration is expected.

## Files Involved (Expected)

- `src/sample_manager/gui/` — Qt entry point, main window, controllers, models, widgets, workers.
- `src/sample_manager/services/` — framework-neutral browser/navigation frontend services.
- `src/sample_manager/cli.py` and `pyproject.toml` — staged launch commands and dependencies.
- `tests/gui/` and service tests — offscreen Qt, model, interaction, waveform, and lifecycle tests.

## Phase Progress

- **Phase 1 — Framework-neutral service extraction — DONE (2026-07-07).**
  - Added `src/sample_manager/services/navigation.py` (`NavItem`, `NavState`, `build_items`,
    `_to_rel_norm`) — no UI-framework imports.
  - Added `src/sample_manager/services/library_browser.py` (`LibraryBrowserService` plus frozen
    DTOs `LibraryRoot`, `BrowserItem`, `SampleDetails`, `SelectionSummary`) — no UI-framework
    imports.
  - `tui/nav_state.py` is now a thin re-export of `services.navigation`; `tui/data.py`
    (`TuiDataSource`) is a thin adapter delegating to `LibraryBrowserService`. `tui/app.py`
    unchanged.
  - Tests: added `tests/test_navigation.py` and `tests/test_library_browser.py`.
  - **Gate passed**: `pytest tests/` → 642 passed (was 601). No `textual`/`Textual` or
    `PySide6`/`PyQt` references under `src/sample_manager/services/`. TUI imports/launch path intact.
- **Phase 2 — Qt shell (models + four-zone layout) — DONE (2026-07-07).**
  - Dependencies: `PySide6>=6.6` added as a runtime dependency; `pytest-qt>=4.2` added to the
    `dev` extra in `pyproject.toml`.
  - New package `src/sample_manager/gui/`:
    - `app.py` — `run_gui(argv)` opens the DB via the shared `cli._get_db()`, builds a
      `LibraryBrowserService`, `QApplication` (loads `theme.qss`), controller, and `MainWindow`;
      returns `app.exec()`. Also `build_application()` / `create_main_window()` helpers.
    - `main_window.py` — `QMainWindow` with a vertical splitter of two horizontal splitters:
      top = Preview (75) | Session (25); bottom = Browser (75) | Selected (25). Window geometry
      and all three splitter states persist to `QSettings("SampleManager", "SampleManager")` on
      close and restore on open.
    - `controller.py` — `BrowserController(QObject)` owns one `BrowserListModel`, one
      `SelectionListModel`, and the nav path; methods `load_root`, `navigate_to`, `navigate_up`
      (stops at root), `toggle_selection`; signals `current_path_changed`, `selection_changed`,
      `focus_changed`. Holds only `LibraryBrowserService`, never a `Db`.
    - `models/browser_model.py` — `BrowserListModel(QAbstractListModel)` with roles
      Path/IsDir/SampleId/IsSelected/Meta (`UserRole+1..+5`); `reset_with`, `refresh_item`,
      `update_selection`.
    - `models/selection_model.py` — `SelectionListModel(QAbstractListModel)` with SampleId/Path
      roles; `reset_from_service()`.
    - `widgets/` — `preview.py` (metadata + waveform placeholder, no audio), `browser.py` (filter
      field driving a case-insensitive prefix `QSortFilterProxyModel` + breadcrumb + `QListView`),
      `session_summary.py`, `selection.py`. Widgets are presentation-only — no SQL, no `Db`.
    - `workers.py` — `Worker(QRunnable)` + `WorkerSignals` scaffold for Phase 4.
    - `shortcuts.py` — `install_shortcuts()` scaffold (Backspace / Alt+Up navigate-up); full
      parity in Phase 3.
    - `theme.qss` — base dark stylesheet.
  - CLI: `sampleman gui` command added (`cli.py:gui_cmd` → `sys.exit(run_gui())`). Bare
    `sampleman` still launches Textual via the existing callback; `__main__.py` unchanged.
  - Tests: `tests/gui/` (`conftest.py` forces `QT_QPA_PLATFORM=offscreen`, provides
    `populated_service`) with `test_browser_model.py`, `test_selection_model.py`,
    `test_main_window.py` — 17 tests.
  - **Gate passed**: `pytest tests/` → 659 passed (642 prior + 17 GUI). No `textual`/`Textual`
    in `src/sample_manager/gui/`; no `sqlite3`/`Db()` in `gui/widgets/`;
    `from sample_manager.gui.app import run_gui` imports clean; `sampleman --help` shows `gui`;
    TUI launch path intact.
  - **Note**: the plan's `--qt-no-exception-hook` pytest flag does not exist in pytest-qt 4.5.0
    (installed against pytest 9); the offscreen suite passes without it. Run GUI tests with
    `QT_QPA_PLATFORM=offscreen pytest tests/gui/ -v`.
- **Phase 3 — Keyboard + mouse interaction parity — DONE (2026-07-07).**
  - `shortcuts.py` — `install_shortcuts()` now sets `WindowShortcut` context and returns
    `dict[str, QShortcut]` (keyed by sequence) so the window can selectively toggle a subset.
    Added `SHORTCUT_HELP` — the canonical `(keys, action)` parity table rendered by the help
    dialog.
  - `main_window.py` — registers the full parity table as `QShortcut`s on the window:
    `J/Down`, `K/Up` (move focus), `H/Left`/`Backspace`/`Alt+Up` (parent), `L/Right` (enter dir /
    open action dialog for a file), `Return` (enter dir / toggle file), `Space` (playback stub
    with a Phase-4 TODO), `A`/`D` (add/remove focused sample), `/` (focus filter), `Escape`
    (clear filter else close dialog), `?` (help), `Ctrl+P` (command palette). Handlers read the
    focused row from the browser and call controller methods; no SQL.
  - **Typing guard**: `QApplication.focusChanged` toggles the single-key ("typing-sensitive")
    shortcuts off while a `QLineEdit` holds focus, so `/`, vim letters, and arrows can be typed /
    used for cursor movement in the filter. All shortcuts are suspended while a dialog is open and
    restored on `finished`.
  - **Focus model**: the browser `QListView` is `NoFocus` and the filter is `ClickFocus` — this
    stops the view's built-in arrow/type-ahead handling and the filter's auto-grab from consuming
    the keys via `ShortcutOverride` before the window shortcuts fire. Focus movement is driven by
    `move_focus`/`focus_first`; mouse clicks still set the current index.
  - `controller.py` — added explicit `add_to_selection` / `remove_from_selection` (idempotent)
    alongside `toggle_selection`, all routed through a shared `_refresh_after_selection` that uses
    the browser model's in-place `update_selection` (preserving the focused row) and refreshes the
    selection model + session summary.
  - `dialogs.py` (new) — `ActionDialog` (per-file Add/Remove/Close), `HelpDialog` (table of every
    shortcut from `SHORTCUT_HELP`), `CommandPaletteDialog` (filter field + static action list that
    invokes controller callbacks). All close on `Escape`; shown non-modally.
  - `widgets/browser.py` — focus/filter API, filter-change focus preservation, and a right-click
    context menu (Add / Remove / Open in file manager stub) via new signals.
  - `widgets/selection.py` — single-click emits `detail_requested` (drives the preview) and a
    right-click "Remove from selection" context menu.
  - Tests: `tests/gui/test_interactions.py` (33 tests) covering every shortcut via
    `qtbot.keyClick`, single/double click, both context menus, filter prefix/case/escape/nav, the
    three dialogs, and selection-mutation refresh + focus preservation. The offscreen platform
    never marks the window OS-active, so the fixture calls `QApplication.setActiveWindow` to make
    `WindowShortcut` fire.
  - **Gate passed**: `pytest tests/` → 692 passed (659 prior + 33). `QT_QPA_PLATFORM=offscreen
    pytest tests/gui/` → 50 passed. No `textual`/`Textual` under `src/sample_manager/gui/`. Bare
    `sampleman` still launches Textual; `sampleman gui` launches Qt.

- **Phase 4 — Audio engine + pixel waveform wired into the Qt GUI — DONE (2026-07-07).**
  - `audio/waveform.py` — added `WaveformService.get_waveform(path, bins)` (reuses the existing
    (path, size, mtime) LRU from `load()` and re-bins the cached full-resolution envelope to the
    requested count) and a pure-Python `resample_bins()` helper (down- or up-samples to exactly N
    bins with no numpy).
  - `audio/sounddevice_output.py` — added `NullOutput`, a no-op `AudioOutput` used when
    `sounddevice` is not installed so the GUI runs silently instead of crashing.
  - `services/library_browser.py` — added `sample_path(sample_id)` (library-root path + rel_path)
    so front-ends can hand a real filesystem path to the audio engine.
  - `gui/workers.py` — fleshed out `WorkerSignals` (`waveform_ready(int, object)`,
    `error(int, str)`) and `WaveformWorker(generation, path, bins, service)` (QRunnable that calls
    `get_waveform` off the GUI thread and emits queued results; never touches a widget). Kept a
    generic `Worker` for ad-hoc background work.
  - `gui/widgets/waveform.py` (new) — `WaveformWidget(QWidget)`. Posts a `WaveformWorker` to
    `QThreadPool.globalInstance()` (`setMaxThreadCount(2)`), carries a monotonic `generation` and
    drops stale results. `paintEvent` scales the painter by `1/devicePixelRatioF()` and draws one
    vertical min→max line per *physical* pixel (bg #1a1a1a, wave #3a7d3a, played region #4a9d4a,
    zero line mid-gray, 1px #00ff00 playhead); shows centred "Loading…"/error/blank states.
    Wheel = zoom around the cursor (clamped to ≥0.05 span), click-drag = pan, double-click =
    reset; zoom is a normalized `[zoom_start, zoom_end]` window over the full file re-sliced at
    paint time. `minimumSizeHint` = 200×80.
  - `gui/widgets/preview.py` — replaced the placeholder with the `WaveformWidget`; forwards a
    resolved focus path (`set_focus_path`) and playback snapshots (`on_playback_changed`) to it.
  - `gui/controller.py` — takes an optional `AudioPlayer`; a 200 ms `QTimer` polls
    `player.snapshot()` and re-broadcasts it as `playback_changed(PlaybackSnapshot)`. `set_focus`
    auto-auditions files (`player.play`) and never plays for directories; `play_focused_from_start`
    backs `Space` (`player.play_from_start`); `shutdown()` stops the timer and closes the player.
  - `gui/main_window.py` — passes the waveform service to the preview, wires `playback_changed` to
    the preview + status bar, resolves the focus path, `Space` → restart, and a three-section
    status bar (dir | `PLAYING — file [m:ss / m:ss]` | errors auto-cleared after 5 s).
    `closeEvent` stops the timer and calls `controller.shutdown()` (→ `player.close()`) before the
    DB closes.
  - `gui/app.py` — `_build_audio()` constructs the `AudioPlayer` (with `SoundDeviceOutput` when
    available, else `NullOutput` + a status-bar warning) and a `WaveformService`, injected via
    `create_main_window(service, player, waveform_service)`. All audio imports are lazy
    (`TYPE_CHECKING` or inside functions) so importing `gui/` pulls in no numpy/sounddevice.
  - Tests: `tests/gui/test_waveform_widget.py` (physical-pixel-width request + render,
    loading/error/empty states, stale-generation drop, zoom clamp/pan/reset) and
    `tests/gui/test_playback_integration.py` (polling timer emits, auto-audition, `Space` restart,
    no-player no-ops, `closeEvent` closes the player, status-bar formatter).
  - **Gate passed**: `pytest tests/` → 713 passed (692 prior + 21). `QT_QPA_PLATFORM=offscreen
    pytest tests/gui/` → 71 passed. No `textual` under `src/sample_manager/gui/`; no
    `sqlite3`/`Db()` under `gui/widgets/`; no `PySide6` under `src/sample_manager/audio/`. GUI
    import loads no numpy/sounddevice. Bare `sampleman` still launches Textual.

- **Phase 5 — Default launch cutover to Qt — DONE (2026-07-07).**
  - `src/sample_manager/__main__.py` — `python -m sample_manager` now launches the Qt GUI via
    `gui.app.run_gui(sys.argv)`. The DB is opened lazily inside `run_gui`, so importing the module
    has no side effects. Header comment documents the rollback path (`sampleman tui`) and that
    Textual stays installed until cross-platform Qt packaging is validated.
  - `src/sample_manager/cli.py` — the no-subcommand callback (`_main`) now launches the Qt GUI
    instead of Textual (`raise typer.Exit(run_gui())`); added a `tui` command
    (`SampleManagerApp().run()`) as the legacy Textual fallback. The `gui` command is unchanged.
  - Docs updated: `README.md` (launch instructions + `tui` note + screenshots-pending note),
    `docs/03-cli.md` (`gui`/`tui` in the command reference), `docs/11-progress.md` (Qt cutover
    section), `CLAUDE.md` (Commands + Architecture: `gui/`, `services/`, `tui/`).
  - **Textual deletion deferred**: no Textual source, TUI modules, Textual tests, or the `textual`
    dependency in `pyproject.toml` were removed. Deletion happens only after packaging smoke tests
    pass on macOS, Windows, and Linux — that validation cannot be performed in this environment.
  - **Gate passed**: `pytest tests/` → 713 passed, 0 failed. `QT_QPA_PLATFORM=offscreen pytest
    tests/gui/` → 71 passed, 0 failed. `sampleman --help` lists both `gui` and `tui`. No
  `textual`/`Textual` references under `src/sample_manager/gui/`. `python -c "from
  sample_manager.__main__ import run_gui"` imports clean.

- **Post-cutover — System default audio output setting — DONE (2026-07-07).**
  - Added a Settings dialog with an I/O tab and persisted `System Default Output` / `Disabled`
    modes under `QSettings` key `io/audio_output_mode`.
  - System Default constructs `SoundDeviceOutput(device=None)`, explicitly following the operating
    system's current default output device. Changes apply immediately by replacing and closing the
    controller's existing player.
  - NumPy, soundfile, and sounddevice moved into standard runtime dependencies so a normal GUI
    installation includes WAV decoding and real playback support; audioread and mutagen remain in
    the optional `[audio]` extra.
  - Added Settings to the Application menu (`Ctrl+,`) and command palette.
  - **Gate passed**: `QT_QPA_PLATFORM=offscreen pytest` → 720 passed, 0 failed. Hardware playback
  was not exercised because the existing virtual environment predates the dependency move and
  does not currently contain sounddevice.
  - Follow-up device discovery added `AudioOutputDevice` and `list_output_devices()`, filtering
    sounddevice inventory to output-capable endpoints and exposing Core Audio host API, channel
    count, sample rate, and system-default status.
  - Settings → I/O now lists System Default, each available macOS output device, and None.
    Specific device indices persist in `QSettings` and are applied immediately through
    `SoundDeviceOutput(device=index)`.
  - When discovery fails or returns no output-capable devices, the combo contains only `None` and
    defaults to that safe no-output selection rather than advertising an unusable system default.
  - Live host verification returned `MacBook Pro Speakers` via Core Audio with two output channels.
  - **Follow-up gate passed**: `QT_QPA_PLATFORM=offscreen pytest` → 728 passed, 0 failed.
  - Transport follow-up: Space now pauses active/loading playback or starts the focused sample at
    frame zero; Ctrl+Space resumes a paused track from the checkpoint retained by `AudioPlayer`.
  - **Transport gate passed**: `QT_QPA_PLATFORM=offscreen pytest` → 732 passed, 0 failed.

## Resolution

Phase 5 cutover complete: the Qt GUI is the default launch for both `sampleman` (bare) and
`python -m sample_manager`; `sampleman tui` retains the Textual terminal UI. Textual source,
tests, and the dependency remain in place and are removed only after cross-platform Qt packaging
smoke tests pass on macOS, Windows, and Linux.

## Validation

- Existing CLI and domain suite remains green.
- Qt tests run with `QT_QPA_PLATFORM=offscreen`.
- GUI parity checklist passes on macOS, Windows, and Linux.
- Packaged application smoke test passes on each target platform.

## Links

- Plan: `007-qt-gui-migration.md`
- Implementation prompt: `prompt.md`
- Qt for Python: <https://doc.qt.io/qtforpython-6/>
- Qt Model/View: <https://doc.qt.io/qtforpython-6/overviews/qtwidgets-model-view-programming.html>
