"""Selected Files List widget — read-only scrollable selection (Zone 4, purple border)."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static


class SelectedFilesListWidget(VerticalScroll):
    """Scrollable read-only list of selected sample filenames."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "Selected Files (0)"

    def on_mount(self) -> None:
        self.mount(Static("  No samples selected · press 'a' to add", classes="sel-hint"))

    def update(self, items: list[dict]) -> None:
        self.border_title = f"Selected Files ({len(items)})"
        self.remove_children()
        if not items:
            self.mount(Static("  No samples selected · press 'a' to add", classes="sel-hint"))
        else:
            self.mount(*[
                Static(f"  {item.get('filename', '?')}", classes="sel-item")
                for item in items
            ])
