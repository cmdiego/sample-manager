# Feature Specification: Interactive Waveform Rendering & Navigation

**Feature Branch**: `001-interactive-waveform`

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Take a look inside @docs/prompts/interactive-waveform.md for the next feature specs"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — High-Fidelity Terminal Waveform (Priority: P1)

A user browsing their sample library in the terminal sees a waveform preview for the focused
sample that is visibly more detailed than the current block-character rendering. The finer
vertical resolution lets them quickly assess a sample's shape, attack, sustain, and density
before auditioning it.

**Why this priority**: This is the most visible quality improvement. It delivers standalone value
without requiring any playback changes, and it enables meaningful waveform navigation (P3) by
giving the user a richer visual target to aim for.

**Independent Test**: Open the terminal UI, focus any audio file. The waveform panel shows
noticeably higher vertical resolution compared to the previous rendering at the same terminal
width. No playback or navigation code needs to be present.

**Acceptance Scenarios**:

1. **Given** the terminal UI is open and an audio file is focused, **When** the waveform panel
   renders, **Then** the waveform displays at higher vertical resolution than the current
   block-character implementation.
2. **Given** the terminal is resized, **When** the waveform redraws, **Then** it adapts to the
   new width without corrupting the display.
3. **Given** the renderer fails to load (missing optional dependency), **When** the waveform
   panel renders, **Then** it falls back gracefully to a visible error or the previous renderer
   rather than crashing.

---

### User Story 2 — Smooth Playback Position Indicator (Priority: P2)

A user listening to a sample in either the terminal or desktop interface sees a playhead
indicator that moves smoothly and stays accurately synchronized with the audio position. Starting
playback, pausing, and resuming all feel immediate. The waveform display never stutters or
freezes while audio is playing.

**Why this priority**: Responsive playback feedback is foundational. Without it, P3 (keyboard
seek) and P4 (click-to-seek) feel unreliable even if the underlying logic is correct.

**Independent Test**: Play a sample in either frontend. The playhead moves smoothly across the
waveform for the duration of the file. Pressing pause immediately stops it. This story is
testable independently of any navigation changes.

**Acceptance Scenarios**:

1. **Given** a sample is playing, **When** the playback position advances, **Then** the playhead
   indicator moves continuously and remains synchronized with the audio.
2. **Given** a sample is playing, **When** the user pauses, **Then** the playhead stops at the
   correct position immediately.
3. **Given** a waveform is being generated for a new file, **When** audio from the previous file
   is still playing, **Then** playback is not interrupted or delayed by waveform generation.
4. **Given** a sample has finished playing, **When** playback completes, **Then** the playhead
   returns to the start and the indicator clears.

---

### User Story 3 — Keyboard Waveform Navigation in the Terminal (Priority: P3)

A terminal user can enter a dedicated waveform navigation mode to scrub through a loaded sample
using the keyboard. They can move a cursor left and right (fine and coarse steps), jump to the
beginning or end, confirm a seek position to update audio playback, and exit back to normal
browsing mode. The controls do not conflict with existing application shortcuts.

**Why this priority**: Waveform navigation is a core workflow enhancement for terminal users who
cannot use a mouse. It depends on a usable waveform display (P1) and accurate playback state
(P2).

**Independent Test**: With a sample focused and loaded, activate waveform navigation mode. Move
the cursor left and right. Press Enter to seek to the cursor position. Audio playback jumps to
that position. Press Escape to exit mode. This story is fully testable in the TUI alone.

**Acceptance Scenarios**:

1. **Given** a sample is focused, **When** the user activates waveform navigation mode, **Then**
   the waveform widget enters navigation mode and displays a visible cursor.
2. **Given** the user is in waveform navigation mode, **When** Left/Right is pressed, **Then**
   the cursor moves by a fine step in the corresponding direction.
3. **Given** the user is in waveform navigation mode, **When** Shift+Left/Right is pressed,
   **Then** the cursor moves by a larger step.
4. **Given** the user is in waveform navigation mode, **When** Home is pressed, **Then** the
   cursor jumps to the very beginning of the waveform.
5. **Given** the user is in waveform navigation mode, **When** End is pressed, **Then** the
   cursor jumps to the very end.
6. **Given** the user is in waveform navigation mode, **When** Enter is pressed, **Then** audio
   playback seeks to the cursor's position and the playhead updates accordingly.
7. **Given** the user is in waveform navigation mode, **When** Escape is pressed, **Then** the
   waveform widget exits navigation mode and returns to normal display without seeking.
8. **Given** the app is in normal browsing mode, **When** the waveform navigation keybindings
   are checked, **Then** none conflict with existing application shortcuts.

---

### User Story 4 — Mouse Click-to-Seek in the Desktop Interface (Priority: P4)

A desktop user can click anywhere on the waveform display to instantly jump audio playback to
that position. The playhead moves to the clicked location and audio resumes from there. An
optional enhancement allows click-and-drag scrubbing.

**Why this priority**: The GUI already supports zoom and pan via the mouse. Adding seek completes
the interaction model for desktop users. It depends on a working shared playback controller (P2).

**Independent Test**: Open the GUI, focus a sample, start playback. Click on any point in the
waveform. Audio playback jumps to that position. This story is testable independently of any TUI
work.

**Acceptance Scenarios**:

1. **Given** a sample is loaded in the GUI waveform widget, **When** the user left-clicks on a
   point in the waveform, **Then** audio playback seeks to the corresponding time position.
2. **Given** the user clicks near the start of the waveform, **When** seeking completes, **Then**
   the playhead moves to the start of the visible position.
3. **Given** the waveform is zoomed in, **When** the user clicks on a visible point, **Then**
   the seek position corresponds to the zoomed view, not the raw click pixel.
4. **Given** a sample is not loaded, **When** the user clicks on the waveform area, **Then**
   no seek action occurs and no error is raised.

---

### Edge Cases

- What happens when a very short sample (< 1 second) is displayed at full terminal width?
- How does waveform navigation behave when the waveform is still loading?
- What happens when seek is triggered but the audio decoder encounters an error mid-file?
- How does the playhead render when the file is playing but the waveform has not yet generated?
- What happens when the user resizes the terminal while in waveform navigation mode?
- How does click-to-seek interact with the zoom window in the GUI (does it seek based on the
  visible portion or the full file)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The terminal waveform MUST render at noticeably higher vertical resolution than the
  current block-character implementation at standard terminal widths.
- **FR-002**: The terminal waveform renderer MUST remain replaceable without modifying the
  waveform data or playback layers.
- **FR-003**: The playback position indicator MUST update continuously and independently of
  waveform data generation in both frontends.
- **FR-004**: Waveform generation MUST NOT block or interrupt audio playback at any time.
- **FR-005**: Waveform data for a given file MUST be generated at most once and reused for
  subsequent replays and frontend switches during a session.
- **FR-006**: Terminal users MUST be able to enter a dedicated waveform navigation mode that
  supports fine seek (Left/Right), coarse seek (Shift+Left/Right), boundary jumps (Home/End),
  seek confirmation (Enter), and mode exit (Escape).
- **FR-007**: The waveform navigation keybindings in the terminal MUST NOT conflict with any
  existing application modes or shortcuts.
- **FR-008**: Desktop users MUST be able to left-click on any position in the waveform to seek
  audio playback to the corresponding time position.
- **FR-009**: Both frontends MUST derive playback position from the same shared playback
  controller and display consistent state.
- **FR-010**: When the waveform widget receives a seek action while no file is loaded, it MUST
  ignore the action without raising an error.

### Key Entities

- **WaveformData**: An immutable representation of a decoded audio file's amplitude envelope,
  keyed by file path and file identity (size + modification time). Shared across all frontends.
- **Playback Controller**: A single shared source of truth for current play state, position,
  duration, and path. Both frontends observe the same controller.
- **Waveform Navigation Cursor**: A position within the waveform (expressed as a normalized
  fraction 0..1) that the user can move independently before confirming a seek.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The terminal waveform is visibly higher resolution than the current implementation
  at 80-column and 120-column terminal widths.
- **SC-002**: Play, pause, and seek operations feel immediate; users perceive no lag between
  input and response.
- **SC-003**: The playback position indicator moves smoothly and remains accurately synchronized
  with audio throughout playback.
- **SC-004**: Terminal users can seek to any position in the waveform in 3 keystrokes or fewer
  from normal browsing mode (activate mode, move cursor, confirm).
- **SC-005**: Reopening or replaying the same sample displays the waveform instantly, without
  re-generating waveform data.
- **SC-006**: GUI and terminal interfaces show consistent playback position when the same file
  is active in both.
- **SC-007**: No audio dropout or perceptible glitch occurs during waveform navigation or seek.

## Assumptions

- The existing `WaveformService` LRU cache (64 entries, keyed by path + file identity) satisfies
  the in-memory caching requirement without structural changes.
- The existing `AudioPlayer` shared model satisfies the shared-playback-controller requirement
  for both frontends; the primary addition needed is a public `seek(position_seconds)` method.
- The terminal waveform widget's rendering strategy is abstracted so that the Braille renderer
  (candidate: textual-plotext) can be adopted without modifying the waveform data or audio layers.
- Persistent (on-disk) waveform cache is explicitly out of scope for this feature.
- Waveform editing, destructive audio operations, zoom history, markers, loop regions, beat
  grid, spectral visualization, and multi-track are out of scope.
- Waveform navigation in the terminal produces a seek action on the existing `AudioPlayer`; the
  player does not need to be replaced or refactored, only extended.
- The GUI click-to-seek interaction respects the current zoom window: a click at a given pixel
  maps to the corresponding position within the zoomed view, not the raw file position.
- The final TUI keybindings are subject to a non-conflict review against `tui/keybindings.py`
  and `tui/modes.py` before implementation is locked in.
