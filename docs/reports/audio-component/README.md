# Audio Component Report

This directory records the implementation history and current architecture of
`sample_manager.audio` as of 2026-07-07.

## Documents

- [`history.md`](history.md) — chronological record of requirements, implementation increments,
  changed decisions, validation, and deferred work.
- [`architecture.md`](architecture.md) — current module boundaries, public API, runtime behavior,
  dependency policy, integration contract, and known limitations.

## Current State

The Audio component is a headless Python domain package covering:

- lazy backend discovery and normalized audio errors;
- file decoding to normalized float PCM;
- decode-free container metadata;
- peak, RMS, and dBFS analysis;
- asynchronous single-track playback through an injected output port;
- a lazy `sounddevice` output adapter;
- signed min/max waveform envelopes and an in-memory waveform cache.

The Textual frontend consumes the package through `AudioPlayer`, `PlaybackSnapshot`, and
`WaveformService`. The audio package contains no Textual, SQL, repository, or rendering code.

## Verified Baseline

- **Full suite:** 601 passing tests.
- **Audio-focused suite:** 52 collected tests.
- **Available in the current development environment:** NumPy, soundfile, audioread, mutagen.
- **Unavailable in the current development environment:** sounddevice; real hardware playback
  therefore requires installing the `[audio]` extra and a functioning host output device.

## Historical Task Sources

- [Task 004 — Audio Analysis: First Steps](../tasks/004-audio-analysis-first-steps/task.md)
- [Task 005 — Audio Player and Artwork](../tasks/005-audio-player-and-artwork/task.md)
- [Task 006 — TUI Waveform and Artwork Display](../tasks/006-tui-waveform-and-artwork-display/task.md)
- [Task 007 — Qt GUI Migration](../tasks/007-qt-gui-migration/task.md)

Tasks 005 and 006 are planning records, not accurate completion reports. Artwork extraction and
display were not implemented. The delivered playback and waveform work is recorded in
[`history.md`](history.md).

