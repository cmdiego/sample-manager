# TUI: Waveform & Cover-Art Display

## Goal
Show the focused audio file's waveform and cover art in the TUI: render the waveform from the
audio domain's peak-array API, and display the file's embedded cover image, falling back to a
default stock image when the file has none.

## Context / Motivation
Next development step pairing with Task 005. Gives the browser a visual preview (waveform + art)
as the user moves focus, consistent with the Digitakt-inspired preview-on-cursor-movement idea.

## Dependencies
- **Blocked by**: Task 005 — requires `analysis.waveform_peaks(...)` and cover-art extraction from
  the audio domain. Do not start rendering until those APIs exist.
- **Read first**: `.claude/agents/tui-architect.md`, `src/sample_manager/tui/` (app, data, widgets),
  Task 005 plan + its reported API surface.

## Scope
- `waveform.py` widget: render the peak array (block/braille glyph envelope) for the focused file.
- `artwork.py` widget: display embedded cover art; when extraction returns None, show a bundled
  default stock image asset.
- Wire both to focus changes via the existing refresh path; audio access flows through
  `data.py` (TuiDataSource), never decoding audio inside widgets.

## Non-Goals
- Any audio decoding/analysis/peak computation in the TUI (that's Task 005/audio).
- Playback controls UI (can be a later task once the engine API is settled).

## Design / Approach
- Widgets are pure renderers of data handed to them; all CSS in `styles/app.tcss`; `update()` via
  `remove_children()`+`mount()`; no business logic duplication.
- `data.py` gains thin methods that call the audio APIs (peaks, artwork bytes) — keeping the
  layering: TUI → data source → audio domain.
- Ship a small default stock image asset under the tui package for the no-art fallback.
- Terminal image display: use a Textual-compatible approach (e.g. rich-pixels/ANSI blocks);
  document the chosen method and any capability limits.

## Implementation Steps
1. Add `data.py` pass-throughs to the Task 005 audio APIs (waveform peaks, cover-art bytes).
2. Implement the waveform widget; render on focus change.
3. Implement the artwork widget with the default-stock-image fallback.
4. Place the widgets in the layout; add CSS.
5. Add Pilot tests (waveform renders for a file; artwork falls back to stock when none).
6. Run `pytest tests/ -v`; confirm green.

## Testing
- Focusing an audio file renders a non-empty waveform region.
- A file with no embedded art shows the default stock image; one with art shows its image path/bytes.
- `pytest tests/ -v` stays green.

## Resolved Decisions
- TUI renders; audio provides data. Default stock-image fallback is a TUI responsibility.
