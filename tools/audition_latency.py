"""Measure real audition latency of the TUI playback path on this machine.

Usage:
    python tools/audition_latency.py FOLDER [--device N] [--count 40]
                                            [--latency 0.025] [--gap 0.25]

Plays up to ``--count`` audio files from FOLDER through the same player, decode
cache, and persistent output stream the TUI uses, then reports how long each
audition took from ``play()`` to its first audible buffer (plus the device's
reported output latency). After one warm-up audition, which also opens the
persistent stream and is reported separately, two passes run over the rest:

* ``cold``: every file is decoded on demand, the first time it is heard.
* ``cached``: every file is already in the decode cache, which is what the
  TUI's neighbour prefetch achieves while you move through a folder.

This needs a real output device, so run it on your own machine. Turn the
volume down: it plays short excerpts of each file.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sample_manager.audio.decode import AUDIOREAD_EXTS, SOUNDFILE_EXTS  # noqa: E402
from sample_manager.audio.decode_cache import DecodeCache  # noqa: E402
from sample_manager.audio.player import AudioPlayer, PlaybackStatus  # noqa: E402
from sample_manager.audio.stream_output import StreamingSoundDeviceOutput  # noqa: E402

_EXTENSIONS = SOUNDFILE_EXTS | AUDIOREAD_EXTS


def _files(folder: Path, count: int) -> list[Path]:
    found = sorted(
        path for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in _EXTENSIONS
    )
    return found[:count]


def _audition(player: AudioPlayer, path: Path, timeout: float = 3.0) -> float | None:
    """Return seconds from play() to the first rendered buffer, or None."""
    started = time.perf_counter()
    player.play_from_start(path)
    deadline = started + timeout
    while time.perf_counter() < deadline:
        stats = player.engine_stats()
        first = stats.get("last_first_render_at")
        if first is not None and first >= started:
            return first - started
        if player.snapshot().status is PlaybackStatus.ERROR:
            return None
        time.sleep(0.0005)
    return None


def _run_pass(player: AudioPlayer, files: list[Path], *, gap: float) -> list[float]:
    results = []
    for path in files:
        latency = _audition(player, path)
        if latency is None:
            print(f"  failed: {path.name} ({player.snapshot().error or 'timeout'})")
        else:
            results.append(latency)
        time.sleep(gap)
    return results


def _report(label: str, values: list[float], output_latency: float) -> None:
    if not values:
        print(f"{label:11} no successful auditions")
        return
    ms = sorted((value + output_latency) * 1000 for value in values)
    p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
    print(
        f"{label:11} n={len(ms):3}  p50 {statistics.median(ms):6.1f} ms  "
        f"p95 {p95:6.1f} ms  max {ms[-1]:6.1f} ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--device", type=int, default=None, help="sounddevice output index")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--latency", type=float, default=0.025, help="requested output buffering (s)")
    parser.add_argument("--gap", type=float, default=0.25, help="seconds each file plays")
    args = parser.parse_args()

    files = _files(args.folder.expanduser(), args.count)
    if not files:
        sys.exit(f"No audio files found under {args.folder}")

    output = StreamingSoundDeviceOutput(device=args.device, latency=args.latency)
    # The cold pass fills the cache; the cached pass then measures cache hits,
    # the state neighbour prefetch keeps the TUI in.
    cache = DecodeCache()
    player = AudioPlayer(decoder=cache, output=output)
    try:
        warmup = _audition(player, files[0])
        time.sleep(args.gap)
        cold = _run_pass(player, files[1:], gap=args.gap)
        cached = _run_pass(player, files[1:], gap=args.gap)
        player.pause()
        time.sleep(0.05)
        stats = output.stats()
    finally:
        cache.close()
        player.close()

    output_latency = stats.get("output_latency_s") or 0.0
    print(
        f"\ndevice rate {stats.get('device_rate')} Hz · channels {stats.get('channels')} · "
        f"output latency {output_latency * 1000:.1f} ms · xruns {stats.get('xruns')}"
    )
    if warmup is not None:
        print(f"first audition incl. stream open: {(warmup + output_latency) * 1000:.1f} ms")
    print("play() -> first audible buffer, including output latency:")
    _report("cold", cold, output_latency)
    _report("cached", cached, output_latency)


if __name__ == "__main__":
    main()
