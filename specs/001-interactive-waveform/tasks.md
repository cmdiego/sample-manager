# Tasks: Interactive Waveform Rendering & Navigation

**Input**: Design documents from `specs/001-interactive-waveform/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Tests**: Included — the project constitution (Principle III) mandates TDD. Tests are written
before each implementation block and must fail before the implementation is written.

**Organization**: Tasks grouped by user story to enable independent delivery of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared state dependency)
- **[Story]**: Which user story: US1=Braille renderer, US2=Smooth playback, US3=TUI nav, US4=GUI seek

## Path Conventions

Single project layout at `src/sample_manager/` and `tests/`.

---

## Phase 1: Setup

**Purpose**: Confirm baseline before any changes. No code modifications.

- [X] T001 Run full test suite to establish baseline: `pytest tests/ -v` and `QT_QPA_PLATFORM=offscreen pytest tests/gui/ -v` — all must pass before any work begins

---

## Phase 2: Foundational — AudioPlayer.seek() (Blocking Prerequisite)

**Purpose**: Add the shared `seek()` API that US3 (TUI nav) and US4 (GUI click-to-seek) both depend on.

**⚠️ CRITICAL**: US3 and US4 cannot be fully implemented until this phase is complete.

- [X] T002 [P] Write failing unit tests for `AudioPlayer.seek()` in `tests/test_audio_player.py` — cover four cases: (1) seek while PLAYING: generation incremented, output paused, play re-queued from target frame; (2) seek while PAUSED: `_position_frames` updated, no output call; (3) seek while IDLE (no audio loaded): no-op, no exception; (4) clamp: `seek(-1.0)` clamps to frame 0, `seek(duration + 10)` clamps to last frame
- [X] T003 Implement `AudioPlayer.seek(position_seconds: float) -> None` in `src/sample_manager/audio/player.py` — acquire `_lock`; return early if `_closed`, `_path is None`, or `_audio is None`; compute `target_frame = max(0, min(int(position_seconds * self._audio.sample_rate), self._audio.frames - 1))`; if PLAYING: increment `_generation`, set `_position_frames = target_frame`, release lock, pause output, re-queue `(generation, self._path)`; if PAUSED/IDLE/LOADING: set `_position_frames = target_frame` only (depends on T002 tests failing first)
- [X] T004 Run `pytest tests/test_audio_player.py -v -k seek` — all seek tests must pass before proceeding to user story phases (depends T003)

**Checkpoint**: `AudioPlayer.seek()` is complete and tested. US3 and US4 can now proceed.

---

## Phase 3: User Story 1 — High-Fidelity Terminal Waveform (Priority: P1) 🎯 MVP

**Goal**: Replace the block-character TUI waveform with a Unicode Braille renderer that delivers
~4× higher vertical resolution. Add navigation-cursor rendering support in the same pass.

**Independent Test**: `pytest tests/test_tui_waveform.py -v` — no GUI, no playback device needed.

### Tests for US1 (write first — must FAIL before implementation)

- [X] T005 [P] [US1] Write failing tests for `render_braille_waveform()` in `tests/test_tui_waveform.py` — assert: (1) all characters in output are in U+2800–U+28FF range or Rich markup (not `█`); (2) output line count equals `height` parameter; (3) character count per line equals `width // 2`; (4) `progress=0.5` places a visible playback cursor at mid-width; (5) `nav_cursor=0.75` places a distinct nav cursor at 75% of width; (6) flat silence (all-zero bins) renders as a flat center line; (7) `bins=()` returns empty `rich.Text` without error
- [X] T006 [P] [US1] Write failing tests for `WaveformWidget.set_nav_cursor()` and `nav_cursor_fraction()` in `tests/test_tui_waveform.py` — assert: (1) `set_nav_cursor(0.5)` causes `nav_cursor_fraction()` to return `0.5`; (2) `set_nav_cursor(None)` causes `nav_cursor_fraction()` to return `None`; (3) calling `set_loading(path)` auto-clears nav cursor; (4) calling `set_data(data)` auto-clears nav cursor; (5) calling `set_error(path, msg)` auto-clears nav cursor; (6) `set_nav_cursor(1.5)` is clamped to `1.0`; (7) `set_nav_cursor(-0.1)` is clamped to `0.0`

### Implementation for US1

- [X] T007 [US1] Implement `render_braille_waveform(bins, width, height=4, progress=0.0, nav_cursor=None)` in `src/sample_manager/tui/widgets/waveform.py` — pair adjacent display columns into Braille characters; encode min/max amplitude as dot patterns using the 2×4 Unicode Braille grid (U+2800 base, dot layout: row0=[0x01,0x08], row1=[0x02,0x10], row2=[0x04,0x20], row3=[0x40,0x80]); played columns in `bright_green`, unplayed in `green`; playback cursor (`│`) in `bold yellow`; nav cursor (`▌`) in `bold cyan`; zero line as `─` in `dim green`; return `rich.Text` with `\n` separating rows (depends on T005 failing first)
- [X] T008 [US1] Add `set_nav_cursor(fraction: float | None) -> None` and `nav_cursor_fraction(self) -> float | None` methods to `WaveformWidget` in `src/sample_manager/tui/widgets/waveform.py`; store as `self._nav_cursor: float | None = None`; clamp to [0.0, 1.0] when not None; call `self.refresh()`; add `self._nav_cursor = None` to the bodies of `set_loading()`, `set_data()`, and `set_error()` (depends on T006 failing first)
- [X] T009 [US1] Update `WaveformWidget.render()` in `src/sample_manager/tui/widgets/waveform.py` to call `render_braille_waveform(self._data.bins, width, height, self._progress, self._nav_cursor)` when `self._data is not None`; keep `render_waveform` function intact (do not remove it) as a documented fallback (depends T007, T008)
- [X] T010 [US1] Run `pytest tests/test_tui_waveform.py -v` — all US1 tests must pass (depends T007, T008, T009)

**Checkpoint**: US1 complete. Terminal waveform renders in Braille. Can demo independently.

---

## Phase 4: User Story 2 — Smooth Playback Position Indicator (Priority: P2)

**Goal**: Confirm the Braille renderer's progress cursor tracks playback correctly and the
200 ms polling loop remains non-blocking. Most infrastructure already exists; these tasks
verify it integrates correctly with the new renderer.

**Independent Test**: `pytest tests/test_tui_waveform.py -v -k progress` and
`pytest tests/test_audio_tui_integration.py -v`

### Tests for US2 (write first — must FAIL before implementation)

- [X] T011 [P] [US2] Write failing tests for Braille progress-cursor accuracy in `tests/test_tui_waveform.py` — assert: (1) `progress=0.0` produces no cursor column (cursor character absent); (2) `progress=0.25` places cursor at column `width // 8` (i.e., 25% of `width // 2` Braille chars); (3) `progress=1.0` places cursor at the last Braille column; (4) cursor character is never placed outside [0, width//2) range for any progress in [0.0, 1.0]

### Implementation for US2

- [X] T012 [US2] Verify `WaveformWidget.set_progress()` in `src/sample_manager/tui/widgets/waveform.py` calls `self.refresh()` when the value changes (confirm existing behavior — no change required if already correct; otherwise add the call); confirm `render()` passes `self._progress` to `render_braille_waveform` (already wired in T009) (depends T009)
- [X] T013 [US2] Run `pytest tests/test_tui_waveform.py -v -k progress` and `pytest tests/test_audio_tui_integration.py -v` — all must pass (depends T011, T012)

**Checkpoint**: US2 complete. Playback cursor moves correctly in the Braille renderer.

---

## Phase 5: User Story 3 — Keyboard Waveform Navigation in the Terminal (Priority: P3)

**Goal**: Add waveform nav mode (`w` to enter, arrows to move cursor, `Enter` to seek, `Escape` to
exit) to the TUI. Depends on `AudioPlayer.seek()` (foundational, T003) and the Braille nav-cursor
rendering (US1, T008).

**Independent Test**: `pytest tests/test_tui_waveform.py -v -k nav` — wires against a headless
`SampleManagerApp` instance; no real audio device required.

### Tests for US3 (write first — must FAIL before implementation)

- [X] T014 [P] [US3] Write failing tests for `AppMode.WAVEFORM_NAV` transitions in `tests/test_tui_waveform.py` — use Textual's `app.pilot()` or a direct handler call; assert: (1) pressing `w` in BROWSE mode with a loaded waveform sets `app._mode == AppMode.WAVEFORM_NAV` and initializes cursor to playback position; (2) pressing `w` in SEARCH mode is a no-op (mode stays SEARCH); (3) pressing `escape` from WAVEFORM_NAV returns to BROWSE without calling `AudioPlayer.seek()`; (4) pressing `enter` from WAVEFORM_NAV calls `AudioPlayer.seek()` with correct `cursor_fraction × duration_seconds` and returns to BROWSE
- [X] T015 [P] [US3] Write failing tests for nav-mode cursor movement in `tests/test_tui_waveform.py` — assert: (1) `left` moves cursor left by `1 / waveform_display_width` (fine step); (2) `right` moves cursor right by fine step; (3) `shift+left` moves cursor left by `10 × fine_step` (coarse); (4) `shift+right` moves cursor right by coarse step; (5) `home` sets cursor to `0.0`; (6) `end` sets cursor to `1.0`; (7) cursor is clamped at [0.0, 1.0] on boundary moves; (8) `up` and `down` are NOT captured (bubble through to list navigation)

### Implementation for US3

- [X] T016 [US3] Add `WAVEFORM_NAV = "waveform_nav"` to `AppMode` enum in `src/sample_manager/tui/modes.py` (depends T014 failing first)
- [X] T017 [US3] Extend `ACTION_DESCRIPTIONS` and `ACTION_CATEGORIES` in `src/sample_manager/tui/keybindings.py` — add entries: `waveform_nav_enter` ("Enter waveform navigation"), `waveform_seek_fine_left` ("Seek left (fine)"), `waveform_seek_fine_right` ("Seek right (fine)"), `waveform_seek_coarse_left` ("Seek left (coarse)"), `waveform_seek_coarse_right` ("Seek right (coarse)"), `waveform_seek_confirm` ("Confirm seek position"), `waveform_nav_exit` ("Exit waveform navigation"); add to "Playback" category
- [X] T018 [US3] Update `SampleManagerApp.on_key()` (or equivalent key handler) in `src/sample_manager/tui/app.py` — (1) when mode is BROWSE and key is `w` and `self._waveform_data is not None`: set `self._mode = AppMode.WAVEFORM_NAV`, initialize `_nav_cursor` from current playback position, call `top_display.set_nav_cursor(_nav_cursor)`; (2) when mode is WAVEFORM_NAV: consume `left`/`h` (fine left), `right`/`l` (fine right), `shift+left` (coarse left), `shift+right` (coarse right), `home` (0.0), `end` (1.0) — update `_nav_cursor` and call `top_display.set_nav_cursor()`; on `enter`: call `self._audio_player.seek(_nav_cursor × duration)`, clear nav cursor, return to BROWSE; on `escape`: clear nav cursor, return to BROWSE; all other keys pass through; fine step = `1 / max(1, waveform_display_columns)`, coarse step = `10 × fine_step` (depends T016, T017)
- [X] T019 [US3] Add `set_nav_cursor(fraction: float | None) -> None` delegation in `src/sample_manager/tui/widgets/top_display.py` — call `self._waveform_widget().set_nav_cursor(fraction)` if widget exists; mirrors existing `set_playback_progress` pattern
- [X] T020 [US3] Run `pytest tests/test_tui_waveform.py -v -k nav` — all nav mode tests must pass (depends T014–T019)

**Checkpoint**: US3 complete. Terminal users can seek with keyboard. Demo independently.

---

## Phase 6: User Story 4 — Mouse Click-to-Seek in the Desktop Interface (Priority: P4)

**Goal**: Single left-click on the Qt waveform widget seeks audio to the clicked position.
Drag-to-pan is preserved. Depends on `AudioPlayer.seek()` (foundational, T003).

**Independent Test**: `QT_QPA_PLATFORM=offscreen pytest tests/gui/test_waveform_widget.py -v -k seek`

### Tests for US4 (write first — must FAIL before implementation)

- [X] T021 [P] [US4] Write failing tests for `WaveformWidget.seek_requested` signal in `tests/gui/test_waveform_widget.py` — use `pytest-qt` `qtbot.waitSignal`; assert: (1) a click (press + release at same x) emits `seek_requested` with fraction ≈ `click_x / width` when not zoomed; (2) a drag (press at x=10, release at x=50, threshold=4 px) does NOT emit `seek_requested`; (3) in a zoomed state (`zoom_start=0.25, zoom_end=0.75`), click at 50% of widget width emits fraction `0.25 + 0.5 × 0.5 = 0.5`; (4) signal is NOT emitted when state is LOADING or EMPTY; (5) emitted fraction is clamped to [0.0, 1.0]

### Implementation for US4

- [X] T022 [US4] Add `CLICK_THRESHOLD_PX: int = 4` class constant and `seek_requested = Signal(float)` to `WaveformWidget` in `src/sample_manager/gui/widgets/waveform.py`; update `mouseReleaseEvent`: if `_pan_anchor_x is not None` and `abs(event.position().x() - _pan_anchor_x) < CLICK_THRESHOLD_PX` and `_state is _State.READY`: compute `fraction = _zoom_start + (event.position().x() / max(1, self.width())) * (_zoom_end - _zoom_start)`, clamp to [0.0, 1.0], emit `seek_requested(fraction)`; clear `_pan_anchor_x` in both branches (depends T021 failing first)
- [X] T023 [US4] Wire `seek_requested` signal to `AudioPlayer.seek()` in `src/sample_manager/gui/widgets/preview.py` — add `connect_player(player: AudioPlayer)` method that connects `self._waveform.seek_requested` to a lambda: `lambda frac: player.seek(frac * (player.snapshot().duration_seconds or 0.0))`; call this from `gui/app.py` or `BrowserController` after the player is set up
- [X] T024 [US4] Run `QT_QPA_PLATFORM=offscreen pytest tests/gui/test_waveform_widget.py -v -k seek` — all seek tests must pass (depends T021, T022, T023)

**Checkpoint**: US4 complete. GUI users can click-to-seek. All four user stories are done.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T025 [P] Verify `render_waveform()` (block-char renderer) is still present and importable in `src/sample_manager/tui/widgets/waveform.py` — run `python -c "from sample_manager.tui.widgets.waveform import render_waveform; print('ok')"` from `.venv`
- [X] T026 [P] Run full regression suite: `pytest tests/ -v` and `QT_QPA_PLATFORM=offscreen pytest tests/gui/ -v` — zero failures, zero new skips
- [X] T027 Follow validation scenarios in `specs/001-interactive-waveform/quickstart.md` — manually run all 4 scenarios against a real sample library and confirm acceptance criteria are met

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start here
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS US3 and US4**
- **Phase 3 (US1)**: Depends on Phase 1 only (no seek needed for Braille renderer)
- **Phase 4 (US2)**: Depends on Phase 3 (US1 must be wired)
- **Phase 5 (US3)**: Depends on Phase 2 (seek API) **AND** Phase 3 (nav cursor rendering in US1)
- **Phase 6 (US4)**: Depends on Phase 2 (seek API) only; independent of US1/US2/US3
- **Phase 7 (Polish)**: Depends on all desired stories being complete

### User Story Dependencies

```
Phase 1 (Setup)
    │
    ├──▶ Phase 2 (Foundational: seek API)
    │         │
    │         ├──▶ Phase 5 (US3: TUI nav) ──┐
    │         │                             ▼
    │         └──▶ Phase 6 (US4: GUI seek)  │
    │                                       │
    ├──▶ Phase 3 (US1: Braille renderer)    │
    │         │                             │
    │         └──▶ Phase 4 (US2: playhead)  │
    │              (also needed by US3) ────┘
    │
    └─────────────────────────────────────▶ Phase 7 (Polish)
```

**US3 requires BOTH Phase 2 (seek) AND Phase 3 (nav cursor).**
**US4 requires only Phase 2 (seek).**
**US1 and US4 can be worked in parallel after Phase 1.**

### Within Each Phase

- Constitution Principle III: Tests MUST be written and confirmed FAILING before implementation
- Each test file task [P] can run in parallel with other [P] test tasks in the same phase
- Implementation tasks depend on test tasks in the same phase

---

## Parallel Opportunities

### After Phase 1:

**Stream A** (Braille renderer): T002–T004 → T005–T010 → T011–T013 → T014–T020

**Stream B** (GUI seek): T002–T004 → T021–T024

Streams A and B share T002–T004 (foundational). After T004:
- Stream A: US1 work (T005–T010) can start immediately (no seek needed)
- Stream B: US4 work (T021–T024) can start after T004

```bash
# Parallel within Phase 2 (run together before implementation):
Task T002: Write seek tests in tests/test_audio_player.py

# After T002:
Task T003: Implement AudioPlayer.seek() in src/sample_manager/audio/player.py

# Parallel within Phase 3 (run together before implementation):
Task T005: Write render_braille_waveform tests in tests/test_tui_waveform.py
Task T006: Write WaveformWidget.set_nav_cursor tests in tests/test_tui_waveform.py

# After T005 + T006:
Task T007: Implement render_braille_waveform (depends T005)
Task T008: Implement set_nav_cursor (depends T006)
```

---

## Implementation Strategy

### MVP First (US1 only — Braille Renderer)

1. Complete Phase 1: baseline check (T001)
2. Complete Phase 3: US1 tasks (T005–T010) — Braille renderer independent of seek
3. **STOP AND VALIDATE**: `pytest tests/test_tui_waveform.py -v` + visual TUI check
4. Demo: `sampleman tui` shows Braille waveform

### Incremental Delivery

1. Phase 1 → Phase 3 (US1) → Demo Braille waveform
2. Phase 2 (seek API) → Phase 6 (US4) → Demo GUI click-to-seek
3. Phase 4 (US2) + Phase 5 (US3) → Demo TUI keyboard nav
4. Phase 7 (Polish) → Full regression

### Parallel Team Strategy

With two developers after Phase 1:
- Developer A: Phase 2 (seek API) → Phase 5 (US3 TUI nav)
- Developer B: Phase 3 (US1 Braille) → Phase 6 (US4 GUI seek)

---

## Notes

- `[P]` tasks touch different files and have no shared in-progress dependencies
- Each user story has an independent test checkpoint before the next story begins
- The existing `render_waveform()` (block chars) MUST NOT be removed — it is the documented fallback
- TDD: every test task must produce FAILING tests before the paired implementation task runs
- Commit after each phase checkpoint at minimum
