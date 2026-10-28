"""Explicit, inert-by-default confirmation for persistent/destructive actions."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmScreen(ModalScreen[bool]):
    """A reviewable action summary; Escape and Cancel never invoke the action."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    #confirm-dialog { width: 68; max-width: 95%; height: auto; max-height: 90%;
                      border: round $accent; background: $surface; padding: 1 2; }
    #confirm-dialog Static { height: auto; max-height: 12; overflow-y: auto; }
    #confirm-dialog Horizontal { height: 3; align-horizontal: right; }
    """

    def __init__(self, summary: str, label="Confirm"):
        super().__init__()
        self.summary, self.label = summary, label

    def compose(self) -> ComposeResult:
        """Keep confirmation labels literal even for user-controlled paths."""
        with Vertical(id="confirm-dialog"):
            yield Static(self.summary, markup=False)
            with Horizontal():
                yield Button("Cancel", id="confirm-cancel")
                yield Button(self.label, id="confirm-accept", variant="warning")

    def action_cancel(self):
        """Discard the proposed action."""
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed):
        """Only the explicit confirmation button returns True."""
        event.stop()
        self.dismiss(event.button.id == "confirm-accept")
