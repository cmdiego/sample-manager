"""Collapsible folder/tag choices alongside the existing sample browser."""

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.containers import Vertical
from textual.widgets import OptionList, Static


class BrowseColumns(Widget):
    """Present facet choices; app/service actions own filtering and navigation."""

    DEFAULT_CSS = """
    BrowseColumns { width: 38; height: 1fr; layout: horizontal; }
    BrowseColumns Vertical { width: 1fr; height: 1fr; border-right: solid $panel-lighten-2; }
    BrowseColumns Static { height: 1; color: $text-muted; }
    BrowseColumns OptionList { height: 1fr; border: none; }
    .narrow BrowseColumns { display: none; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._key = None
        self.paths = []
        self.tags = []

    def compose(self) -> ComposeResult:
        """Lists own keyboard/mouse highlighting without changing sample focus."""
        with Vertical():
            yield Static("Folders")
            yield OptionList(id="folder-column")
        with Vertical():
            yield Static("Tags")
            yield OptionList(id="tag-column")

    def on_mount(self) -> None:
        """Column lists must not steal the application's initial browser keys."""
        for view in self.query(OptionList):
            view.can_focus = False

    def update_choices(self, state, facets):
        """Rebuild only when folder/tag choices change, retaining highlights."""
        folders = [state.current_dir] + [item.path for item in state.items if item.is_dir and item.name != ".."]
        if state.current_dir != state.current_root:
            folders.insert(0, state.current_dir.parent)
        tags = [None] + [row["name_display"] for row in facets]
        key = (state.current_dir, tuple(folders), tuple((r["name_display"], r["samples"]) for r in facets))
        if key == self._key:
            return
        self._key, self.paths, self.tags = key, folders, tags
        for selector, labels in (
            ("#folder-column", [".." if p == state.current_dir.parent else p.name + "/" for p in folders]),
            ("#tag-column", ["All tags"] + [f"{r['name_display']} ({r['samples']})" for r in facets]),
        ):
            view = self.query_one(selector, OptionList)
            previous = view.highlighted
            view.clear_options().add_options([Text(label) for label in labels])
            view.highlighted = min(previous or 0, len(labels) - 1)
        self.query_one("#folder-column").border_title = "Folders"
        self.query_one("#tag-column").border_title = "Tags"
