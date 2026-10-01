# Task 009 — JSON GUI Testbench

- **Status**: In Progress
- **Created**: 2026-07-08
- **Owner**: Codex
- **Origin**: user request
- **Scope**: Improve the GUI testbench by using JSON scenario files to simulate user interface behavior in repeatable Qt tests.

## 1. [Struct]

Describe the relevant structure before changing code.

- **Primary area**: `tests/gui/`
- **Supporting areas**: `src/sample_manager/gui/`, `tests/gui/conftest.py`
- **Current ownership boundaries**:
  - `src/sample_manager/gui/main_window.py` owns Qt widget composition, shortcuts, menu actions, and signal wiring.
  - `src/sample_manager/gui/controller.py` owns browser state, selection state, playback state, and service-facing GUI operations.
  - `src/sample_manager/gui/simulation.py` owns JSON simulation dispatch and the JSON-lines simulation shell.
  - `src/sample_manager/gui/widgets/` owns focused widget behavior such as browser navigation, preview display, stage display, and session/stage summary rendering.
  - `tests/gui/` owns headless Qt behavior tests using `pytest-qt` and the offscreen Qt platform.
  - `tests/gui/conftest.py` owns GUI fixtures, including an in-memory migrated database and a real temporary sample library.
- **Files expected to change**:
  - `src/sample_manager/gui/simulation.py` — reusable JSON GUI simulation runtime and shell.
  - `src/sample_manager/gui/app.py` — app launch integration for `--simulation`.
  - `src/sample_manager/cli.py` — CLI option integration for `sampleman --simulation` and `sampleman gui --simulation`.
  - `tests/gui/test_json_scenarios.py` — execute JSON-defined GUI scenarios.
  - `tests/gui/test_simulation_shell.py` — verify JSON-lines shell behavior.
  - `tests/gui/scenarios/*.json` — store scenario definitions.
  - Potentially `tests/gui/helpers.py` — isolate scenario runner mechanics if the runner becomes large enough.
- **Files expected to remain untouched**:
  - `src/sample_manager/gui/main_window.py` unless a scenario exposes missing test seams.
  - `src/sample_manager/gui/controller.py` unless the testbench reveals behavior that cannot be observed through existing interfaces.
  - Production audio, persistence, scanner, and TUI modules.

## 2. [Interfaces]

List the integration seams this task will use or modify.

- **User-facing interface**:
  - Simulated keyboard input such as `J`, `K`, `H`, `L`, arrow keys, `Return`, `Space`, `Ctrl+Space`, `A`, `D`, `/`, `Escape`, `?`, and `Ctrl+P`.
  - Simulated text entry for browser filtering and command/dialog inputs.
  - Simulated mouse interactions where needed for parity with existing tests.
- **Internal API/interface**:
  - `create_main_window(service)` remains the primary window construction entry point.
  - `MainWindow` public widget attributes used by tests remain the observation surface: `browser`, `preview`, `selection`, `session_summary`, `active_dialog`, and `controller`.
  - `BrowserController` remains the state authority for current path, focused browser data, stage/selection state, and summary data.
- **Persistence/config interface**:
  - Scenario tests should continue to use the in-memory DB from `tests/gui/conftest.py`.
  - JSON scenario files must not depend on machine-specific absolute paths.
  - QSettings-backed geometry/state must not leak between tests; existing test isolation should be preserved or strengthened.
- **Events/signals/commands**:
  - Qt key/mouse events should be emitted through `qtbot` rather than direct slot calls unless a scenario explicitly asserts controller-level behavior.
  - Signals such as browser focus changes, directory activation, selection changes, playback changes, and dialog actions are observed through resulting UI/controller state.
- **Tests as interface contracts**:
  - Existing imperative tests in `tests/gui/test_interactions.py` and `tests/gui/test_main_window.py` define behavior that JSON scenarios must not weaken.
  - New JSON scenarios should encode high-value workflows, not every existing unit assertion.
- **Initial JSON message schema**:
  - `{"event": "key", "key": "J"}` sends a Qt key event to the active main window.
  - `{"command": "navigate", "path": "drums"}` directly moves the controller to a path relative to the fixture root.
  - `{"command": "focus", "row": 1}` focuses a visible browser row.
  - `{"command": "snapshot"}` returns the current JSON-serializable state without changing app state.
  - `{"assert": "path", "relative": "drums"}` verifies the current browser path.
  - `{"assert": "focus", "row": 0, "name": "kick.wav", "is_dir": false}` verifies browser focus.
  - `{"assert": "visible_rows", "names": ["kick.wav", "snare.wav"]}` verifies visible browser rows.
- **Simulation shell interface**:
  - `sampleman --simulation`
  - `sampleman gui --simulation`
  - `python -m sample_manager --simulation`
  - `sampleman --simulation-temp`
  - `sampleman gui --simulation-temp`
  - `python -m sample_manager --simulation-temp`
  - The shell reads one JSON object per stdin line and writes one JSON response per stdout line.
  - `--simulation-temp` creates a disposable SQLite database and sample library, bypassing real user config.

## 3. [Todo]

- [x] Inspect current GUI tests and identify workflows that are duplicated or hard to maintain.
- [x] Define a minimal JSON schema for GUI movement scenarios.
- [x] Decide whether schema validation is lightweight in-code validation or a formal JSON Schema file.
- [x] Add scenario fixtures/files under `tests/gui/scenarios/`.
- [x] Implement a scenario runner that maps JSON movement actions to `qtbot` operations and state assertions.
- [x] Port at least two representative movement workflows to JSON scenarios.
- [x] Keep existing imperative tests where they provide clearer low-level coverage.
- [x] Add failure messages that identify scenario name, step index, action, and assertion.
- [x] Run GUI-focused tests.
- [x] Update this report with first-slice implementation notes.
- [x] Expose the JSON simulation runtime through an application `--simulation` shell.
- [x] Add a temporary simulation environment that does not require `sampleman init`.
- [ ] Extend the runtime beyond movement into Stage, filter/search, dialogs, playback, and Arrangement workflows.

## 4. [Implementation + Revert]

### Implementation Plan

1. Add a small JSON scenario format with top-level metadata and ordered `steps`.
2. Support an initial action set:
   - `navigate`
   - `key`
   - `snapshot`
   - `focus`
   - `assert path`
   - `assert focus`
   - `assert visible_rows`
3. Implement a scenario runner in test code only, using `qtbot` and the existing `populated_service` fixture.
4. Add scenario files for core workflows:
   - browser navigation and focus movement
   - filtering and clearing filter state
   - add/remove stage behavior
   - dialog shortcut behavior where stable offscreen assertions exist
5. Add a pytest parametrized test that loads every JSON file in `tests/gui/scenarios/`.
6. Keep production code unchanged unless scenario execution reveals a legitimate missing test seam.
7. Document the supported JSON actions near the runner so future GUI tasks can add scenarios without reverse-engineering the runner.
8. Expose the same runtime through an explicit `--simulation` shell without changing normal GUI launch behavior.
9. Add an explicit temp simulation mode for isolated demo/agent runs.

### Revert Plan

1. Remove `tests/gui/scenarios/` and all JSON scenario files.
2. Remove `src/sample_manager/gui/simulation.py`.
3. Remove the parametrized JSON scenario test and shell tests.
4. Restore `src/sample_manager/gui/app.py` and `src/sample_manager/cli.py` to remove `--simulation`.
5. Remove temporary environment creation from `src/sample_manager/gui/simulation.py`.
6. Restore any modified `tests/gui/conftest.py` fixture changes if they only supported the JSON runner.
7. Re-run the original imperative GUI tests to confirm behavior returns to the pre-testbench state.
8. If production GUI code was changed only for the scenario runner, revert those changes and restore the previous public test surface.

## 5. [Invariance]

These behaviors must remain true after implementation:

- Existing `pytest-qt` GUI tests continue to pass without requiring a visible display server.
- `QT_QPA_PLATFORM=offscreen` remains the default for GUI tests.
- Tests continue to use temporary libraries and in-memory databases; no test depends on the developer machine's real sample library.
- JSON scenarios exercise user-observable behavior through Qt events where practical, not by bypassing the GUI into private implementation details.
- Normal GUI launch behavior is unchanged unless `--simulation` is explicitly passed.
- Real user config is untouched when `--simulation-temp` is used.
- Simulation code remains isolated in `src/sample_manager/gui/simulation.py` and does not alter widget/controller behavior.
- Existing shortcut semantics remain unchanged.
- Existing labels remain unchanged unless the active GUI design task explicitly changes them.
- Failures from JSON scenarios must be debuggable from pytest output without opening the JSON file and runner side by side.

## 6. [Implementation]

### Changed Files

- `src/sample_manager/gui/simulation.py` — added `GuiSimulationRuntime`, a JSON-object dispatcher around the real Qt main window, `run_simulation_shell()`, and a disposable temporary simulation environment.
- `src/sample_manager/gui/app.py` — added `--simulation` / `--simulation-temp` flag consumption and simulation shell launch paths.
- `src/sample_manager/cli.py` — added `--simulation` / `--simulation-temp` to the default launch callback and explicit `gui` command.
- `tests/gui/test_json_scenarios.py` — added a parametrized pytest entry point that loads every JSON file under `tests/gui/scenarios/`.
- `tests/gui/test_simulation_shell.py` — added JSON-lines shell tests.
- `tests/gui/scenarios/movement-vim-keys.json` — added a scenario covering `L`, `J`, `K`, and `H` browser movement/navigation.
- `tests/gui/scenarios/movement-arrow-keys.json` — added a scenario covering direct navigate command plus arrow-key movement/navigation.
- `tests/gui/scenarios/search-shortcut-focuses-filter.json` — added a scenario proving `/` focuses the browser search/filter field.
- `README.md` — documented real-config simulation and temp simulation launch commands.
- `tests/test_cli.py` — added CLI flag pass-through tests.
- `docs/reports/tasks/009-json-gui-testbench/task.md` — updated this report with the first implemented slice.
- `docs/reports/tasks/README.md` — updated the tracker status for Task 009.

### Behavior Implemented

The GUI testbench now has a first JSON simulation runtime.

- Scenarios are JSON files with ordered `steps`.
- Each step is a JSON object containing exactly one of `event`, `command`, or `assert`.
- `event: key` sends real Qt key events through `qtbot` to the active main window.
- `command: navigate` and `command: focus` provide deterministic setup primitives for scenario authors.
- `assert: path`, `assert: focus`, and `assert: visible_rows` verify movement-visible app state.
- `command: snapshot` returns the current state without mutation.
- `GuiSimulationRuntime.snapshot()` returns JSON-serializable state after each dispatch: current relative path, visible rows, focused row metadata, and Stage count.
- `sampleman --simulation`, `sampleman gui --simulation`, and `python -m sample_manager --simulation` enter a JSON-lines shell that dispatches against the real GUI.
- `sampleman --simulation-temp`, `sampleman gui --simulation-temp`, and `python -m sample_manager --simulation-temp` enter the same shell with a temporary SQLite DB and generated sample library.
- Normal GUI launch behavior is unchanged.

### Validation

- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui/test_json_scenarios.py -v`: PASS — 2 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui/test_json_scenarios.py tests/gui/test_simulation_shell.py -v`: PASS — 4 passed, 3 warnings.
- `.venv/bin/pytest tests/test_cli.py::test_default_simulation_option_launches_simulation_shell tests/test_cli.py::test_gui_command_simulation_option_launches_simulation_shell -v`: PASS — 2 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui -v`: PASS — 124 passed, 6 warnings.
- `.venv/bin/pytest tests/test_cli.py -v`: PASS — 20 passed.
- `.venv/bin/sampleman --help`: PASS — app-level `--simulation` option displayed.
- `.venv/bin/sampleman gui --help`: PASS — `gui --simulation` option displayed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui/test_simulation_shell.py tests/gui/test_json_scenarios.py -v`: PASS — 5 passed, 4 warnings.
- `printf ... | QT_QPA_PLATFORM=offscreen .venv/bin/sampleman --simulation-temp`: PASS — shell returned `drums`, `loops`, then `kick.wav`, `snare.wav`.

### Follow-ups / Risks

- The JSON schema should stay intentionally small; over-modeling the GUI can create a second brittle UI automation framework.
- The runner should favor workflows that are painful to express imperatively, while keeping simple widget/model unit tests as normal Python tests.
- Offscreen Qt behavior can differ from real interaction for focus and shortcut delivery, so the runner must preserve existing activation/focus safeguards from `tests/gui/test_interactions.py`.
- The full GUI test run still emits an asynchronous waveform worker teardown traceback after pytest reports success; that appears outside the JSON movement runtime and should be handled as a separate audio/worker lifecycle task.
