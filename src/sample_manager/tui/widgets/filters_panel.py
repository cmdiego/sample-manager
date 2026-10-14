"""Filters Panel widget — shows active filter/search state (Zone 3a, red border)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class FiltersPanel(Widget):
    """Thin strip showing the active typeahead filter query."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Filter"
        self._query = ""

    def compose(self) -> ComposeResult:
        yield Static("  (no filter active)", classes="filter-empty", id="filter-text")

    def update_filter(self, query: str) -> None:
        self._query = query
        label = self.query_one("#filter-text", Static)
        if query:
            self.border_title = f"Filter — /{query}"
            label.update(f"  [bold yellow]/{query}[/bold yellow]  (type to narrow · backspace · esc to clear)")
            label.set_class(True, "filter-text")
            label.set_class(False, "filter-empty")
        else:
            self.border_title = "Filter"
            label.update("  (no filter active)")
            label.set_class(False, "filter-text")
            label.set_class(True, "filter-empty")
