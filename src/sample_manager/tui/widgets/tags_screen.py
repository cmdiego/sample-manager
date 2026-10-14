"""Manage the focused sample's tags with explicit, immediately applied actions."""

from __future__ import annotations

from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option


class TagsScreen(ModalScreen):
    """Attach/detach tags for the sample captured when this screen opened."""

    BINDINGS = [("escape", "close", "Close")]
    DEFAULT_CSS = """
    TagsScreen { align: center middle; }
    #sample-tags-dialog {
        width: 72; max-width: 95%; height: 22; max-height: 95%;
        border: round $accent; background: $surface; padding: 0 2;
    }
    #sample-tags-title { height: 2; text-style: bold; }
    #sample-tags-note { height: 2; color: $text-muted; }
    #sample-tag-entry { height: 3; }
    #sample-tag-entry Input { width: 1fr; }
    #sample-tag-entry Button { width: 10; min-width: 10; margin-left: 1; }
    #sample-tags-list { height: 1fr; min-height: 3; }
    #sample-tags-empty { height: 1; color: $text-muted; }
    #sample-tags-status { height: 2; }
    #sample-tags-actions { height: 3; align-horizontal: right; }
    #sample-tags-actions Button { margin-left: 1; }
    """

    def __init__(
        self, filename: str, tags: list[dict], *,
        on_add: Callable[[str], list[dict]],
        on_remove: Callable[[str], list[dict]],
    ) -> None:
        super().__init__()
        self._filename = filename
        self._tags = tags
        self._on_add = on_add
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        """Keep tag entry, current attachments, and explicit actions visible."""
        with Vertical(id="sample-tags-dialog"):
            yield Static(f"Tags — {self._filename}", id="sample-tags-title", markup=False)
            yield Static("Changes apply immediately. Removing a tag affects only this sample.", id="sample-tags-note")
            with Horizontal(id="sample-tag-entry"):
                yield Input(placeholder="Tag name or existing alias", id="sample-tag-input")
                yield Button("Add", id="sample-tag-add", variant="primary")
            yield OptionList(*self._options(), id="sample-tags-list")
            yield Static("No tags yet", id="sample-tags-empty")
            yield Static("", id="sample-tags-status", markup=False)
            with Horizontal(id="sample-tags-actions"):
                yield Button("Remove selected", id="sample-tag-remove", variant="warning")
                yield Button("Close", id="sample-tags-close")

    def _options(self) -> list[Option]:
        """Render user-supplied names literally, including brackets and commas."""
        return [Option(Text(tag["name_display"]), id=str(tag["id"])) for tag in self._tags]

    def on_mount(self) -> None:
        """Focus tag entry and distinguish an empty list from a failed load."""
        self._update_controls()
        self.query_one(Input).focus()

    def _update_controls(self) -> None:
        """Enable removal only when at least one current tag can be selected."""
        self.query_one("#sample-tags-empty", Static).display = not self._tags
        self.query_one("#sample-tag-remove", Button).disabled = not self._tags

    def action_close(self) -> None:
        """Close the editor; completed actions have already been persisted."""
        self.dismiss()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Treat Enter in tag entry as Add, without reaching the browser."""
        event.stop()
        self._add()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Apply only the explicitly selected tag action."""
        event.stop()
        if event.button.id == "sample-tag-add":
            self._add()
        elif event.button.id == "sample-tag-remove":
            self._remove()
        elif event.button.id == "sample-tags-close":
            self.action_close()

    def _apply(self, action: Callable[[], list[dict]], message: str) -> bool:
        """Reload committed attachments, keeping errors and edits in the modal."""
        try:
            tags = action()
        except Exception as exc:  # noqa: BLE001 - validation/storage errors remain visible
            self.query_one("#sample-tags-status", Static).update(str(exc))
            return False
        self._tags = tags
        options = self.query_one(OptionList)
        options.clear_options().add_options(self._options())
        if self._tags:
            options.highlighted = 0
        self._update_controls()
        self.query_one("#sample-tags-status", Static).update(message)
        return True

    def _add(self) -> None:
        """Resolve a typed name or alias through the existing tagging service."""
        field = self.query_one(Input)
        text = field.value
        if self._apply(lambda: self._on_add(text), "Tag added"):
            field.value = ""
            field.focus()

    def _remove(self) -> None:
        """Detach the highlighted tag, leaving tags on other samples intact."""
        index = self.query_one(OptionList).highlighted
        if index is None or not 0 <= index < len(self._tags):
            return
        name = self._tags[index]["name_display"]
        self._apply(lambda: self._on_remove(name), f"Removed {name} from this sample")
