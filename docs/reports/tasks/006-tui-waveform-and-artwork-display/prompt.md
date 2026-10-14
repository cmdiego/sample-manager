Task (006 — TUI: Waveform & Cover-Art Display): render the focused audio file's waveform and cover art (with default stock-image fallback).

BLOCKED BY Task 005 — do not start until the audio domain exposes waveform_peaks(...) and
cover-art extraction. Consume those APIs; do not decode/analyze audio in the TUI.

Read these docs first:
- docs/reports/tasks/006-tui-waveform-and-artwork-display/006-tui-waveform-and-artwork-display.md
- docs/reports/tasks/005-audio-player-and-artwork/005-audio-player-and-artwork.md (and its reported API surface)
- src/sample_manager/tui/ (app.py, data.py, widgets/)

Scope (ONLY):
- widgets/waveform.py: render the audio peak array for the focused file.
- widgets/artwork.py: display embedded cover art; fall back to a bundled default stock image when none.
- data.py: thin pass-throughs to the audio APIs (peaks, artwork bytes). Wire display to focus changes.

Deliverables:
- The two widgets + default stock image asset; layout placement; CSS in styles/app.tcss.
- Pilot tests: waveform renders for an audio file; artwork falls back to stock when absent.

Constraints:
- CSS only in styles/app.tcss (no inline DEFAULT_CSS); update() via remove_children()+mount()
  (never refresh()); audio access only through TuiDataSource (data.py); no audio decoding in TUI.

Testing required. Run pytest tests/ -v and report results; no reduction in passing tests.
