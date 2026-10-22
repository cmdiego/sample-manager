"""Integrated search strip showing query and result counts."""

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
        self.border_title = "Search"
        self._query = ""

    def compose(self) -> ComposeResult:
        yield Static("/ Search name, path, or tag", classes="filter-empty", id="filter-text")

    def update_filter(
        self, query: str, *, active: bool = False, count: int | None = None,
    ) -> None:
        """Show the actual query separately from the shortcut that opens it."""
        self._query = query
        self.set_class(active, "search-active")
        label = self.query_one("#filter-text", Static)
        if query:
            self.border_title = f"Search — {escape(query)}"
            matches = f" · {count}{'+' if count == 500 else ''} matches" if count is not None else ""
            label.update(
                f"  [bold]{escape(query)}[/bold]{matches}"
            )
            label.set_class(True, "filter-text")
            label.set_class(False, "filter-empty")
        elif active:
            self.border_title = "Search library"
            label.update("Type a name, path, or tag…")
            label.set_class(True, "filter-text")
            label.set_class(False, "filter-empty")
        else:
            self.border_title = "Search"
            label.update("/ Search name, path, or tag")
            label.set_class(False, "filter-text")
            label.set_class(True, "filter-empty")
