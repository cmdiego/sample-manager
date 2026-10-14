# Task 015 — TUI Search Mode Transition

- **Status**: Done
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: Continued GUI/TUI usability audit
- **Scope**: Make entering TUI search leave waveform navigation so arrow keys have one active meaning.

## 1. [Struct]

- **Primary area**: `src/sample_manager/tui/app.py` keyboard mode transitions.
- **Supporting area**: `tests/test_tui_navigation.py` Textual pilot.
- **Current ownership boundaries**: `SampleManagerApp.on_key()` routes keyboard events; `_start_filter()` activates typeahead; `_exit_waveform_nav()` clears the waveform seek cursor.
- **Files expected to change**: TUI app, mounted TUI pilot test, this report, task tracker.
- **Files expected to remain untouched**: Audio player seek implementation, GUI keyboard handling, persisted sample data.

## 2. [Interfaces]

- **User-facing interface**: Pressing `/` enters typeahead search; waveform navigation uses `w`, arrows, Enter, and Escape.
- **Internal API/interface**: `_start_filter()` cancels waveform navigation through `_exit_waveform_nav(seek=False)` before activating search.
- **Persistence/config interface**: None.
- **Events/signals/commands**: Textual key events `w`, `/`, character input, and arrows.
- **Tests as interface contracts**: A mounted Textual pilot exercises the key sequence and asserts the seek cursor is no longer active in search mode.

## 3. [Todo]

- [x] Reproduce overlapping waveform and search modes with a mounted TUI.
- [x] Add a failing pilot regression.
- [x] Cancel waveform navigation when search starts.
- [x] Run focused and full-suite validation.
- [x] Record implementation and update tracker.

## 4. [Implementation + Revert]

### Implementation Plan

1. Extend the mounted navigation pilot to enter waveform mode and then typeahead search.
2. Call the existing no-seek exit path before `_start_filter()` updates the search state.
3. Validate mode state and keyboard behavior, then run the complete test suite.

### Revert Plan

1. Revert the `_start_filter()` change in `src/sample_manager/tui/app.py`.
2. Revert the pilot addition in `tests/test_tui_navigation.py`.
3. Revert this report and its tracker row; no data migration is needed.

## 5. [Invariance]

- Pressing Enter in waveform navigation still seeks to the chosen fraction.
- Pressing Escape in waveform navigation still cancels without seeking.
- Typing `/` from ordinary browser mode still opens an empty search.
- Search typing and Stage navigation remain functional.

## 6. [Implementation]

### Changed Files

- `src/sample_manager/tui/app.py` — cancel waveform navigation without seeking before search activates.
- `tests/test_tui_navigation.py` — drive `w`, `/`, typing, and Right in a mounted Textual pilot; verify only browser navigation handles Right.
- `docs/reports/tasks/README.md` — mark the task done.

### Behavior Implemented

Entering typeahead search clears the waveform seek cursor and ends its arrow-key routing. Search then handles text and navigation keys normally; the transition never seeks audio.

### Validation

- Baseline mounted TUI: `w`, `/`, `k`, Right left both search and waveform navigation active; Right moved the seek cursor.
- Added pilot failed before the code change because waveform navigation remained active.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tui_navigation.py tests/test_tui_waveform.py tests/test_tui_filter.py`: 38 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/`: 881 passed, 10 deprecation warnings.

### Follow-ups / Risks

- No known behavioral risk; this PR is based on the branch for Task 014 until that PR merges.
