"""Preview zone — metadata + pixel waveform for the focused sample.

Shows filename, format, size, tags, and sample id (Phase 2), and below the
metadata a :class:`WaveformWidget` that paints the focused file's waveform,
playhead, and played region (Phase 4).

Presentation-only: it reads a ``SampleDetails`` DTO handed to it and forwards a
resolved path + playback snapshots to the waveform widget; it never touches the
DB.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...services.library_browser import SampleDetails
from .waveform import WaveformWidget

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...audio.player import AudioPlayer, PlaybackSnapshot
    from ...audio.waveform import WaveformService


def _human_size(num: int | None) -> str:
    if not num:
        return "—"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


class PreviewWidget(QWidget):
    """Displays metadata for the focused sample (waveform lands in Phase 4)."""

    def __init__(self, waveform_service: "WaveformService | None" = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PreviewWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        self._title = QLabel("No sample selected")
        self._title.setObjectName("PreviewTitle")
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._format = QLabel("")
        self._size = QLabel("")
        self._tags = QLabel("")
        self._tags.setWordWrap(True)
        self._sample_id = QLabel("")
        for lbl in (self._format, self._size, self._tags, self._sample_id):
            lbl.setObjectName("PreviewMeta")
            layout.addWidget(lbl)

        # The pixel waveform takes the remaining vertical space.
        self._waveform = WaveformWidget(service=waveform_service)
        layout.addWidget(self._waveform, stretch=1)

        self.clear()

    # -- audio wiring ---------------------------------------------------------

    @property
    def waveform(self) -> WaveformWidget:
        return self._waveform

    def connect_player(self, player: "AudioPlayer") -> None:
        """Wire waveform click-to-seek into *player*."""
        self._waveform.seek_requested.connect(
            lambda frac: player.seek(
                frac * (player.snapshot().duration_seconds or 0.0)
            )
        )

    def set_waveform_service(self, service: "WaveformService | None") -> None:
        self._waveform.set_service(service)

    def set_focus_path(self, path: Path | None) -> None:
        """Point the waveform at *path* (or clear it when ``None``)."""
        self._waveform.set_path(path)

    def on_playback_changed(self, snapshot: "PlaybackSnapshot | None") -> None:
        self._waveform.set_playback(snapshot)

    # -- public API -----------------------------------------------------------

    def show_details(self, details: SampleDetails | None) -> None:
        """Render *details*, or the empty state when ``None``."""
        if details is None:
            self.clear()
            return

        self._title.setText(details.filename)

        # SampleDetails exposes ``ext`` and ``size_bytes``; accept ``format`` /
        # ``file_size`` / ``tags`` too so richer DTOs render without changes.
        fmt = getattr(details, "format", None) or details.ext or "—"
        self._format.setText(f"Format: {fmt}")

        size = getattr(details, "file_size", None)
        if size is None:
            size = details.size_bytes
        self._size.setText(f"Size: {_human_size(size)}")

        tags = getattr(details, "tags", None)
        if tags:
            joined = ", ".join(str(t) for t in tags) if not isinstance(tags, str) else tags
            self._tags.setText(f"Tags: {joined}")
            self._tags.show()
        else:
            self._tags.hide()

        self._sample_id.setText(f"Sample ID: {details.id}")

    def clear(self) -> None:
        self._title.setText("No sample selected")
        self._format.setText("")
        self._size.setText("")
        self._tags.setText("")
        self._tags.hide()
        self._sample_id.setText("")
        self._waveform.set_path(None)
