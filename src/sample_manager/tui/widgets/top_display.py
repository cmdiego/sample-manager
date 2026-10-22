"""Compact shared preview for the focused Browser or Stage sample."""

from __future__ import annotations

from pathlib import Path
from rich.markup import escape

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from ...audio.waveform import WaveformData
from ..nav_state import NavItem
from .waveform import WaveformWidget
from .metadata_panel import MetadataPanel


def _fmt_size(n: int | None) -> str:
    if n is None:
        return "?"
    val = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if val < 1024:
            return f"{val:.0f} {unit}"
        val /= 1024
    return f"{val:.1f} TB"


class TopDisplayWidget(Widget):
    """Context panel: shows metadata for the focused sample or directory summary."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Preview"
        # Keep the current target synchronously: Textual removes/mounts children
        # asynchronously, so a query can still find the outgoing waveform.
        self._waveform: WaveformWidget | None = None
        self.metadata_panel = MetadataPanel(classes="embedded-panel")

    def compose(self) -> ComposeResult:
        yield self.metadata_panel
        yield Static("  [ no sample focused ]", classes="meta-row")

    def update_focus(self, item: NavItem | None, details: dict | None) -> None:
        """Refresh metadata while retaining waveform state for the same sample."""
        path = item.path if item is not None and not item.is_dir else None
        self.metadata_panel.set_target(path)
        self.metadata_panel.set_library_tags((details or {}).get("tags") or [])
        reuse_waveform = (
            path is not None and self._waveform is not None and self._waveform.path == path
        )
        if reuse_waveform:
            # Selection/tags do not change the audio: keep data, loading/error
            # state, playback progress and the seek cursor on the existing view.
            self.remove_children(".meta-row")
        else:
            self.remove_children(".meta-row, WaveformWidget")
            self._waveform = None
        if item is None:
            self.border_title = "Preview"
            self.mount(Static("  [ no sample focused ]", classes="meta-row"))
            return

        if item.is_dir:
            self.border_title = f"Directory — {escape(item.name)}"
            self.mount(
                Static(f"  {item.name}/", classes="meta-row", markup=False),
                Static("  i Inspect contents and subfolders", classes="meta-row", markup=False),
            )
            return

        # File — show what we have from the DB
        self.border_title = f"Preview — {escape(item.name)}"
        rows: list[Widget] = []
        if not reuse_waveform:
            self._waveform = WaveformWidget(item.path, classes="waveform-display")
            rows.append(self._waveform)

        if details:
            ext = str(details.get("ext") or "audio").upper()
            size = _fmt_size(details.get("size_bytes"))
            # Keep technical details beneath the waveform; assigned tags live
            # in the musical summary so they are not repeated in both panes.
            identity = f" · #{item.sample_id}" if item.sample_id is not None else ""
            rows.append(Static(
                f"{escape(ext)} · {size}{identity}", classes="meta-row"
            ))
        else:
            rows.append(Static("Not indexed · F5 to rescan library", classes="meta-row"))

        self.mount(*rows)

    def set_waveform_loading(self, path: Path) -> None:
        waveform = self._waveform_widget()
        if waveform is not None:
            waveform.set_loading(path)

    def set_waveform_data(self, data: WaveformData) -> None:
        waveform = self._waveform_widget()
        if waveform is not None and waveform.path == data.path:
            waveform.set_data(data)

    def set_waveform_error(self, path: Path, message: str) -> None:
        waveform = self._waveform_widget()
        if waveform is not None and waveform.path == path:
            waveform.set_error(path, message)

    def set_playback_progress(self, path: Path | None, progress: float) -> None:
        waveform = self._waveform_widget()
        if waveform is not None:
            waveform.set_progress(progress if waveform.path == path else 0.0)

    def set_nav_cursor(self, fraction: float | None) -> None:
        waveform = self._waveform_widget()
        if waveform is not None:
            waveform.set_nav_cursor(fraction)

    def _waveform_widget(self) -> WaveformWidget | None:
        """Return the current target even while its mount is still pending."""
        return self._waveform
