"""Engine health and reproducible first-non-silent-buffer diagnostics."""

import json
import math
import time
from pathlib import Path
import typer
from ..audio.factory import build_player
from ..audio.decode import SOUNDFILE_EXTS, AUDIOREAD_EXTS
from ..audio.player import PlaybackStatus


def register(app):
    """Keep diagnostics independent of the library database and GUI imports."""
    engine_app = typer.Typer(help="Audio engine diagnostics (buffer timing, not acoustic latency)")
    app.add_typer(engine_app, name="engine")

    def create(engine, backend, buffer_frames):
        """Reject unsupported options before touching audio hardware."""
        if engine not in ("python", "native", "auto") or backend not in ("device", "null"):
            raise typer.BadParameter("engine must be python/native/auto; backend device/null")
        if buffer_frames not in (128, 256, 512, 1024, 2048):
            raise typer.BadParameter("buffer frames must be 128/256/512/1024/2048")
        return build_player(engine=engine, backend=backend, buffer_frames=buffer_frames)

    @engine_app.command("stats")
    def stats(engine: str = "python", backend: str = "null", buffer_frames: int = 1024):
        """Inspect a fresh diagnostics instance; does not attach to a running UI."""
        player = None
        try:
            player = create(engine, backend, buffer_frames)
            typer.echo(json.dumps({"backend": backend, "requested_engine": engine,
                                   "buffer_frames": buffer_frames, **player.engine_stats()}, indent=2))
        except Exception as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        finally:
            if player is not None:
                player.close()

    @engine_app.command("bench")
    def bench(folder: Path, engine: str = "python", backend: str = "null",
              buffer_frames: int = 256, max_files: int = 20, passes: int = 2):
        """Audition a fixed sorted corpus; the first pass is not guaranteed cold disk."""
        if not folder.is_dir() or not 1 <= max_files <= 1000 or not 1 <= passes <= 10:
            raise typer.BadParameter("Choose a folder, 1–1000 files and 1–10 passes")
        files = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in SOUNDFILE_EXTS | AUDIOREAD_EXTS)[:max_files]
        if not files:
            raise typer.BadParameter("No supported samples found")
        player = None
        try:
            player = create(engine, backend, buffer_frames)
            results = []
            for run in range(passes):
                for path in files:
                    requested = time.perf_counter()
                    player.play_from_start(path)
                    result = {"path": str(path), "pass": run + 1}
                    while time.perf_counter() - requested < 10:
                        snapshot = player.snapshot()
                        stats = player.engine_stats()
                        first = stats.get("last_first_render_at")
                        if first is not None and first >= requested:
                            result["input_to_first_non_silent_buffer_ms"] = (first - requested) * 1000
                            break
                        if snapshot.status is PlaybackStatus.ERROR:
                            result["error"] = snapshot.error
                            break
                        if snapshot.status is PlaybackStatus.IDLE:
                            result["error"] = "No non-silent frame (silent/empty file)"
                            break
                        time.sleep(0.001)
                    else:
                        result["error"] = "No non-silent output within 10 seconds"
                    results.append(result)
                    player.pause()
            values = sorted(r["input_to_first_non_silent_buffer_ms"] for r in results if "input_to_first_non_silent_buffer_ms" in r)
            summary = {f"p{p}_ms": values[min(len(values)-1, math.ceil(len(values)*p/100)-1)]
                       for p in (50,95,99)} if values else {}
            typer.echo(json.dumps({"measurement": "input to first non-silent device buffer; not acoustic latency",
                "cache_note": "First pass may have warm OS cache; later passes reuse engine caches",
                "backend": backend, "buffer_frames": buffer_frames, "summary": summary,
                "stats": player.engine_stats(), "results": results}, indent=2))
        except Exception as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        finally:
            if player is not None:
                player.close()
