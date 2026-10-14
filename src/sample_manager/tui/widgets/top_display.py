"""Top Display widget — shows focused sample metadata (Zone 1, white border)."""

from __future__ import annotations

from pathlib import Path
from rich.markup import escape

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Static

from ...audio.waveform import WaveformData
from ..nav_state import NavItem
from .waveform import WaveformWidget


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

    def compose(self) -> ComposeResult:
        yield Static("  [ no sample focused ]", classes="meta-row")

    def update_focus(self, item: NavItem | None, details: dict | None) -> None:
        self.remove_children()
        if item is None:
            self.border_title = "Preview"
            self.mount(Static("  [ no sample focused ]", classes="meta-row"))
            return

        if item.is_dir:
            self.border_title = f"Directory — {escape(item.name)}"
            self.mount(Static(f"  {item.name}/", classes="meta-row", markup=False))
            return

        # File — show what we have from the DB
        self.border_title = f"Preview — {escape(item.name)}"
        rows: list[Widget] = [
            WaveformWidget(item.path, classes="waveform-display"),
        ]

        if details:
            name = details.get("filename", item.name)
            ext = details.get("ext") or ""
            size = _fmt_size(details.get("size_bytes"))
            tags = details.get("tags") or []

            rows.append(Static(f"  [dim]Name:[/dim]  {escape(str(name))}", classes="meta-row"))
            if ext:
                rows.append(Static(f"  [dim]Type:[/dim]  {ext.upper()}", classes="meta-row"))
            rows.append(Static(f"  [dim]Size:[/dim]  {size}", classes="meta-row"))
            if tags:
                tag_str = "  ".join(escape(str(t)) for t in tags)
                rows.append(Static(f"  [dim]Tags:[/dim]  {tag_str}", classes="meta-row"))
            if item.sample_id is not None:
                rows.append(Static(f"  [dim]ID:[/dim]   #{item.sample_id}", classes="meta-row"))
        else:
            rows.append(Static(f"  {item.name}", classes="meta-row", markup=False))
            rows.append(Static("  [dim](not indexed)[/dim]", classes="meta-row"))

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
        try:
            return self.query(WaveformWidget).first()
        except NoMatches:
            return None
