"""Persistent playback view independent of the focused browser metadata."""

import math
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from .waveform import WaveformWidget


class TransportBar(Widget):
    """Keep the sounding sample, time and engine health visible in every view."""

    DEFAULT_CSS = """
    TransportBar { height: 3; border-top: solid $panel-lighten-2; padding: 0 1; }
    TransportBar Static { height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    TransportBar WaveformWidget { height: 1; color: $accent; }
    """

    def compose(self) -> ComposeResult:
        """Mount stable children so progress never rebuilds sample tables."""
        yield Static("Transport · idle · engine Python", id="transport-state", markup=False)
        yield WaveformWidget(id="transport-waveform")

    def update_playback(self, playback, stats: dict) -> None:
        """Show measured fields only when available; never invent native metrics."""
        name = playback.path.name if playback.path else "No sample playing"
        duration = f" / {playback.duration_seconds:.2f}s" if playback.duration_seconds else ""
        health = str(stats.get("engine", "python"))
        if stats.get("output_latency_s") is not None:
            health += f" · device {stats['output_latency_s'] * 1000:.0f} ms"
        if "xruns" in stats:
            health += f" · {stats['xruns']} xrun"
        if "starved" in stats:
            health += f" · {stats['starved']} starved"
        if "peak" in stats:
            peak = stats["peak"]
            db = f"{20 * math.log10(peak):.0f}" if peak > 0 else "−∞"
            health += f" · {'▮' * min(8, round(peak * 8))} {db} dB"
        if stats.get("warning"):
            health += f" · {stats['warning']}"
        if playback.error:
            health += f" · {playback.error}"
        self.query_one(Static).update(
            f"{playback.status.value} · {name} · {playback.position_seconds:.2f}{duration} · {health}"
        )
        waveform = self.query_one(WaveformWidget)
        waveform.set_progress(
            playback.position_seconds / playback.duration_seconds
            if playback.duration_seconds and waveform.path == playback.path else 0
        )
