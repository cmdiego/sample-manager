"""Filters Panel widget — shows active filter/search state (Zone 3a, red border)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from rich.markup import escape


class FiltersPanel(Widget):
    """Thin strip showing the active typeahead filter query."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Filter"
        self._query = ""

    def compose(self) -> ComposeResult:
        yield Static("  (no filter active)", classes="filter-empty", id="filter-text")

    def update_filter(
        self, query: str, *, active: bool = False, count: int | None = None,
    ) -> None:
        """Show the actual query separately from the shortcut that opens it."""
        self._query = query
        label = self.query_one("#filter-text", Static)
        if query:
            self.border_title = f"Search — {escape(query)}"
            matches = f" · {count}{'+' if count == 500 else ''} matches" if count is not None else ""
            label.update(
                f"  [bold yellow]{escape(query)}[/bold yellow]{matches} · ↑/↓ results · Esc clear"
            )
            label.set_class(True, "filter-text")
            label.set_class(False, "filter-empty")
        elif active:
            self.border_title = "Search library"
            label.update("  Type a name, path, or tag · Shift+Space for space · Esc cancel")
            label.set_class(True, "filter-text")
            label.set_class(False, "filter-empty")
        else:
            self.border_title = "Filter"
            label.update("  (no filter active)")
            label.set_class(False, "filter-text")
            label.set_class(True, "filter-empty")
