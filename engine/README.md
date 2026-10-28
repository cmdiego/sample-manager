# Optional audition engine

This workspace builds the separate `sample-manager-engine` package. The main
application remains installable and usable without Rust or this extension.
Python is the default engine; native is opt-in until device acceptance is recorded.

## Build and test

Install Rust 1.90.0 and Python 3.10 or newer, then from the repository root:

```sh
python -m pip install 'maturin>=1.9,<2'
cd engine
cargo fmt --all --check
cargo clippy --workspace --locked -- -D warnings
cargo test -p sm-engine --locked
maturin build --release --locked --out dist
python -m pip install dist/*.whl
```

Linux builds also need the ALSA development headers and pkg-config. Windows
uses the MSVC toolchain. `.github/workflows/native.yml` builds macOS arm64/x86_64,
Linux x86_64/aarch64 and Windows x86_64 wheels, and exercises the same abi3 wheel
with Python 3.10 and 3.14. The workflow uploads artifacts and does not publish.
The `[native]` extra names this distribution; until a release is published,
install a locally built/CI wheel before selecting native in Settings.

## Boundary and ownership

`sm-engine` is the Rust core. `sm-engine-py` binds it to
`sample_manager_engine._engine` using PyO3's `abi3-py310` ABI. Control, two
prioritized decoder workers, and a persistent CPAL output run outside the GIL.
The Python `AudioPlayer` keeps the existing play/pause/seek/resume API; its native
adapter translates seek/resume into generation-checked starts. Device changes
replace the engine and flush all device-rate caches.

Symphonia handles WAV/AIFF/FLAC/MP3. Other formats keep their existing Python
backend requirements and pass one device-rate stereo float32 PCM buffer through
the binding. The native callback never calls Python. Native device indexes are
matched to a unique PortAudio device name before use; ambiguous/missing matches
fail rather than silently selecting another device.

Each active source has a half-second SPSC frame ring. The byte-bounded head LRU
stores up to half a second per file and is keyed by path/size/nanosecond mtime.
Play and prefetch queues are bounded; a saturated play queue reports an error so
callers can retry. Prefetch has a separate generation and lower worker priority.
Only two voices mix, with 3 ms fades; retired ring/voice allocations return to
the control thread for reclamation. The normal render path is covered by an
allocation guard. Callback panics silence that buffer and mark engine failure.
The callback uses atomics and rtrb rather than a custom unsafe seqlock; snapshots
are eventually consistent UI observations, not a transaction across all fields.

The timer-driven NullBackend runs the same mixer for headless tests. Snapshot
peak/RMS and starvation counts are measured. CPAL stream errors are reported as
`device_errors`; they are not advertised as a portable hardware xrun count.
Timestamp diagnostics identify first non-silent buffer output. They are not
acoustic latency and a first benchmark pass is not guaranteed cold disk.

```sh
sampleman engine stats --engine native --backend null
sampleman engine bench /path/to/fixtures --engine native --backend null
sampleman engine bench /path/to/fixtures --engine python --backend device
```

## Release acceptance still required

The local development result validates the macOS ARM64 wheel and NullBackend.
CI execution on the other targets, real macOS/Linux device latency and listening
checks, device disconnect/recovery, slow storage, and Windows device behavior
remain acceptance work. No native default promotion or package publication is
performed by this implementation. Python remains the recovery setting.
