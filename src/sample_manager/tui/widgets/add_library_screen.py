"""Terminal library-folder entry with validation before any persistent changes."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from ...config import normalize_path


class AddLibraryScreen(ModalScreen):
    """Return a validated folder path, or None when the user cancels."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    AddLibraryScreen { align: center middle; }
    #add-library-dialog {
        width: 72; max-width: 95%; height: auto; max-height: 95%;
        border: round $accent; background: $surface; padding: 1 2;
    }
    #add-library-title { text-style: bold; margin-bottom: 1; }
    #add-library-error { height: auto; color: $error; }
    #add-library-actions { height: 3; align-horizontal: right; margin-top: 1; }
    #add-library-actions Button { margin-left: 1; }
    """

    def compose(self) -> ComposeResult:
        """Make folder entry usable by keyboard, paste, or button activation."""
        with Vertical(id="add-library-dialog"):
            yield Static("Add Sample Folder", id="add-library-title")
            yield Static("Type or paste a folder path. Samples stay in their original location.")
            yield Input(placeholder="~/Music/Samples", id="add-library-path")
            yield Static("", id="add-library-error", markup=False)
            with Horizontal(id="add-library-actions"):
                yield Button("Add & Scan", id="add-library-submit", variant="primary")
                yield Button("Cancel", id="add-library-cancel")

    def on_mount(self) -> None:
        """Focus the empty input without preselecting an expensive scan target."""
        self.query_one(Input).focus()

    def action_cancel(self) -> None:
        """Leave storage untouched when no folder has been submitted."""
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Consume Enter so it cannot also select a hidden browser row."""
        event.stop()
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Validate Add & Scan, or close without changes on Cancel."""
        event.stop()
        if event.button.id == "add-library-submit":
            self._submit()
        elif event.button.id == "add-library-cancel":
            self.action_cancel()

    def _submit(self) -> None:
        """Resolve user-friendly paths and keep invalid input available to edit."""
        text = self.query_one(Input).value.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            text = text[1:-1]
        try:
            if not text.strip():
                raise ValueError("Enter a sample folder path")
            path = normalize_path(text)
            if not path.is_dir():
                raise ValueError("Folder does not exist or is not a directory")
        except (OSError, ValueError) as exc:
            self.query_one("#add-library-error", Static).update(str(exc))
            return
        self.dismiss(path)
