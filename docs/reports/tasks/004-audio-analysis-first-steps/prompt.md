Task (004 — Audio Analysis: First Steps): stand up the sample_manager.audio domain and implement basic multi-format audio analysis.

Read these docs first:
- docs/reports/tasks/004-audio-analysis-first-steps/004-audio-analysis-first-steps.md
- docs/00-vision.md
- src/sample_manager/exit_codes.py
- .claude/agents/audio-engineer.md  (your charter and domain boundary)

Scope (ONLY):
- Create src/sample_manager/audio/ with decode.py, metadata.py, analysis.py.
- Extract metadata (format, duration, sample rate, channels, bit depth) and compute basic
  features (peak, RMS) across WAV, FLAC, MP3, AAC, M4A/MP4, OGG.
- Choose libraries (soundfile / audioread / mutagen / numpy); add them as an OPTIONAL [audio]
  extra in pyproject.toml with lazy imports and graceful degradation when a backend is missing.
- Analysis is read-only; never mutate or move audio files.
- Do NOT render anything. Waveform/visual display is the tui-architect's job — you only produce
  data. Do not import Textual and do not write SQL.

Deliverables:
- The audio package with a clean typed API (e.g. AudioFeatures).
- pyproject.toml [audio] extra.
- Tests using synthetic tones (write a tiny WAV in-test); guard compressed-format tests behind
  backend availability so the suite stays hermetic.
- Report the public API surface so it can be wired into services/TUI later.

Testing required. Run pytest tests/ -v and report results; no reduction in passing tests.
