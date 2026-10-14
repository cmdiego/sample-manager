# Feature: Interactive Waveform Rendering & Navigation

## Summary

Improve the waveform visualization subsystem used by both the TUI and future GUI by increasing waveform rendering quality, improving playback responsiveness, and adding waveform navigation (scrubbing/seeking).

The implementation should expose a common waveform rendering model while allowing each frontend (Textual TUI and GUI) to provide its own rendering backend.

---

# Problem Statement

The current waveform implementation has several shortcomings:

1. Waveform resolution is too low in the Textual TUI.
2. Playback state updates are sluggish.
3. Waveform rendering refreshes too slowly during playback.
4. Users cannot traverse (scrub/seek) through the waveform.
5. TUI and GUI currently have no unified interaction model.

---

# Goals

- Produce high-resolution waveform rendering in the terminal.
- Achieve responsive playback updates.
- Keep playback UI synchronized with audio playback.
- Allow seeking through the waveform.
- Share as much waveform logic as possible between GUI and TUI.

---

# Functional Requirements

## 1. High Resolution TUI Waveform

Replace the current low-resolution waveform rendering with a higher fidelity implementation.

### Preferred implementation

Investigate using:

- textual-plotext

This package wraps Plotext for Textual applications.

Plotext renders using Braille Unicode characters, allowing roughly 8× the vertical resolution of traditional terminal characters.

The waveform renderer should:

- decode the audio file
- generate amplitude samples
- downsample according to terminal width
- render inside a reusable Textual widget

The rendering implementation should remain replaceable.

---

## 2. Waveform Rendering Pipeline

Separate waveform generation from rendering.

Suggested architecture:

Audio Decoder

↓

Waveform Generator

↓

Waveform Cache

↓

Frontend Renderer

(TUI or GUI)

The renderer should never decode audio directly.

Waveform generation should happen once per audio file and be cached.

---

## 3. Playback Refresh Performance

Playback should feel responsive.

The playhead should update independently of waveform generation.

Requirements:

- playback start should feel immediate
- pause should feel immediate
- seek should feel immediate
- waveform redraws should never block audio playback

Waveform rendering should reuse cached waveform data whenever possible.

---

## 4. Shared Playback Model

Both frontends should use a shared playback controller.

The playback controller should expose:

- current playback position
- total duration
- play state
- playback notifications/events

Both GUI and TUI should observe the same playback state.

---

## 5. Waveform Navigation

Users should be able to navigate within the waveform.

Navigation should support:

- seeking
- scrubbing
- jumping to arbitrary positions

Seeking should update:

- audio playback position
- playhead indicator
- waveform viewport (if scrolling)

---

# TUI Interaction Requirements

The TUI has multiple interaction modes.

Investigate a dedicated waveform navigation mode.

Possible controls:

- Left / Right
  - move cursor
- Shift + Left / Right
  - faster seek
- Home
  - beginning
- End
  - end
- Enter
  - seek playback
- Escape
  - leave waveform mode

The final keybindings should not conflict with existing application modes.

---

# GUI Interaction Requirements

The GUI should expose equivalent functionality.

Required interactions:

- mouse click
  - seek playback

Optional enhancements:

- click-and-drag scrubbing
- mouse wheel zoom
- horizontal scrolling

The underlying playback logic should be shared with the TUI.

---

# Waveform Cache

Waveforms should be cached after generation.

The cache should avoid regenerating waveform data when:

- reopening a file
- replaying a file
- changing frontend

Future enhancements may include persistent waveform cache on disk.

This feature only requires an in-memory cache.

---

# Architecture Requirements

Introduce a frontend-independent waveform subsystem.

Suggested modules:

waveform/
decoder.py
generator.py
cache.py
renderer.py
playback.py

Frontend-specific renderers:

tui/
waveform_widget.py

gui/
waveform_widget.py

Business logic must remain independent from the rendering implementation.

---

# Performance Requirements

Waveform generation:

- should occur once per file

Playback:

- should remain responsive regardless of waveform size

Rendering:

- should redraw only changed regions when practical

No operation should block playback while rendering.

---

# Acceptance Criteria

## Waveform Quality

- waveform is visibly higher resolution than the current implementation
- Braille rendering is used if textual-plotext proves suitable

## Responsiveness

- play and pause feel immediate
- playback indicator moves smoothly
- waveform redraws do not noticeably stall playback

## Navigation

Users can:

- seek
- scrub
- jump to arbitrary positions

GUI mouse interactions and TUI keyboard interactions produce identical playback behavior.

## Architecture

Waveform generation is independent from rendering.

Playback logic is shared across all frontends.

Waveform rendering is replaceable.

---

# Technical Investigation

Evaluate whether textual-plotext should become the default TUI renderer.

Specifically investigate:

- rendering quality
- rendering performance
- refresh frequency
- integration with Textual
- API limitations
- CPU usage
- memory usage

Document findings before final implementation.

---

# Out of Scope

The following are explicitly excluded:

- waveform editing
- destructive audio editing
- zoom history
- markers
- loop regions
- beat grid
- spectral visualization
- persistent waveform cache
