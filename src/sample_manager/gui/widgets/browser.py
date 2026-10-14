"""Browser zone — indexed search field, breadcrumb, and result list view.

Presentation-only. It renders whatever model the controller supplies and forwards user intent (navigation,
selection toggles, focus changes) back to the controller via signals. It never
issues SQL.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from ..models.browser_model import IsDirRole, PathRole, SampleIdRole


class BrowserWidget(QWidget):
    """The main directory browser view."""

    # Emitted with an absolute path when the user descends into a directory.
    directory_activated = Signal(Path)
    # Emitted with a sample_id when the user toggles a file's selection.
    selection_toggled = Signal(int)
    # Emitted with a sample_id (or -1) as the focused row changes.
    focus_changed = Signal(int)
    # Context-menu intents (right-click on a browser item).
    add_to_selection_requested = Signal(int)
    remove_from_selection_requested = Signal(int)
    open_externally_requested = Signal(str)
    search_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("BrowserWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._filter = QLineEdit()
        self._filter.setObjectName("BrowserFilter")
        self._filter.setPlaceholderText("Search library by name, path, or tag…")
        self._filter.setClearButtonEnabled(True)
        # Click-focus only: the filter must not auto-grab keyboard focus on
        # startup (that would disable the nav shortcuts via the typing guard).
        # The "/" shortcut focuses it explicitly, which still works.
        self._filter.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        layout.addWidget(self._filter)

        self._search_feedback = QLabel("")
        self._search_feedback.setObjectName("BrowserSearchFeedback")
        self._search_feedback.hide()
        layout.addWidget(self._search_feedback)

        self._breadcrumb = QLabel("")
        self._breadcrumb.setObjectName("BrowserBreadcrumb")
        self._breadcrumb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._breadcrumb)

        self._view = QListView()
        self._view.setObjectName("BrowserList")
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.setDragEnabled(True)
        self._view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # The list must not take keyboard focus: otherwise its built-in arrow-key
        # navigation and type-ahead search would consume J/K/H/L/arrows via
        # ShortcutOverride before the window-level QShortcuts could fire. Focus
        # movement is driven entirely through the shortcuts + mouse clicks.
        self._view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._view, stretch=1)

        self._proxy = QSortFilterProxyModel(self)
        # The proxy maps result indexes to the source model for navigation and
        # drag. Search itself runs over the indexed library in the service.

        self._filter.textChanged.connect(self._on_filter_text)
        self._view.doubleClicked.connect(self._on_activated)
        self._view.activated.connect(self._on_activated)
        self._view.customContextMenuRequested.connect(self._on_context_menu)

    # -- wiring ---------------------------------------------------------------

    def set_source_model(self, model) -> None:
        """Attach the browser model behind the filter proxy."""
        self._proxy.setSourceModel(model)
        self._view.setModel(self._proxy)
        sel = self._view.selectionModel()
        if sel is not None:
            sel.currentChanged.connect(self._on_current_changed)

    @property
    def proxy(self) -> QSortFilterProxyModel:
        return self._proxy

    @property
    def view(self) -> QListView:
        return self._view

    def set_breadcrumb(self, path: Path) -> None:
        self._breadcrumb.setText(str(path))

    # -- focus / filter API (driven by keyboard shortcuts) --------------------

    def move_focus(self, delta: int) -> None:
        """Move the focused (current) row by *delta*, clamped to the ends."""
        model = self._view.model()
        if model is None:
            return
        count = model.rowCount()
        if count == 0:
            return
        current = self._view.currentIndex()
        row = current.row() if current.isValid() else -1
        new_row = max(0, min(count - 1, row + delta))
        self._view.setCurrentIndex(model.index(new_row, 0))

    def focus_first(self) -> None:
        """Focus the first visible row (used after navigation / filtering)."""
        model = self._view.model()
        if model is not None and model.rowCount() > 0:
            self._view.setCurrentIndex(model.index(0, 0))

    def current_index(self) -> QModelIndex:
        return self._view.currentIndex()

    def current_data(self, role: int):
        idx = self._view.currentIndex()
        return idx.data(role) if idx.isValid() else None

    def focus_filter(self) -> None:
        self._filter.setFocus()

    def focus_list(self) -> None:
        # The list itself is NoFocus; moving keyboard focus off the filter is
        # enough to re-enable the window-level navigation shortcuts.
        self._filter.clearFocus()

    def filter_text(self) -> str:
        return self._filter.text()

    def clear_filter(self) -> None:
        self._filter.clear()

    def set_search_feedback(self, query: str, count: int) -> None:
        """Show whether the active library search found indexed samples."""
        self._search_feedback.setVisible(bool(query.strip()))
        if query.strip():
            suffix = " (showing up to 500)" if count >= 500 else ""
            message = f"{count} indexed matches{suffix}"
            if count == 0:
                message += " · Scan the library if a file is missing"
            else:
                message += " · Enter or click to audition"
            self._search_feedback.setText(message)

    def filter_has_focus(self) -> bool:
        return self._filter.hasFocus()

    @property
    def filter_field(self) -> QLineEdit:
        return self._filter

    # -- internal slots -------------------------------------------------------

    def _on_filter_text(self, text: str) -> None:
        """Forward search text; the controller owns the root-wide result set."""
        self.search_changed.emit(text)

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self._view.indexAt(pos)
        if not index.isValid():
            return
        menu = self._build_context_menu(index)
        if menu is not None:
            menu.exec(self._view.viewport().mapToGlobal(pos))

    def _build_context_menu(self, index: QModelIndex) -> QMenu | None:
        """Build (but do not show) the context menu for *index*.

        Exposed for tests so they can trigger actions without popping a blocking
        native menu.
        """
        if not index.isValid():
            return None
        menu = QMenu(self)
        is_dir = index.data(IsDirRole)
        sample_id = index.data(SampleIdRole)
        path = index.data(PathRole)
        if not is_dir and sample_id is not None:
            sid = int(sample_id)
            add = menu.addAction("Add")
            add.triggered.connect(lambda: self.add_to_selection_requested.emit(sid))
            remove = menu.addAction("Remove")
            remove.triggered.connect(lambda: self.remove_from_selection_requested.emit(sid))
        if path:
            open_action = menu.addAction("Open in file manager")
            open_action.triggered.connect(lambda: self.open_externally_requested.emit(str(path)))
        return menu

    def _on_activated(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        is_dir = index.data(IsDirRole)
        sample_id = index.data(SampleIdRole)
        if is_dir:
            path = index.data(PathRole)
            if path:
                self.directory_activated.emit(Path(path))
        elif sample_id is not None:
            self.selection_toggled.emit(int(sample_id))

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            self.focus_changed.emit(-1)
            return
        sample_id = current.data(SampleIdRole)
        self.focus_changed.emit(int(sample_id) if sample_id is not None else -1)
