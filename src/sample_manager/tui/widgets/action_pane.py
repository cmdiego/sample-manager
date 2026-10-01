"""Action pane — modal screen shown when 'l'/right is pressed on a file."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static, Button
from textual.containers import Vertical

from ..nav_state import NavItem


class ActionPane(ModalScreen):
    """Modal overlay with actions for the focused file."""

    DEFAULT_CSS = """
    ActionPane {
        align: center middle;
    }
    ActionPane Vertical {
        width: 44;
        height: auto;
        border: double $accent;
        padding: 1 2;
        background: $surface;
    }
    ActionPane .action-title {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    ActionPane .action-meta {
        color: $text-muted;
        margin-bottom: 1;
    }
    ActionPane .action-hint {
        color: $text-muted;
        margin-top: 1;
    }
    ActionPane Button {
        width: 1fr;
        margin-bottom: 0;
    }
    """

    def __init__(self, item: NavItem, is_selected: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self._item = item
        self._is_selected = is_selected

    def compose(self) -> ComposeResult:
        item = self._item
        meta = f"sample_id={item.sample_id}" if item.sample_id else "not indexed"
        with Vertical():
            yield Static(item.name, classes="action-title")
            yield Static(meta, classes="action-meta")
            if item.sample_id is not None:
                if self._is_selected:
                    yield Button("Remove from selection  [d]", id="remove", variant="warning")
                else:
                    yield Button("Add to selection  [a]", id="add", variant="success")
            else:
                yield Static("(not indexed — run `sample scan` first)", classes="action-meta")
            yield Static("ESC to close", classes="action-hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def on_key(self, event) -> None:
        if event.key == "escape" or event.key == "q":
            self.dismiss(None)
        elif event.key == "a" and self._item.sample_id is not None and not self._is_selected:
            self.dismiss("add")
        elif event.key == "d" and self._item.sample_id is not None and self._is_selected:
            self.dismiss("remove")
