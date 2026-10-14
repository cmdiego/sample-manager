"""Session Summary widget — aggregate stats for current session (Zone 2, blue border)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


def _fmt_size(n: int) -> str:
    val = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if val < 1024:
            return f"{val:.0f} {unit}"
        val /= 1024
    return f"{val:.1f} TB"


class SessionSummaryWidget(Widget):
    """Shows selection count, total size, and target destination."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Session"

    def compose(self) -> ComposeResult:
        yield Static("  [dim]Selected:[/dim]  0 samples", classes="summary-row", id="sum-count")
        yield Static("  [dim]Size:[/dim]     —", classes="summary-row", id="sum-size")
        yield Static("  [dim]Dest:[/dim]     (no profile set)", classes="summary-row", id="sum-dest")

    def update(self, count: int, total_bytes: int, destination: str | None) -> None:
        self.query_one("#sum-count", Static).update(
            f"  [dim]Selected:[/dim]  {count} sample{'s' if count != 1 else ''}"
        )
        self.query_one("#sum-size", Static).update(
            f"  [dim]Size:[/dim]     {_fmt_size(total_bytes) if total_bytes else '—'}"
        )
        dest_text = destination or "(no profile set)"
        self.query_one("#sum-dest", Static).update(
            f"  [dim]Dest:[/dim]     {dest_text}"
        )
