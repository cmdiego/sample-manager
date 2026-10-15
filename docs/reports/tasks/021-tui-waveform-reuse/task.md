# Task 021 — Preserve the TUI Waveform on Selection

- **Status**: Done
- **Created**: 2026-10-14
- **Owner**: Codex
- **Origin**: User reports repeated Enter leaves the current waveform loading forever
- **Scope**: Preserve the current sample's waveform across selection and metadata refreshes, and test asynchronous loading against real mounted widgets.

## 1. [Struct]

- **Primary areas**: `tui/widgets/top_display.py`, `tui/app.py` waveform request handling.
- **Supporting areas**: Mounted TUI waveform regressions and task tracker.
- **Ownership**: App owns the active waveform request/data; TopDisplay owns the mounted presentation; WaveformService owns decoding/cache.
- **Expected changes**: Presentation lifecycle and tests. Database, GUI and audio transport services remain outside this fix.

## 2. [Interfaces]

- **User-facing**: Return continues toggling Stage membership while the waveform stays visible.
- **Internal**: Keep a stable current waveform widget; avoid reapplying loaded data on unchanged refreshes; preserve errors during refresh.
- **Persistence/config**: None.
- **Events**: Selection/metadata refresh, asynchronous waveform success/failure, sample focus changes.
- **Tests**: Real Textual key delivery and rendering, with controlled decoding and isolated sample files.

## 3. [Todo]

- [x] Inspect preview remounting and waveform cache handling.
- [x] Reproduce repeated Enter using the production waveform request path.
- [x] Preserve loaded/loading/error waveform state for the same sample.
- [x] Test sample changes and late waveform completion.
- [x] Run focused and full suites, review and prepare incremental commits for PR publication.

## 4. [Implementation + Revert]

### Implementation Plan

1. Add a mounted regression that loads a waveform and toggles the sample twice.
2. Preserve the same waveform widget during metadata/selection refreshes and route asynchronous updates to its current reference.
3. Verify no redundant decode, no stale result on sample changes, and preserved cursor/error state.

### Revert Plan

1. Revert Task 021 implementation commits and its waveform lifecycle regression tests.
2. Restore prior TopDisplay and app waveform request behavior from the branch parent.
3. No configuration or data rollback is needed.

## 5. [Invariance]

- Enter still toggles Browser selection and removes the selected Stage row.
- Metadata and tags refresh independently of waveform loading.
- A different focused sample receives its own waveform; stale requests cannot overwrite it.
- Playback progress and waveform navigation survive refreshes for the same sample.

## 6. [Implementation]

### Changed Files

- `tui/widgets/top_display.py` — retain the current waveform widget when the sample path matches; refresh metadata rows independently; target waveform setters through a synchronous reference rather than querying outgoing children.
- `tui/app.py` — return immediately for the current waveform request, preserving loaded data, an in-flight load or a completed error.
- `tests/test_tui_waveform_lifecycle.py` — real mounted preview/worker regressions using isolated SQL and controlled decoding.

### Behavior Implemented

- Found that every preview refresh removes/recreates its children, while cached waveform data is synchronously sent to a widget being removed.
- Repeated Enter now only changes selection/metadata; the existing waveform remains mounted and is decoded once.
- Metadata refresh preserves seek and playback cursors. Refresh during decoding retains the worker target, and refresh after decoding failure retains the error message instead of returning to loading forever.
- Changing samples creates a new waveform target; canceled/stale completions cannot overwrite the focused sample's data.

### Validation

- Before the fix, the new repeated-Enter regression failed because the displayed waveform lost its data after Enter.
- Focused lifecycle/widget/waveform/tag suite: 89 passed before adding the successful in-flight completion parameter.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/`: 918 passed, 10 existing deprecation warnings, including all five new lifecycle regressions.
- `git diff --check`: passed; reviewed production changes limited to preview ownership and same-path request handling.

### Follow-ups / Risks

- Prior navigation pilots stubbed `_request_waveform`; the new regressions exercise the production request/display lifecycle and actual rendered waveform state.
- No known blockers. Branch: `codex/tui-waveform-reuse`, PR base: `main`.
