"""Sample list widget — renders the current NavState directory listing."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from ..nav_state import NavState, NavItem


class SampleListWidget(VerticalScroll):
    """Scrollable directory listing with focus highlight."""

    DEFAULT_CSS = ""  # all CSS lives in styles/app.tcss

    class CursorMoved(Message):
        """Fired when the focused item changes."""
        def __init__(self, item: NavItem) -> None:
            super().__init__()
            self.item = item

    class ItemActivated(Message):
        """Fired when the user activates (enters) the focused item."""
        def __init__(self, item: NavItem) -> None:
            super().__init__()
            self.item = item

    def __init__(self, state: NavState, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state = state
        self._prev_focused_index: int = -1
        self.border_title = str(state.current_dir)

    def compose(self) -> ComposeResult:
        yield Static("  (loading...)", id="tree-placeholder")

    def update(self, state: NavState) -> None:
        prev_index = self._prev_focused_index
        self._state = state
        self.border_title = str(state.current_dir)
        self.remove_children()

        if not state.items:
            self.mount(Static("  (empty directory)", id="tree-placeholder"))
            self._prev_focused_index = -1
            return

        rows = [
            Static(_format_item(item, focused=(i == state.focused_index)), classes="file-row")
            for i, item in enumerate(state.items)
        ]
        self.mount(*rows)
        self._scroll_to_focused()

        # Fire CursorMoved when the focused item changes
        if state.focused_index != prev_index and state.focused_item is not None:
            self.post_message(SampleListWidget.CursorMoved(state.focused_item))
        self._prev_focused_index = state.focused_index

    def _scroll_to_focused(self) -> None:
        idx = self._state.focused_index
        if idx < 0:
            return
        rows = list(self.query(".file-row"))
        if idx < len(rows):
            self.scroll_to_widget(rows[idx])


# Backward-compat alias
FileTreeWidget = SampleListWidget


def _format_item(item: NavItem, focused: bool = False) -> str:
    cursor = "▶" if focused else " "
    if item.is_dir:
        text = f"{cursor} {item.name}/"
        return f"[bold]{text}[/bold]" if focused else text

    check = "[green]✓[/green] " if item.is_selected else "  "
    indexed_tag = f" [dim]#{item.sample_id}[/dim]" if item.sample_id is not None else " [dim](not indexed)[/dim]"
    text = f"{cursor} {check}{item.name}{indexed_tag}"
    return f"[bold reverse]{text}[/bold reverse]" if focused else text
