# Sample Manager v2: Design and Concepts

Status: draft for discussion · Reference project: [musikcube](https://github.com/clangen/musikcube)

v2 has two goals, in priority order:

1. **Audition latency.** A sample should be heard right after the key press,
   with no clicks or dropouts while the UI is busy. The design decides how much
   of the playback engine should move to native code (C++), and what that move
   costs.
2. **A more modern TUI**, using musikcube's layout and interaction ideas while
   keeping the keyboard model that v1 users already know.

---

## 1. What v1 does today (measured)

Each audition through `AudioPlayer.play()` (`src/sample_manager/audio/player.py`)
does the following:

1. **Decodes the whole file** before playing anything (`decode()` →
   `soundfile.read()` of every frame).
2. **Opens a new PortAudio `OutputStream`** for each file, at that file's
   sample rate. It stops and closes the previous stream first, and that
   `pause()` runs synchronously on the **UI thread** inside `_request_play`.
3. Runs the **audio callback in Python**. The callback takes an `RLock` and
   copies NumPy slices. Each callback needs the GIL.
4. Has **no fades**, so switching samples cuts the signal abruptly. That causes
   clicks.
5. **Decodes the same file a second time** for the waveform
   (`WaveformService.load`). It then builds 4096 bins in a Python loop over
   float64 data.

You can reproduce the numbers below with `python tools/bench_audition.py`
(48 kHz, 24-bit stereo, warm page cache, 4-core container).

| File            | v1 full decode | v1 envelope | first 2048 frames only | vectorised envelope |
|-----------------|---------------:|------------:|-----------------------:|--------------------:|
| one-shot 0.5 s  |         0.4 ms |       20 ms |                0.08 ms |              0.6 ms |
| loop 8 s        |         5 ms   |       23 ms |                0.07 ms |              1.0 ms |
| stem 60 s       |        33 ms   |       36 ms |                0.07 ms |              3.0 ms |
| stem 240 s      |       126 ms   |       91 ms |                0.09 ms |             12 ms   |

The bench also simulates a Python audio callback with a 256-frame (5.3 ms)
period while the main thread does pure-Python work, similar to Textual layout
and render:

| UI thread | wake-up p50 | p99    | deadlines missed |
|-----------|------------:|-------:|-----------------:|
| idle      | 0.14 ms     | 1.4 ms | 0 %              |
| busy      | 5.25 ms     | 6.5 ms | 6–15 % (3 runs)  |

**Reading the numbers:**

- The **GIL** is the hard limit. A busy Python thread holds it for up to
  `sys.getswitchinterval()` (5 ms) at a time, which is a whole period of a
  small buffer. v1 only avoids dropouts because PortAudio's default
  "high" latency buffers are large. That buffering adds tens of milliseconds
  of output latency to every audition.
- **Full decode** is cheap for one-shots but grows linearly with length:
  126 ms before the first sound of a 4-minute stem. A streaming reader needs
  less than 0.1 ms before it can start.
- **Opening a stream per file** costs time that depends on the backend. This
  was not measured: the container has no audio device. It is usually tens of
  milliseconds on ALSA/Pulse/CoreAudio. Measure it on real hardware with the
  engine instrumentation in §5.6.
- **The waveform path is pure overhead.** It repeats the decode and is about
  20–30× slower than a vectorised envelope.

**Conclusion:** most of the latency comes from **architecture**: full decode,
stream reopening, duplicate work, and large buffers. The language matters
mainly in one place: **the real-time callback must not need the GIL.** The
plan below takes the cheap architectural wins first. It then moves only the
real-time part into native code, behind a narrow interface.

---

## 2. Latency targets

Targets are measured from key press to the first non-silent frame handed to
the device. The engine reports that time stamp itself (§5.6).

| Scenario                                   | v2 target (p95) |
|--------------------------------------------|----------------:|
| Neighbour of the focused row (pre-warmed)  | ≤ 15 ms         |
| Any file, warm OS cache                    | ≤ 25 ms         |
| Any file, cold disk (SSD)                  | ≤ 40 ms         |
| Dropouts during UI activity / scan         | 0               |
| Clicks on switch / pause / seek            | 0 (2–5 ms fades)|

Budget for the pre-warmed case: input event to command ≈ 1 ms, command queue
to engine < 0.1 ms, head block already in RAM, device buffer of 2 × 128–256
frames at 48 kHz ≈ 5–11 ms, then a 2 ms fade-in.

---

## 3. The C++ question: what native code buys and what it costs

### Where native code helps

- **A callback that never touches the GIL.** This is the only reason that
  requires native code. With it, small buffers (128–256 frames) become safe,
  and output latency drops by tens of milliseconds.
- **Decoding off the GIL.** Scans, waveform jobs, and UI rendering can no
  longer delay decoding.
- **SIMD peak and loudness analysis** at scan time. This is useful, but
  vectorised NumPy already gets most of the benefit.

### Where it does not help

- Decoding is **already native**: libsndfile runs underneath `soundfile`.
  Rewriting the decode call in C++ gains almost nothing.
- Persistent streams, head caching, a single shared decode, and vectorisation
  are **design changes**. Python can do all of them.
- UI responsiveness depends on Textual rendering. A C++ engine does not
  change that.

### Costs of a native engine

| Cost                     | Notes and mitigation |
|--------------------------|----------------------|
| Build and distribution   | Wheels for macOS arm64/x86_64, Linux x86_64/aarch64 and Windows. Use `scikit-build-core` and `cibuildwheel` in CI. This is the largest ongoing cost. |
| Contributor barrier      | Two languages and two toolchains. Keep the engine small (target ≤ 2–3k LOC) with a stable interface, so most work stays in Python. |
| Crash surface            | A segfault takes down the whole app. Use ASan/UBSan in CI and fuzz the decoders. Use few dependencies (miniaudio and dr_libs are single-header C libraries that are widely used). |
| Debugging                | Engine logs go to a lock-free ring that Python drains, plus the `sampleman engine bench` / `engine stats` commands. |
| **Cost of each FFI call** | **Small, if the interface is designed well.** One nanobind or C-ABI call costs on the order of 0.1–1 µs. At command rate (key presses, ≤ 100/s) that is negligible. Calls become expensive only when they happen **per buffer**. Rule: Python never passes PCM data and never runs inside the callback. |

### Options compared

| Option | What it is | Latency ceiling | Cost | Verdict |
|---|---|---|---|---|
| **A. Python, re-architected** | Persistent stream, streaming reader, head cache, single decode, fades | Limited by the GIL; needs ~512–1024-frame buffers (11–21 ms of buffering, plus jitter) | Low | **Do first.** Most of the gain at low cost, and it is the fallback in every later phase. |
| **B. C++ engine in-process** | miniaudio + dr_libs/libsndfile, C ABI, nanobind wrapper | Meets all §2 targets | Medium | **Recommended target.** This is musikcube's model, reduced to what we need. |
| C. Rust engine in-process | cpal + symphonia, PyO3 + maturin | Same as B | Medium (maturin makes wheels easier; memory safety) | Equal technically. Choose it instead of B if the maintainers prefer Rust. |
| D. Engine as a separate process | B or C behind a local socket, like musikcube's `server` plugin | Same as B, plus about 0.1 ms for IPC | Higher | Postpone. Worth it only if the GUI, TUI and CLI should share one live engine. |

**Recommendation:** ship option A in v2.0-alpha. It is measurable, cheap, and
needs no toolchain changes. Then build option B behind the **existing
`AudioPlayer`/`AudioOutput` ports**, so Textual, Qt and the tests do not change.
Make B the default only once it beats A on the §2 metrics on real hardware.
Keep A as the automatic fallback when the extension cannot be imported.

---

## 4. Lessons from musikcube

musikcube is a C++ player with a core library (`src/musikcore`), a TUI built
on its own ncurses wrapper (`cursespp`), and a plugin SDK with **C ABI
interfaces** for decoders, outputs, DSP and metadata. Its source tree has
these relevant parts:

| musikcube                                    | Idea we borrow                                       | v2 equivalent |
|----------------------------------------------|------------------------------------------------------|---------------|
| `audio/Player`, `Stream`, `Buffer`           | Decoding into pooled buffers on a separate thread from output | `Voice`, `SourceReader`, `BlockPool` |
| `GaplessTransport`, `Crossfader`             | A transport that owns several players and their fades | `AuditionTransport`: 2 voices, 2–5 ms micro-fades, voice stealing |
| Output plugins (`alsaout`, `pulseout`, `pipewireout`, `wasapiout`, `coreaudioout`, `portaudioout`, `nullout`…) | Interchangeable outputs, including a null output | One dependency, **miniaudio**, which covers the same backends. `NullOutput` stays for tests. |
| `PlaybackService` above the transport        | App-level service separate from the real-time engine | Python `AuditionService` (queue, focus prefetch, settings) |
| `Visualizer`, DSP plugins (`supereqdsp`)     | Post-mix taps                                         | Peak/RMS meter tap, later pitch/tempo DSP |
| `musikcore_c.h` / SDK headers                | **A stable C interface** as the language boundary     | `sm_engine.h`: a C ABI that nanobind (or ctypes) wraps |
| `server` plugin (WebSocket remote)           | Remote control of the engine                          | Option D, later |
| `cursespp` layouts, shortcut bar, JSON themes | Switchable layouts, a persistent status bar, theme files | §6 |

What we **do not** copy: gapless playback and playlists, the per-OS output
plugin binaries, and a C++ UI. musikcube's UI is C++ because the whole
application is. Sample Manager's UI is Python and stays in Python.

---

## 5. v2 audio engine architecture

### 5.1 Threads and data flow

```
 Python (UI / services)                Native engine (no GIL)
 ─────────────────────                 ─────────────────────────────────────────
 AuditionService ──cmd──▶ SPSC command queue ──▶ Control thread
   play(id, path)                                 │ resolves path → cache / reader
   prefetch([paths])                              ▼
   pause / seek / stop                    Decoder pool (1–2 threads)
                                            stream header + head block first
 poll() @30 Hz ◀── atomic snapshot ◀──┐    resample to device rate (if needed)
 events()      ◀── SPSC event queue ◀─┤    fill BlockPool / HeadCache
                                      │           │ lock-free ring per Voice
                                      │           ▼
                                      └── RT callback (miniaudio, persistent stream)
                                            mix ≤2 voices · micro-fade · meter tap
                                            no locks · no alloc · no I/O · no GIL
```

### 5.2 Key mechanisms

- **Persistent device stream.** Open the stream once at the device's native
  rate and keep it open, outputting silence when idle. Changing the output
  device swaps the stream in place. This removes v1's per-file stream
  open/close.
- **Streaming source reader.** Read the header and the first block (about
  0.1 ms in the measurements above), start playback, and let the decoder stay
  ahead by about 200 ms. Files ≤ 10 s are decoded completely into RAM, because
  that is cheap and makes seeking instant.
- **Head cache with focus prefetch.** When the cursor moves, the service sends
  `prefetch()` for the ±N neighbouring rows (N defaults to 3). The engine
  stores the first ~500 ms of each in a byte-bounded LRU (default 64 MB).
  Moving j/k through a folder then hits RAM every time. This works like
  musikcube preparing the next track for gapless playback, but applied to the
  browser cursor.
- **Two voices and micro-fades.** Starting a new sample fades the current voice
  out over 3 ms while the new one fades in. Pause and seek fade as well. This
  removes v1's clicks.
- **One decode, many consumers.** The reader's blocks also feed the peak
  analyser. The waveform no longer decodes the file a second time (§5.4).
- **Lock-free state.** A seqlock snapshot holds status, position in frames,
  duration, the current sample id, peak/RMS levels, xrun count and the
  latency timestamps. Python reads it at UI frame rate, so polling never
  blocks the audio.

### 5.3 C interface (sketch)

```c
// sm_engine.h — the only boundary between Python and native code.
typedef struct sm_engine sm_engine;

sm_engine* sm_engine_create(const sm_config* cfg);   // device, buffer frames, cache MB
void       sm_engine_destroy(sm_engine*);

int  sm_play(sm_engine*, uint64_t token, const char* utf8_path, double start_s);
int  sm_prefetch(sm_engine*, const char* const* paths, size_t count);
int  sm_pause(sm_engine*);  int sm_resume(sm_engine*);
int  sm_seek(sm_engine*, double seconds);
int  sm_set_device(sm_engine*, const char* device_id);

void   sm_snapshot(const sm_engine*, sm_state* out);         // wait-free read
size_t sm_poll_events(sm_engine*, sm_event* out, size_t max); // finished, error, xrun
int    sm_peaks(const char* path, uint32_t buckets, float* min_out, float* max_out);
```

All calls are non-blocking and only enqueue a command. The `token` plays the
role of v1's `generation` counter: stale completions are ignored.

### 5.4 Waveforms and analysis move to scan time

- During a scan, the engine's `sm_peaks` (or the vectorised NumPy fallback)
  computes a **multi-resolution peak pyramid** (4096 → 1024 → 256 bins). It
  also records true peak, RMS/LUFS-short and duration. These are stored in
  SQLite (a `sample_analysis` table with a BLOB column) and keyed by
  `(sample_id, size, mtime_ns)`.
- When a row gets focus, its waveform is read from the database (well under
  a millisecond). Files that were never analysed are computed lazily and
  saved.
- Loudness data allows optional **audition level matching**, so quiet and loud
  samples play back at a similar perceived volume.

### 5.5 Python side

- `NativeAudioPlayer` implements the same interface as `AudioPlayer`
  (`play`, `play_from_start`, `pause`, `seek`, `snapshot`, `close`), so
  `tui/app.py` and the Qt `controller.py` do not change.
- `build_tui_player()` picks the native player when
  `sample_manager._engine` imports. Otherwise it falls back to the improved
  Python player. `config.yaml` gets `audio.engine: auto | native | python`.
- Neither the UI thread nor `pause()` ever waits on device I/O. This fixes
  v1's synchronous `stream.stop()`.

### 5.6 Instrumentation

- The engine time-stamps `t_cmd` (command enqueued), `t_ready` (first block
  available) and `t_out` (first non-silent frame written to the device
  buffer), then adds the device's reported output latency.
- A new `sampleman engine bench <folder>` command auditions N files in a
  fixed sequence and prints p50/p95/p99 for each stage, plus xruns. It runs
  with both engines, so the two can be compared on the same hardware.
- An optional loopback test (output wired to input) gives the true
  acoustic latency for the release notes.

### 5.7 Build and packaging (option B)

- `engine/` directory: C++20, miniaudio, dr_wav/dr_flac/dr_mp3, and
  libsndfile when available, for AIFF/OGG/CAF. Python binding with nanobind.
- `scikit-build-core` backend. `cibuildwheel` on GitHub Actions builds the
  wheel matrix. The sdist builds from source.
- CI: unit tests in C++ (doctest), ASan/UBSan job, and a smoke test in
  Python using miniaudio's null backend (works headless). The existing pytest
  suite runs against both engines.

---

## 6. TUI v2

### 6.1 Principles taken from musikcube

1. **Content first, borders second.** v1 uses five coloured borders
   (white, blue, orange, red, green, purple). v2 uses thin neutral dividers.
   Only the **focused** pane gets the accent colour, the way musikcube
   highlights the active window.
2. **A persistent transport bar** at the bottom on every screen: what is
   playing, a full-width waveform with a playhead, time, and engine health.
3. **Layouts switched with one key**, like musikcube's library, settings and
   console views: Browse, Search, Stage, Arrangements, Settings.
4. **Drill-down columns** instead of a single tree, modelled on musikcube's
   category list → track list: *Pack/Folder → Tags → Samples*.
5. **Theme files** with named colour tokens. They ship in light and dark
   versions and users can override them.
6. **No change to muscle memory.** `\` leader, `j/k`, `/`, `Tab`, `Space`,
   `F1–F6` all keep their v1 meaning.

We keep **Textual** rather than porting to ncurses or C++. Once audio no longer
needs the GIL, UI cost no longer affects audio quality. Textual also gives us
TCSS theming, mouse support and the test harness that already exist.

### 6.2 Browse layout (default)

```
 Sample Manager · ~/Samples/Splice                               Browse  Search  Stage  Arr  ⚙
──────────────────────────────────────────────────────────────────────────────────────────────
 PACKS                  │ TAGS              │ SAMPLES  (drums/kicks · 214)        │ STAGE  (6)
 ▸ 808 Essentials       │   all          214│ ▸ kick_punchy_01.wav    0.42s  -6.1 │  kick_punchy_01
   Analog Drums         │ ▸ kick          96│   kick_punchy_02.wav    0.39s  -5.8 │  snare_crack_04
   Lo-Fi Textures       │   punchy        31│   kick_sub_long.wav     1.80s  -9.0 │  hat_closed_11
   Vocal Chops          │   sub           22│   kick_909_tuned_C.wav  0.55s  -7.2 │  perc_wood_02
   ...                  │   909           14│   kick_room_amb.wav     0.95s -12.4 │  fx_riser_8bar
                        │                   │   ...                                │  vox_chop_Am_3
                        │                   │                                      │
                        │                   │  key C · 0.42s · 48k/24 · stereo     │  ⏎ remove  a arrange
                        │                   │  tags: kick, punchy, 808             │
──────────────────────────────────────────────────────────────────────────────────────────────
 ▶ kick_punchy_01.wav  ⣀⣤⣶⣿⣿⣷⣦⣤⣄⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀│⠀⠀⠀⠀⠀⠀⠀  0:00.21 / 0:00.42   ▮▮▮▮▯ -6dB
 \ commands  / search  Tab pane  Space play  t tags  w scrub      engine native · 9 ms · 0 xrun
```

- **Columns** narrow the view from left to right. In each column `l`/`→`
  moves into the next column and `h`/`←` moves back, as v1's browser does
  today.
- The **sample row** shows duration and loudness, so likely candidates stand
  out before playback.
- The **inline detail** under the list replaces v1's separate top-display
  zone. The full-height metadata panel is still available with `i`.
- The **transport bar** draws a braille waveform across the full terminal
  width, since the bottom row is always free. Waveform scrub mode (`w`)
  takes place in this bar.
- The **engine status line** shows which engine is active, measured latency
  and xrun count. A slow or broken audio setup is visible immediately.

### 6.3 Other layouts

- **Search (`/`)**: a full-width result table ranked by match, with
  inline tag chips. Auditioning works the same as in Browse.
- **Stage**: a list with bulk actions: tag all, create arrangement, clear.
- **Arrangements**: the arrangement list, the folder layout preview from
  `arrangement preview`, and the export profile chosen in that view.
  Export and revert run from here with a confirmation dialog.
- **Settings**: audio device, engine (`auto/native/python`), buffer size,
  prefetch depth, cache size, level matching, theme.

### 6.4 Rendering cost guardrails

- Poll the engine at 30 Hz **only while playing**. Stop the timer when idle.
- Cache the waveform as rendered `Strip` segments per (sample, width).
  When the playhead moves, redraw only the bar's cells and leave the table
  alone.
- Throttle list refreshes during a scan (scan progress arrives as batched
  events).

---

## 7. Milestones

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Baseline** | `tools/bench_audition.py` (done). Add `t_cmd`/`t_out` timing to the v1 player and run on real hardware (macOS + Linux). | Recorded baseline p50/p95 on two machines. |
| **1. Python engine re-architecture (option A)** | Persistent stream, streaming reader, full cache for ≤ 10 s, focus prefetch, fades, async pause, vectorised envelope, single decode | p95 ≤ 40 ms warm; no clicks; existing tests green |
| **2. Peaks and analysis at scan time** | `sample_analysis` table and migration, peak pyramid, LUFS, lazy backfill | Waveform shows in under 5 ms after focus |
| **3. Native engine spike** | `sm_engine.h`, miniaudio + dr_libs, nanobind, null-backend tests, one-platform wheel | Meets §2 targets on one machine; ASan clean |
| **4. Native engine productised** | cibuildwheel matrix, fallback logic, `engine bench`, settings | Wheels for all 5 targets; automatic fallback verified |
| **5. TUI v2** | Neutral theme and tokens, transport bar, layout switcher, drill-down columns, inline detail | Snapshot tests for each layout; v1 keymap tests still pass |
| **6. Later** | Pitch/tempo-matched audition, MIDI trigger, shared engine daemon (option D) | — |

Phases 1–2 and 5 can run in parallel. Phase 3 depends only on the port
interface, which already exists.

---

## 8. Open questions

1. **C++ or Rust** for the engine? This design assumes C++ (as in musikcube,
   with miniaudio as the core). Rust is an equally good choice and its
   packaging is easier. Decide before phase 3.
2. **Device sample rate vs. file rate.** Always resample to the device rate
   (lower risk, small CPU cost), or reopen the stream when an audition needs
   bit-exact output?
3. **Compressed formats.** Is MP3 enough with dr_mp3, or do we still need
   ffmpeg for AAC/M4A? (Today: `audioread`.) This affects the size of the
   wheels.
4. **Qt GUI.** Should it get the same engine and the same transport-bar
   concept in v2, or stay in maintenance mode?
5. **Prefetch I/O on slow drives** (HDD/NAS libraries). Should prefetch depth
   adapt to the measured read time?
