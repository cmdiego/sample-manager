"""Browser pane with an integrated search strip and directory listing."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget

from ..nav_state import NavState
from .filters_panel import FiltersPanel
from .file_tree import SampleListWidget


class BrowserZone(Widget):
    """Single bordered pane containing search and the scrollable sample list."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, state: NavState, **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_state = state
        self.border_title = "Browser"

    def compose(self) -> ComposeResult:
        yield FiltersPanel(id="filters-panel")
        yield SampleListWidget(self._initial_state, id="sample-list")

    @property
    def filters_panel(self) -> FiltersPanel:
        return self.query_one("#filters-panel", FiltersPanel)

    @property
    def sample_list(self) -> SampleListWidget:
        return self.query_one("#sample-list", SampleListWidget)
