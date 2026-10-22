"""Validated, cancel-safe Stage folder and placement editor."""

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class StagePathScreen(ModalScreen[bool]):
    """Apply a captured Stage action only after explicit form submission."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    StagePathScreen { align: center middle; }
    #stage-path-dialog {
        width: 68; max-width: 95%; height: auto; max-height: 95%;
        border: round $accent; background: $surface; padding: 0 2;
    }
    #stage-path-title { height: auto; text-style: bold; color: $accent; }
    #stage-path-note { height: auto; color: $text-muted; }
    #stage-path-error { height: auto; color: $error; }
    #stage-path-actions { height: 3; align-horizontal: right; }
    #stage-path-actions Button { margin-left: 1; }
    """

    def __init__(self, title: str, note: str, on_apply: Callable[[str], None], value: str = "") -> None:
        """Capture source IDs/parent context in the callback before edits begin."""
        super().__init__()
        self._title, self._note, self._on_apply, self._value = title, note, on_apply, value

    def compose(self) -> ComposeResult:
        """Expose the virtual destination and keep validation errors in the form."""
        with Vertical(id="stage-path-dialog"):
            yield Static(self._title, id="stage-path-title", markup=False)
            yield Static(self._note, id="stage-path-note", markup=False)
            yield Input(value=self._value, placeholder="Drums/Kicks", id="stage-path-input")
            yield Static("", id="stage-path-error", markup=False)
            with Horizontal(id="stage-path-actions"):
                yield Button("Apply", variant="primary", id="stage-path-apply")
                yield Button("Cancel", id="stage-path-cancel")

    def on_mount(self) -> None:
        """Focus text entry so folder paths never become global app shortcuts."""
        self.query_one(Input).focus()

    def action_cancel(self) -> None:
        """Cancel leaves Stage, selection and cursor unchanged."""
        self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Treat Enter as an explicit attempt to apply the captured operation."""
        event.stop()
        self._apply()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Share application/cancellation semantics between keys and buttons."""
        event.stop()
        self._apply() if event.button.id == "stage-path-apply" else self.action_cancel()

    def _apply(self) -> None:
        """Keep failed operations editable; successful callbacks commit atomically."""
        try:
            self._on_apply(self.query_one(Input).value)
        except Exception as exc:  # noqa: BLE001 - keep storage/validation errors reviewable
            self.query_one("#stage-path-error", Static).update(str(exc))
            return
        self.dismiss(True)
