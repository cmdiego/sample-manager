# Task 021 — Preserve the TUI Waveform on Selection

- **Status**: In Progress
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
- [ ] Reproduce repeated Enter using the production waveform request path.
- [ ] Preserve loaded/loading/error waveform state for the same sample.
- [ ] Test sample changes and late waveform completion.
- [ ] Run focused and full suites, review, commit incrementally and publish PR.

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

- Pending implementation.

### Behavior Implemented

- Found that every preview refresh removes/recreates its children, while cached waveform data is synchronously sent to a widget being removed.

### Validation

- Pending regression reproduction and test suites.

### Follow-ups / Risks

- Existing navigation pilots stub `_request_waveform`; new tests must exercise the production request/display lifecycle.
