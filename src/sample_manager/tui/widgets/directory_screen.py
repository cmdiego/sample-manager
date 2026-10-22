"""Expandable directory contents inspector, independent of Browser navigation."""

import asyncio
from pathlib import Path
from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode

from ...services.directory_listing import DirectoryItem, list_directory


class ContentsTree(Tree[DirectoryItem]):
    """Add familiar directional expand/collapse keys to Textual's tree."""

    BINDINGS = [
        Binding("right,l", "expand_folder", "Expand", show=False),
        Binding("left,h", "collapse_folder", "Collapse", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def action_expand_folder(self) -> None:
        """Expand a folder, or enter its first loaded child on a second press."""
        node = self.cursor_node
        if node is not None and node.allow_expand:
            if node.is_expanded and node.children:
                self.move_cursor(node.children[0])
            else:
                node.expand()

    def action_collapse_folder(self) -> None:
        """Collapse the current folder, or move to its parent from a leaf."""
        node = self.cursor_node
        if node is not None:
            if node.is_expanded:
                node.collapse()
            elif node.parent is not None:
                self.move_cursor(node.parent)


class DirectoryScreen(ModalScreen):
    """Inspect nested folders and all files without moving the browser cursor."""

    DEFAULT_CSS = """
    DirectoryScreen { align: center middle; }
    #directory-dialog {
        width: 100; max-width: 95%; height: 85%;
        border: round $accent; background: $surface; padding: 0 1;
    }
    #directory-title { height: auto; max-height: 3; text-style: bold; color: $accent; }
    #directory-status { height: 1; color: $text-muted; }
    #directory-tree { height: 1fr; }
    #directory-hint { height: auto; color: $text-muted; }
    """

    def __init__(
        self, path: Path, *,
        sample_selected: Callable[[Path], bool | None] | None = None,
        change_stage: Callable[[Path, str], str] | None = None,
    ) -> None:
        """Capture the inspected folder and track per-node asynchronous reads."""
        super().__init__()
        self._path = path
        # Keep storage and destination choices in the app, outside this tree.
        self._sample_selected = sample_selected
        self._change_stage = change_stage
        self._loaded: set[int] = set()
        self._pending: set[int] = set()
        self._files = 0
        self._folders = 0
        self._links = 0

    def compose(self) -> ComposeResult:
        """Use literal labels so bracketed names remain normal filenames."""
        with Vertical(id="directory-dialog"):
            yield Static(f"Directory contents — {self._path}", id="directory-title", markup=False)
            yield Static("Reading directory…", id="directory-status", markup=False)
            yield ContentsTree(Text(f"{self._path.name or self._path}/"), data=DirectoryItem(self._path, True), id="directory-tree")
            yield Static(
                "j/k ↑/↓ Move · l/→ Expand · h/← Collapse · "
                + ("Enter Toggle Stage · a Add · d Remove · [✓] Staged · " if self._change_stage else "")
                + "Esc Close", id="directory-hint", markup=False,
            )

    def on_mount(self) -> None:
        """Open the inspected root immediately while its contents load off-thread."""
        tree = self.query_one(ContentsTree)
        tree.focus()
        tree.root.expand()
        self._queue_children(tree.root)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Read a nested folder only when the user chooses to expand it."""
        event.stop()
        self._queue_children(event.node)

    def _queue_children(self, node: TreeNode[DirectoryItem]) -> None:
        """Deduplicate repeat expands and leave links visible as terminal leaves."""
        item = node.data
        if item is None or not item.is_dir or item.is_symlink:
            return
        if node.id in self._loaded or node.id in self._pending:
            return
        self._pending.add(node.id)
        self.run_worker(self._load_children(node), group="directory-contents", exit_on_error=False)

    async def _load_children(self, node: TreeNode[DirectoryItem]) -> None:
        """Populate a single subtree, keeping errors local and the UI responsive."""
        try:
            items = await asyncio.to_thread(list_directory, node.data.path)
        except asyncio.CancelledError:
            return
        except OSError as exc:
            if self.is_mounted:
                node.add_leaf(Text(f"Cannot read directory: {exc}"))
                self.query_one("#directory-status", Static).update("Some directory contents are unavailable")
        else:
            if not self.is_mounted:
                return
            for item in items:
                node.add(self._item_label(item), data=item, allow_expand=item.is_dir and not item.is_symlink)
            if not items:
                node.add_leaf(Text("(empty directory)"))
            self._folders += sum(item.is_dir for item in items)
            self._files += sum(not item.is_dir and not item.is_symlink for item in items)
            self._links += sum(item.is_symlink for item in items)
            self.query_one("#directory-status", Static).update(
                f"{self._folders} folders · {self._files} files · {self._links} links loaded"
            )
        finally:
            self._pending.discard(node.id)
        self._loaded.add(node.id)

    def _item_label(self, item: DirectoryItem) -> Text:
        """Mark eligible samples without interpreting brackets in their filenames."""
        suffix = "@ (link)" if item.is_symlink else "/" if item.is_dir else ""
        selected = (
            self._sample_selected(item.path)
            if self._sample_selected and not item.is_dir and not item.is_symlink else None
        )
        prefix = ("[✓] " if selected else "[ ] ") if selected is not None else ""
        return Text(f"{prefix}{item.path.name}{suffix}")

    def _update_stage(self, action: str) -> None:
        """Apply a single-file operation and repaint loaded marks without rebuilding."""
        if self._change_stage is None:
            return
        node = self.query_one(ContentsTree).cursor_node
        item = node.data if node is not None else None
        status = self.query_one("#directory-status", Static)
        if item is None or item.is_dir or item.is_symlink:
            status.update("Choose an indexed sample file to add or remove from Stage")
            return
        try:
            message = self._change_stage(item.path, action)
        except Exception as exc:  # noqa: BLE001 - leave storage errors local and retryable
            status.update(f"Stage: {exc}")
            return
        # Repaint all aliases of a selected sample while preserving expansion,
        # scrolling, and the exact cursor node the user is acting on.
        pending = [self.query_one(ContentsTree).root]
        while pending:
            current = pending.pop()
            if current.data is not None:
                current.set_label(self._item_label(current.data))
            pending.extend(current.children)
        status.update(message)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Enter/click on a file toggles Stage; Tree still owns folder expansion."""
        event.stop()
        if event.node.data is not None and not event.node.data.is_dir:
            self._update_stage("toggle")

    def on_key(self, event) -> None:
        """Dismiss without letting the same key alter or quit the underlying app."""
        if self._change_stage is not None and event.key in ("a", "d"):
            event.stop()
            event.prevent_default()
            self._update_stage("add" if event.key == "a" else "remove")
            return
        if event.key in ("escape", "q", "i"):
            event.stop()
            self.dismiss(None)
