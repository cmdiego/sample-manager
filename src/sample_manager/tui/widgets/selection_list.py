"""Selected Files List widget — scrollable Stage with a visible active cursor."""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.markup import escape

from .session_summary import _fmt_size


class SelectedFilesListWidget(VerticalScroll):
    """Render selected filenames and show which one keyboard actions target."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    def __init__(self, **kwargs) -> None:
        """Create an empty Stage whose cursor is set by the TUI app."""
        super().__init__(**kwargs)
        self.border_title = "Stage · 0 · 0 B"

    def on_mount(self) -> None:
        """Show a hint before the first app refresh."""
        self.mount(Static("No samples selected\nn New folder · Tab to Browser to add", classes="sel-hint"))

    def update(
        self, items: list[dict], *, focused_index: int = -1, active: bool = False,
        total_bytes: int = 0, destination: str | None = None,
        sample_count: int | None = None, folder_path: str = "",
    ) -> None:
        """Replace Stage rows while keeping the active target unambiguous."""
        count = len(items) if sample_count is None else sample_count
        self.border_title = f"Stage · {count} · {_fmt_size(total_bytes)}"
        self.border_subtitle = escape(folder_path or destination or "")
        self.set_class(active, "active-pane")
        self.remove_children()
        if not items:
            self.mount(Static("No samples selected\nn New folder · Tab to Browser to add", classes="sel-hint"))
        else:
            self.mount(*[
                Static(
                    f"{'▶' if active and index == focused_index else ' '}  "
                    f"{escape(str(item.get('filename', '?')))}{'/' if item.get('is_dir') else ''}",
                    classes="sel-item" + (" cursor-row" if active and index == focused_index else ""),
                )
                for index, item in enumerate(items)
            ])

            if all(item.get("is_parent") for item in items):
                self.mount(Static("Empty folder · Tab to Browser to add", classes="sel-hint"))

            # Wait for replacement rows to mount before following the Stage
            # cursor; otherwise navigation past the viewport can go invisible.
            self.call_after_refresh(self._scroll_to_cursor)

    def _scroll_to_cursor(self) -> None:
        """Keep the active Stage target visible after asynchronous row mounts."""
        rows = self.query(".cursor-row")
        if rows:
            self.scroll_to_widget(rows.first(), animate=False, immediate=True)
