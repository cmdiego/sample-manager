Task (005 — Audio: Media Player, Cover-Art Extraction & Waveform Data): extend the audio domain with playback, artwork extraction, and waveform peak data.

Read these docs first:
- docs/reports/tasks/005-audio-player-and-artwork/005-audio-player-and-artwork.md
- .claude/agents/audio-engineer.md  (your charter and domain boundary)
- src/sample_manager/audio/  (existing package from Task 004)

Scope (ONLY):
- engine.py: play/pause/stop/seek + output-device (sound routing) selection, behind a mockable,
  non-blocking interface.
- artwork.py: extract embedded cover-art bytes + mime (mutagen); return None when absent. Read-only.
- analysis.py: add a pure waveform_peaks(...) -> buckets of (min,max) data API.
- Playback backend goes under the optional [audio] extra; lazy import; degrade gracefully with no device.

Deliverables:
- The new modules + waveform data API; [audio] extra updated; tests (headless/mocked engine,
  artwork present/absent, waveform bucket envelope).
- Report the public API surface so the tui-architect (Task 006) can consume it.

Constraints:
- Do NOT render anything (no waveform pixels, no image widget, no stock-image fallback — that is
  Task 006/TUI). No Textual imports. No SQL/repo access. Analysis/extraction is read-only.

Testing required. Run pytest tests/ -v and report results; no reduction in passing tests.
