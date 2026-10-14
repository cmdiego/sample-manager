"""Selected Files List widget — scrollable Stage with a visible active cursor."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.markup import escape


class SelectedFilesListWidget(VerticalScroll):
    """Render selected filenames and show which one keyboard actions target."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, **kwargs) -> None:
        """Create an empty Stage whose cursor is set by the TUI app."""
        super().__init__(**kwargs)
        self.border_title = "Selected Files (0)"

    def on_mount(self) -> None:
        """Show a hint before the first app refresh."""
        self.mount(Static("  No samples selected · Tab to Browser, then a to add", classes="sel-hint"))

    def update(
        self, items: list[dict], *, focused_index: int = -1, active: bool = False
    ) -> None:
        """Replace Stage rows while keeping the active target unambiguous."""
        self.border_title = f"{'▶ ' if active else ''}Selected Files ({len(items)})"
        self.set_class(active, "active-pane")
        self.remove_children()
        if not items:
            self.mount(Static("  No samples selected · Tab to Browser, then a to add", classes="sel-hint"))
        else:
            self.mount(*[
                Static(
                    f"{'▶' if active and index == focused_index else ' '}  "
                    f"{escape(str(item.get('filename', '?')))}",
                    classes="sel-item",
                )
                for index, item in enumerate(items)
            ])
