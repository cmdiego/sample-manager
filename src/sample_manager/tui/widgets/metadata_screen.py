"""Expanded scrolling view for every available native metadata field."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from .metadata_panel import MetadataPanel


class MetadataScreen(ModalScreen):
    """Keep a live reference so in-flight metadata appears without reopening."""

    DEFAULT_CSS = """
    MetadataScreen { align: center middle; }
    #metadata-dialog {
        width: 88; max-width: 95%; height: 80%;
        border: round $accent; background: $surface; padding: 0 2;
    }
    #metadata-title { height: auto; text-style: bold; color: $accent; }
    #metadata-full-values { height: auto; margin-top: 1; }
    #metadata-hint { height: 1; dock: bottom; color: $text-muted; }
    """

    def __init__(self, panel: MetadataPanel) -> None:
        """Bind the opened view to the focused file and its loading result."""
        super().__init__()
        self._panel = panel
        self._shown = None

    def compose(self) -> ComposeResult:
        """Let long values wrap and let standard Textual keys scroll the view."""
        with VerticalScroll(id="metadata-dialog"):
            yield Static(f"Metadata — {self._panel.path.name}", id="metadata-title", markup=False)
            yield Static("", id="metadata-full-values", markup=False)
            yield Static("↑/↓ Scroll · PgUp/PgDn Page · Esc Close", id="metadata-hint", markup=False)

    def on_mount(self) -> None:
        """Show cached data immediately and track an in-flight read if needed."""
        self.query_one("#metadata-dialog").focus()
        self._refresh_values()
        self.set_interval(0.1, self._refresh_values)

    def _refresh_values(self) -> None:
        """Refresh only when loading completes, preserving the scroll position."""
        state = (self._panel.rows, self._panel.message, self._panel.library_tags)
        if state != self._shown:
            self._shown = state
            fields = [f"{label}: {value}" for label, value in self._panel.rows]
            if self._panel.library_tags:
                fields.insert(0, "Library tags: " + " · ".join(self._panel.library_tags))
            if self._panel.message:
                fields.append(self._panel.message)
            self.query_one("#metadata-full-values", Static).update("\n\n".join(fields))

    def on_key(self, event) -> None:
        """Consume dismiss keys so closing cannot quit the underlying app."""
        if event.key in ("escape", "q", "i"):
            event.stop()
            self.dismiss(None)
