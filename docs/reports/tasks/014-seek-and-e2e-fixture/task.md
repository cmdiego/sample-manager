# Task 014 — GUI Seek and Hermetic Lifecycle Fixture

- **Status**: In Progress
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: User-reported regressions after PRs #3–#5 merged
- **Scope**: Restore GUI waveform seeking and remove the lifecycle test's dependence on an ignored local sample pack.

## 1. [Struct]

- **Primary areas**: `src/sample_manager/gui/main_window.py`, `src/sample_manager/gui/widgets/preview.py`, `tests/test_e2e_lifecycle.py`.
- **Supporting areas**: `src/sample_manager/gui/controller.py`, `tests/gui/test_playback_integration.py`, `tests/gui/test_waveform_widget.py`.
- **Current ownership boundaries**: `WaveformWidget` emits a file-relative seek fraction; `PreviewWidget` converts it to seconds; `BrowserController` owns the active player and can replace it through audio settings. The lifecycle test owns its temporary configuration and database.
- **Files expected to change**: GUI preview/window wiring, GUI integration test, lifecycle fixture, this report, task tracker.
- **Files expected to remain untouched**: Audio player seek implementation, TUI seek behavior, production sample scanning and export code.

## 2. [Interfaces]

- **User-facing interface**: Clicking a loaded GUI waveform seeks the playing sample, including after changing audio output.
- **Internal API/interface**: `PreviewWidget.connect_player()` receives the current `AudioPlayer` or `None`; `MainWindow` supplies it on construction and replacement.
- **Persistence/config interface**: No production configuration or schema change; lifecycle test generates its own `.wav` below `tmp_path`.
- **Events/signals/commands**: `WaveformWidget.seek_requested(float)` reaches `AudioPlayer.seek(seconds)`; CLI lifecycle commands continue to run in sequence.
- **Tests as interface contracts**: GUI integration covers click and player replacement; the lifecycle test runs in a fresh source archive with no `test_lib/` directory.

## 3. [Todo]

- [x] Reproduce both reports on merged `origin/main`.
- [x] Inspect player replacement and fixture assumptions.
- [ ] Wire the GUI waveform to the current player.
- [ ] Generate a valid temporary WAV inside the lifecycle fixture.
- [ ] Add a GUI integration regression test.
- [ ] Run focused, clean-archive, and full-suite validation.
- [ ] Record final implementation and update the tracker.

## 4. [Implementation + Revert]

### Implementation Plan

1. Make `PreviewWidget.connect_player()` retain one signal connection while updating its current player reference.
2. Call it from `MainWindow` at startup and after audio output changes.
3. Generate a small standard-library WAV in each lifecycle test's `tmp_path`, preserving the filename and directory shape expected by search and export assertions.
4. Run a GUI click regression and lifecycle tests from a clean archive, then the full suite.

### Revert Plan

1. Revert the changes to `src/sample_manager/gui/widgets/preview.py` and `src/sample_manager/gui/main_window.py` to restore the previous waveform wiring.
2. Revert `tests/gui/test_playback_integration.py` and `tests/test_e2e_lifecycle.py` to restore the previous test behavior.
3. Revert this report and its tracker row; no persisted user data or configuration requires migration.

## 5. [Invariance]

- Waveform clicks still emit fractions within `[0, 1]` and drags still pan without seeking.
- TUI seeking and audio player's pause/play semantics remain unchanged.
- Lifecycle test still scans one drum WAV and exercises tag, selection, arrangement, export, and revert.
- Changing audio output closes the old player and directs subsequent actions to the replacement.

## 6. [Implementation]

### Changed Files

- Pending.

### Behavior Implemented

Pending.

### Validation

- Baseline clean archive: `pytest -q tests/test_e2e_lifecycle.py` failed 3 of 5 tests because `test_lib/Funky_Disco` does not exist.
- Baseline GUI: emitting a seek request on a real `MainWindow` called the player's `seek()` zero times.

### Follow-ups / Risks

- None identified yet.
