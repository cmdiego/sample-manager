# Task 010 — Search, Drag and Drop, and Focus

- **Status**: Done
- **Created**: 2026-10-13
- **Owner**: Codex
- **Origin**: user request
- **Scope**: Make sample discovery and Stage drag and drop usable in the GUI, restore reliable keyboard focus, and repair related TUI filtering behavior.

## 1. [Struct]

- **Primary area**: `src/sample_manager/gui/` browser, Stage, controller, and main window.
- **Supporting areas**: `src/sample_manager/services/library_browser.py`, `src/sample_manager/repos/sample_repo.py`, `src/sample_manager/tui/app.py`, and interaction tests.
- **Current ownership boundaries**: repositories own SQL; services return browser DTOs; GUI widgets emit intents; the controller updates models and Stage; the TUI owns terminal focus and typeahead state.
- **Files expected to change**: browser and Stage widgets, controller, main window, sample repository, browser service, GUI simulation scenarios/tests, TUI app/tests, user documentation.
- **Files expected to remain untouched**: audio playback and waveform files, schema migrations, export code, and user configuration.

## 2. [Interfaces]

- **User-facing interface**: GUI search field, Browser → Stage drag and drop, Space transport while searching, Escape and click-away focus exit; TUI typeahead movement and selection.
- **Internal API/interface**: `SampleRepo.search_by_text()` performs a root-scoped text search; `LibraryBrowserService.search_samples()` maps results to `BrowserItem`; `BrowserController.search()` switches between directory and search results without changing the current directory.
- **Persistence/config interface**: reuse existing sample and Stage tables; no migration or setting change.
- **Events/signals/commands**: search text changes trigger controller search; Qt drag MIME carries indexed sample IDs; Stage drop emits an add intent; TUI filtered cursor tracks the visible list. Space resumes paused audio, and Shift+Space inserts a literal search space.
- **Tests as interface contracts**: JSON GUI scenarios and offscreen Qt interaction tests, service/repository tests, TUI behavior tests, then the full suite.

## 3. [Todo]

- [x] Inspect existing GUI/TUI implementation and tests.
- [x] Identify prefix-only GUI filter and TUI filtered-focus mismatch.
- [x] Implement root-wide, case-insensitive substring and multi-term GUI search.
- [x] Index `.wave` files and repair combined CLI tag/name/path search.
- [x] Implement Browser → Stage drag and drop and keyboard focus exits.
- [x] Repair TUI filtered focus, matching, and empty state.
- [x] Replace the GUI's file-manager placeholder action.
- [x] Probe adjacent interaction behavior and document remaining pitfalls.
- [x] Add scenarios/tests and run validation.
- [x] Finalize this report and task tracker.

## 4. [Implementation + Revert]

### Implementation Plan

1. Add parameterized indexed-sample search to `SampleRepo` and expose results as browser DTOs through `LibraryBrowserService`; include `.wave` in scanning.
2. Switch the controller's browser model between the current directory and root-wide search results. Keep result paths available for preview and navigation.
3. Add an internal Browser drag payload and Stage drop handler; wire Stage's add intent to the existing controller operation.
4. Make Space a transport shortcut during search; make Escape clear and leave search; release search focus on click outside the field. Keep current audio playing while a query is typed.
5. Fix TUI substring matching and its visible-result cursor; repair combined CLI tag filtering and the GUI's file-manager action; exercise representative flows through JSON GUI simulation and terminal tests.

### Revert Plan

1. Remove Task 010 search methods from `sample_repo.py`, `library_browser.py`, and `controller.py`; restore local filtering in `browser.py`.
2. Remove drag payload/drop handlers and Stage signal wiring from GUI widgets and `main_window.py`.
3. Restore TUI filter handling in `tui/app.py`, CLI query building in `search.py`, and scanner extensions; remove Task 010 tests/scenarios.
4. Restore the pre-task README and tracker entries; delete this report; rerun the GUI/TUI suites.

## 5. [Invariance]

- Normal directory navigation still displays directories first and preserves the current root boundary.
- Stage remains persistent and duplicate additions remain idempotent.
- Existing playback controls and uncommitted waveform work remain intact.
- Search text never changes sample metadata or the active library root.
- GUI tests remain runnable with Qt's offscreen platform and isolated databases.

## 6. [Implementation]

### Changed Files

- `src/sample_manager/repos/sample_repo.py`, `src/sample_manager/services/library_browser.py`, `src/sample_manager/gui/controller.py` — root-scoped indexed search, result DTOs, and model switching.
- `src/sample_manager/gui/widgets/browser.py`, `src/sample_manager/gui/models/browser_model.py`, `src/sample_manager/gui/widgets/selection.py`, `src/sample_manager/gui/drag.py` — search UI and results, internal Browser drag payload, and Stage drop target.
- `src/sample_manager/gui/main_window.py`, `src/sample_manager/gui/shortcuts.py` — search focus and transport behavior, Stage wiring, file-manager action, and shortcut help.
- `src/sample_manager/scanner.py` — include `.wave` in scans.
- `src/sample_manager/search.py` — bind combined search parameters in SQL order and correctly handle overlapping expanded tag groups.
- `src/sample_manager/tui/app.py`, `src/sample_manager/tui/widgets/file_tree.py` — substring typeahead, visible cursor targeting, resume behavior, and no-match message.
- `src/sample_manager/gui/simulation.py`, `tests/gui/scenarios/search-and-focus.json` — JSON search typing, click, and focus scenario.
- `tests/gui/test_search_drag.py`, `tests/gui/test_interactions.py`, `tests/gui/test_playback_integration.py`, `tests/test_sample_search.py`, `tests/test_scanner.py`, `tests/test_search.py`, `tests/test_tui_filter.py`, `tests/test_audio_tui_integration.py` — regression coverage.
- `README.md` — search, drag, playback, and rescan instructions.

### Behavior Implemented

The GUI searches up to 500 indexed samples in the active root. Every whitespace-separated term can match a filename, relative path, tag name, shorthand, or alias, case-insensitively. Filename hits rank first and show their containing folder. Search typing preserves the current audition; Enter, Down, or click chooses a result. Space remains pause/resume while search has focus, Shift+Space inserts a search space, Escape clears search, and a click elsewhere releases typing focus while keeping results visible. Indexed Browser samples can be dragged into Stage, and invalid/stale payloads are ignored.

The TUI now matches name substrings, moves a real cursor through visible results with arrows, acts on the highlighted match, and says “no matches” for an empty filter result. Space resumes paused audio in both frontends. The GUI's “Open in file manager” action opens the containing folder.

### Validation

- Baseline `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`: 847 passed, 8 warnings.
- `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`: 863 passed, 9 existing Qt/audioread deprecation warnings.
- `sampleman --simulation-temp` JSON shell search/assertion smoke test: PASS.
- `git diff --check`: PASS.

### Follow-ups / Risks

- Drag implementation assumes Browser → Stage. Finder → library import and Stage → Arrangement remain separate workflow choices.
- The GUI and TUI both open only the first library root; there is no root switcher. The GUI has no in-app scan/rescan action, so pre-existing `.wave` files need a CLI rescan.
- TUI `Tab` is advertised as pane cycling but currently does nothing (`SampleManagerApp.on_key`). TUI typeahead still searches only the current directory, whereas GUI search spans its active root.
- Very large libraries may need debounced or indexed full-text search; the current GUI query runs against SQLite on each text change and caps visible hits at 500.
