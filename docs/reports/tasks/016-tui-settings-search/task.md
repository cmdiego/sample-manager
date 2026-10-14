# Task 016 — TUI Settings and Library Search

- **Status**: In Progress
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: User request to focus on TUI settings, search, and sample-manager workflow gaps
- **Scope**: Add editable TUI playback preferences and make search find indexed samples throughout the active library.

## 1. [Struct]

- **Primary areas**: `tui/app.py`, `tui/data.py`, `tui/widgets/filters_panel.py`, new TUI settings module and modal.
- **Supporting areas**: Shared library search, audio output device discovery, navigation DTO, TUI pilot tests.
- **Ownership**: Reuse `LibraryBrowserService` for indexed search; keep SQL in repositories and audio devices in the audio domain. Store TUI preferences under the existing YAML config's `tui` key.
- **Expected changes**: TUI modules, navigation search-row context, tests, README, task tracker.
- **Unchanged areas**: GUI preferences and database schema.

## 2. [Interfaces]

- **User interface**: F2 and command-palette Settings; output-device selector; auto-audition switch; visible config/database/library paths; Save and Cancel.
- **Search**: `/` activates an empty query; displayed text has no added slash. Match names, relative paths, and tags across the active indexed root. Escape restores directory browsing.
- **Persistence**: Preserve existing YAML keys and save `tui.auto_audition` plus `tui.audio_output`.
- **Integration**: Existing `AudioPlayer`, `SoundDeviceOutput`, `NullOutput`, and `list_output_devices`.
- **Contracts**: Mounted Textual tests for exact query text, nested hits, editing, modal input isolation, settings persistence and cancellation.

## 3. [Todo]

- [x] Verify current main and carry Task 015 into the main-based branch.
- [x] Reproduce slash display and current-directory-only search.
- [ ] Implement indexed root-wide search with clear query feedback.
- [ ] Add editable, persistent settings with discoverable entry points.
- [ ] Test modal isolation, device failures, search editing, and playback behavior.
- [ ] Compare common sample-manager capabilities and record actionable gaps.
- [ ] Run required checks, make incremental commits, and open a main-targeted PR.

## 4. [Implementation + Revert]

### Implementation Plan

1. Reuse the indexed library search and cache results per query; show relative path context and result count.
2. Remove the visual slash prefix, ignore a repeated activation slash on an empty query, support paste, and keep search active when text is deleted.
3. Add a settings modal with output selection, auto-audition, configuration paths, and Save/Cancel. Apply settings without allowing modal keys to reach Browser actions.
4. Validate real Textual input and persistence using temporary libraries and fake output devices.

### Revert Plan

1. Revert Task 016 commits touching TUI app/data/widgets/settings and navigation DTO context.
2. Restore the TUI tests, README, and tracker. Task 015 is independent and can remain.
3. Existing `tui` YAML preferences may be left in place; older versions ignore that key.

## 5. [Invariance]

- Source samples remain unchanged; Stage persists through SQLite.
- Escape returns to the previous directory cursor.
- Space remains global playback during search; settings controls own their keyboard events.
- Device discovery failure leaves System Default and Disabled available.
- Cancel never changes stored preferences or replaces the player.

## 6. [Implementation]

### Changed Files

- Pending.

### Behavior Implemented

- Baseline pilot confirmed the stored query is `Drum`, while the display adds `/Drum`. Nested samples are absent because matching only uses current directory rows.

### Validation

- Pending implementation.

### Follow-ups / Risks

- Capability audit references: [Sononym preferences](https://www.sononym.net/docs/manual/preferences/), [filtering](https://www.sononym.net/docs/manual/filtering/), [favorites](https://www.sononym.net/docs/manual/favorites/), and [XO interface overview](https://support.xlnaudio.com/hc/en-us/articles/16920363887645-Interface-Overview).
- Candidate gaps to probe: library rescan/add, favorites and tagging, preview volume/looping, result sorting, reveal-source action, and metadata filters.
