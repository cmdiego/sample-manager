"""``MainWindow`` — the four-zone Qt shell.

Layout (a vertical splitter of two horizontal splitters):

    +-------------------------------+-----------------+
    |  Preview (75%)                | Stage Summary   |   top row
    +-------------------------------+-----------------+
    |  Browser (75%)                | Selected (25%)  |   bottom row
    +-------------------------------+-----------------+

Window geometry and splitter positions are restored from ``QSettings`` on open
and persisted on close. The window wires widgets to the ``BrowserController`` via
signals; it holds no ``Db`` and issues no SQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QEvent, QSignalBlocker, QThreadPool, Qt, QSettings, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QLabel, QLineEdit, QMainWindow, QSplitter,
    QToolBar, QWidget,
)

from .controller import BrowserController
from .dialogs import ActionDialog, CommandDialog, CommandPaletteDialog, HelpDialog, SettingsDialog
from .command_interpreter import CommandInterpreter
from .models.browser_model import IsDirRole, PathRole, SampleIdRole

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..audio.player import PlaybackSnapshot
    from ..audio.waveform import WaveformService
from .shortcuts import install_shortcuts
from .workers import Worker
from .widgets.browser import BrowserWidget
from .widgets.preview import PreviewWidget
from .widgets.selection import SelectionWidget
from .widgets.session_summary import SessionSummaryWidget

# Single-key shortcuts that must yield to a focused text field so the user can
# type these characters (or move the text cursor) instead of triggering nav.
_TYPING_SENSITIVE_KEYS = frozenset(
    {
        "J", "K", "H", "L",
        "Down", "Up", "Left", "Right",
    "Return", "Space", "Ctrl+Space", "Escape", "A", "D", "/", "?",
    }
)

SETTINGS_ORG = "SampleManager"
SETTINGS_APP = "SampleManager"


class MainWindow(QMainWindow):
    """The top-level GUI window."""

    def __init__(
        self,
        controller: BrowserController,
        waveform_service: "WaveformService | None" = None,
        audio_player_factory=None,
        preferred_root_path: Path | None = None,
        on_library_selected: Callable[[Path], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._audio_player_factory = audio_player_factory
        self._on_library_selected = on_library_selected
        self._scan_worker: Worker | None = None
        self._active_dialog = None
        self._command_interpreter = CommandInterpreter()
        self.setWindowTitle("Sample Manager")
        self.setObjectName("SampleManagerMainWindow")

        # -- application menu ------------------------------------------------
        app_menu = self.menuBar().addMenu("&Application")
        self._settings_action = QAction("Settings…", self)
        self._settings_action.setObjectName("SettingsAction")
        self._settings_action.setShortcut(QKeySequence("Meta+,"))
        self._settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        self._settings_action.triggered.connect(self._show_settings)
        app_menu.addAction(self._settings_action)

        # Keep library selection and indexing discoverable even when the
        # current database has no roots yet.
        library_toolbar = QToolBar("Libraries", self)
        library_toolbar.setObjectName("LibraryToolbar")
        library_toolbar.setMovable(False)
        self.addToolBar(library_toolbar)
        library_toolbar.addWidget(QLabel("Library: "))
        self._root_picker = QComboBox(self)
        self._root_picker.setObjectName("LibraryRootPicker")
        self._root_picker.setMinimumContentsLength(24)
        self._root_picker.currentIndexChanged.connect(self._on_root_picked)
        library_toolbar.addWidget(self._root_picker)
        self._add_library_action = QAction("Add Folder…", self)
        self._add_library_action.setObjectName("AddLibraryAction")
        self._add_library_action.triggered.connect(self._choose_library_folder)
        library_toolbar.addAction(self._add_library_action)
        self._rescan_action = QAction("Rescan", self)
        self._rescan_action.setObjectName("RescanLibraryAction")
        self._rescan_action.triggered.connect(self._rescan_current_library)
        library_toolbar.addAction(self._rescan_action)

        # -- zones ------------------------------------------------------------
        self._preview = PreviewWidget(waveform_service=waveform_service)
        self._session = SessionSummaryWidget()
        self._browser = BrowserWidget()
        self._selection = SelectionWidget()

        # -- splitters --------------------------------------------------------
        self._top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_splitter.setObjectName("TopSplitter")
        self._top_splitter.addWidget(self._preview)
        self._top_splitter.addWidget(self._session)
        self._top_splitter.setStretchFactor(0, 3)
        self._top_splitter.setStretchFactor(1, 1)

        self._bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._bottom_splitter.setObjectName("BottomSplitter")
        self._bottom_splitter.addWidget(self._browser)
        self._bottom_splitter.addWidget(self._selection)
        self._bottom_splitter.setStretchFactor(0, 3)
        self._bottom_splitter.setStretchFactor(1, 1)

        self._main_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_splitter.setObjectName("MainSplitter")
        self._main_splitter.addWidget(self._top_splitter)
        self._main_splitter.addWidget(self._bottom_splitter)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 1)

        container = QWidget()
        container.setObjectName("CentralContainer")
        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._main_splitter)
        self.setCentralWidget(container)

        # -- model wiring -----------------------------------------------------
        self._browser.set_source_model(self._controller.browser_model)
        self._selection.set_model(self._controller.selection_model)

        # -- signal wiring ----------------------------------------------------
        self._browser.directory_activated.connect(self._controller.navigate_to)
        self._browser.selection_toggled.connect(self._controller.toggle_selection)
        self._browser.focus_changed.connect(self._on_focus_changed)
        self._browser.add_to_selection_requested.connect(self._controller.add_to_selection)
        self._browser.remove_from_selection_requested.connect(
            self._controller.remove_from_selection
        )
        self._browser.open_externally_requested.connect(self._on_open_externally)
        self._selection.remove_requested.connect(self._controller.remove_from_selection)
        self._selection.add_requested.connect(self._controller.add_to_selection)
        self._selection.detail_requested.connect(self._on_focus_changed)
        self._browser.search_changed.connect(self._on_search_changed)

        self._controller.current_path_changed.connect(self._browser.set_breadcrumb)
        self._controller.current_path_changed.connect(self._on_path_changed)
        self._controller.current_path_changed.connect(self._on_status_path)
        self._controller.selection_changed.connect(self._session.set_summary)
        self._controller.playback_changed.connect(self._preview.on_playback_changed)
        self._controller.playback_changed.connect(self._on_playback_changed)

        # -- status bar (dir | playback | errors) ----------------------------
        self._status_dir = QLabel("")
        self._status_playback = QLabel("")
        self._status_error = QLabel("")
        self._status_error.setObjectName("StatusError")
        bar = self.statusBar()
        bar.addWidget(self._status_dir, 1)
        bar.addWidget(self._status_playback, 2)
        bar.addPermanentWidget(self._status_error)
        self._error_clear_timer = QTimer(self)
        self._error_clear_timer.setSingleShot(True)
        self._error_clear_timer.setInterval(5000)
        self._error_clear_timer.timeout.connect(lambda: self._status_error.setText(""))

        # -- shortcuts (full parity with the terminal TUI) -------------------
        self._shortcuts = install_shortcuts(
            self,
            {
                # Focus movement.
                "J": lambda: self._browser.move_focus(1),
                "Down": lambda: self._browser.move_focus(1),
                "K": lambda: self._browser.move_focus(-1),
                "Up": lambda: self._browser.move_focus(-1),
                # Directory navigation.
                "H": self._controller.navigate_up,
                "Left": self._controller.navigate_up,
                "Backspace": self._controller.navigate_up,
                "Alt+Up": self._controller.navigate_up,
                "L": self._activate_focused_l,
                "Right": self._activate_focused_l,
                "Return": self._activate_focused_return,
                # Playback (wired in Phase 4).
                "Space": self._toggle_playback,
                "Ctrl+Space": self._resume_playback,
                # Selection.
                "A": self._add_focused,
                "D": self._remove_focused,
                # Filter + dialogs.
                "/": self._focus_filter,
                "Escape": self._on_escape,
                "?": self._show_help,
                "Ctrl+P": self._show_command_palette,
            },
        )
        self._install_focus_guard()

        # -- initial state ----------------------------------------------------
        self._session.set_summary(self._controller.selection_summary())
        roots = self._controller.library_roots()
        preferred = next(
            (root for root in roots if root.path == preferred_root_path), None
        )
        initial = preferred or (roots[0] if roots else None)
        self._refresh_library_picker(initial.id if initial else None)
        if initial is not None:
            self._select_library(initial.id, persist=False)

        self._restore_settings()

    # -- library roots and scanning ------------------------------------------

    def _refresh_library_picker(self, selected_id: int | None = None) -> None:
        """Rebuild the picker from indexed roots without triggering navigation."""
        roots = self._controller.library_roots()
        with QSignalBlocker(self._root_picker):
            self._root_picker.clear()
            for root in roots:
                self._root_picker.addItem(str(root.path), root.id)
            chosen = self._root_picker.findData(selected_id)
            self._root_picker.setCurrentIndex(chosen if chosen >= 0 else (0 if roots else -1))
        self._rescan_action.setEnabled(bool(roots) and self._scan_worker is None)

    def _on_root_picked(self, index: int) -> None:
        """Switch roots when the user chooses a different indexed library."""
        if index >= 0:
            self._select_library(int(self._root_picker.itemData(index)))

    def _select_library(self, root_id: int, *, persist: bool = True) -> None:
        """Load a real root and clear search results from the previous root."""
        root = next((r for r in self._controller.library_roots() if r.id == root_id), None)
        if root is None or not root.path.is_dir():
            active = self._controller.current_root
            if active is not None and active.id != root_id:
                # The combo box has already moved; put its highlight back on
                # the library the browser is still showing.
                self._refresh_library_picker(active.id)
            self.show_status_error("Library folder is missing; choose another folder")
            return
        self._browser.clear_filter()
        self._controller.load_root(root)
        if persist and self._on_library_selected is not None:
            try:
                self._on_library_selected(root.path)
            except (OSError, ValueError) as exc:
                self.show_status_error(f"Could not save library preference: {exc}")

    def _choose_library_folder(self) -> None:
        """Ask for a folder, then index it without holding up the Qt event loop."""
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Sample Library", str(Path.home())
        )
        if folder:
            self._start_scan(Path(folder))

    def _rescan_current_library(self) -> None:
        """Reconcile the active library with files currently on disk."""
        root = self._controller.current_root
        if root is not None:
            self._start_scan(root.path)

    def _start_scan(self, path: Path) -> None:
        """Start one scanner job with an independent database connection."""
        if self._scan_worker is not None:
            return
        if not path.is_dir():
            self.show_status_error(f"Library folder is unavailable: {path}")
            return
        self._add_library_action.setEnabled(False)
        self._rescan_action.setEnabled(False)
        self._root_picker.setEnabled(False)
        self.statusBar().showMessage(f"Scanning {path}…")
        worker = Worker(self._controller.service.scan_directory, path)
        worker.signals.result.connect(self._on_scan_result)
        worker.signals.error.connect(self._on_scan_error)
        worker.signals.finished.connect(self._on_scan_finished)
        self._scan_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_scan_result(self, result) -> None:
        """Refresh Qt models only after the worker commits its scanner result."""
        current = self._controller.current_root
        self._refresh_library_picker(result.library_root_id)
        if current is not None and current.id == result.library_root_id:
            self._controller.refresh_after_scan(self._browser.filter_text())
            self._browser.set_search_feedback(
                self._browser.filter_text(), self._controller.browser_model.rowCount()
            )
        else:
            self._select_library(result.library_root_id)
        self.statusBar().showMessage(
            f"Scanned {result.total_on_disk} files: "
            f"{result.inserted} new, {result.updated} updated, {result.pruned} removed",
            10000,
        )

    def _on_scan_error(self, error: Exception) -> None:
        """Keep the existing library usable after an indexing failure."""
        self.statusBar().clearMessage()
        self.show_status_error(f"Scan failed: {error}")

    def _on_scan_finished(self) -> None:
        """Restore controls after either a completed or failed scan."""
        self._scan_worker = None
        self._root_picker.setEnabled(True)
        self._add_library_action.setEnabled(True)
        self._rescan_action.setEnabled(self._controller.current_root is not None)

    # -- typing guard ---------------------------------------------------------

    def _install_focus_guard(self) -> None:
        """Disable single-key shortcuts while a text field has focus.

        A ``QShortcut`` consumes the key event before a focused ``QLineEdit``
        sees it, so ``/``, ``j``, arrow keys, etc. could never be typed or used
        for cursor movement in the filter/palette. Toggling the sensitive
        shortcuts on app-level focus changes fixes this without per-slot guards.
        """
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_app_focus_changed)
            # A list with NoFocus does not take focus on mouse press. Watch the
            # press itself so clicking a search result still exits typing mode.
            app.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802
        """Handle search transport keys and click-away before widgets consume them."""
        field = self._browser.filter_field
        if self._active_dialog is None and obj is field and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Space:
                if event.modifiers() == Qt.KeyboardModifier.NoModifier:
                    self._toggle_playback()
                    return True
                if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                    self._resume_playback()
                    return True
            if event.key() == Qt.Key.Key_Escape:
                self._on_escape()
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._browser.focus_first()
                field.clearFocus()
                return True
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._browser.focus_first()
                field.clearFocus()
                return True
        if (
            self._active_dialog is None
            and event.type() == QEvent.Type.MouseButtonPress
            and field.hasFocus()
            and obj is not field
            and not (isinstance(obj, QWidget) and field.isAncestorOf(obj))
        ):
            # Leave results visible so a click can act on the row the user saw.
            field.clearFocus()
        return super().eventFilter(obj, event)

    def _on_app_focus_changed(self, _old, now) -> None:
        # While a dialog is open the shortcuts are suspended wholesale; don't let
        # a focus change inside the dialog re-enable them.
        if self._active_dialog is not None:
            return
        typing = isinstance(now, QLineEdit)
        for seq, shortcut in self._shortcuts.items():
            if seq in _TYPING_SENSITIVE_KEYS:
                shortcut.setEnabled(not typing)

    def _on_search_changed(self, query: str) -> None:
        """Refresh indexed results without auditioning every typed prefix."""
        count = self._controller.search(query)
        self._browser.set_search_feedback(query, count)
        if not query.strip():
            self._browser.focus_first()

    # -- focus → preview ------------------------------------------------------

    def _on_focus_changed(self, sample_id: int) -> None:
        if sample_id is None or sample_id < 0:
            # A model reset during text entry clears the row selection. Keep
            # the current preview and audition until the user chooses a hit.
            if self._browser.filter_text().strip():
                return
            self._preview.clear()
            self._controller.set_focus(None)
            return
        details = self._controller.service.sample_details(sample_id)
        self._preview.show_details(details)
        path = self._controller.service.sample_path(sample_id)
        self._preview.set_focus_path(path)
        self._controller.set_focus(sample_id)

    def _on_path_changed(self, _path) -> None:
        # A new directory starts ordinary browsing; stale search results should
        # not replace its contents on the next key press.
        if self._browser.filter_text():
            self._browser.clear_filter()
        self._browser.focus_first()

    # -- status bar -----------------------------------------------------------

    def _on_status_path(self, path) -> None:
        self._status_dir.setText(str(path))

    def _on_playback_changed(self, snapshot: "PlaybackSnapshot") -> None:
        self._status_playback.setText(_format_playback(snapshot))
        error = getattr(snapshot, "error", None)
        if error:
            self.show_status_error(error)

    def show_status_error(self, message: str) -> None:
        """Show *message* in the right status section; auto-clear after 5 s."""
        self._status_error.setText(message)
        self._error_clear_timer.start()

    # -- shortcut handlers ----------------------------------------------------

    def _focused_sample_id(self) -> int | None:
        sid = self._browser.current_data(SampleIdRole)
        return int(sid) if sid is not None else None

    def _activate_focused_l(self) -> None:
        """``L`` / Right: enter a directory, or open the action dialog for a file."""
        self._activate_focused(file_opens_dialog=True)

    def _activate_focused_return(self) -> None:
        """``Return``: enter a directory, or toggle a file's selection."""
        self._activate_focused(file_opens_dialog=False)

    def _activate_focused(self, *, file_opens_dialog: bool) -> None:
        index = self._browser.current_index()
        if not index.isValid():
            return
        if index.data(IsDirRole):
            path = index.data(PathRole)
            if path:
                self._controller.navigate_to(Path(path))
            return
        sample_id = index.data(SampleIdRole)
        if sample_id is None:
            return
        if file_opens_dialog:
            self._open_action_dialog(int(sample_id))
        else:
            self._controller.toggle_selection(int(sample_id))

    def _add_focused(self) -> None:
        sid = self._focused_sample_id()
        if sid is not None:
            self._controller.add_to_selection(sid)

    def _remove_focused(self) -> None:
        sid = self._focused_sample_id()
        if sid is not None:
            self._controller.remove_from_selection(sid)

    def _toggle_playback(self) -> None:
        """``Space``: pause or resume, starting the focused sample if idle."""
        self._controller.toggle_focused_playback()

    def _resume_playback(self) -> None:
        """``Ctrl+Space``: resume a paused track from its checkpoint."""
        self._controller.resume_playback()

    def _focus_filter(self) -> None:
        self._browser.focus_filter()

    def _on_escape(self) -> None:
        # Escape always exits search, including an empty focused search field.
        if self._browser.filter_text() or self._browser.filter_has_focus():
            self._browser.clear_filter()
            self._browser.focus_list()
            return
        # Priority 2: close any open (non-modal) dialog.
        if self._active_dialog is not None and self._active_dialog.isVisible():
            self._active_dialog.close()
            self._active_dialog = None

    def _on_open_externally(self, path: str) -> None:
        """Open a sample's parent folder (or a directory) in the file manager."""
        target = Path(path)
        folder = target if target.is_dir() else target.parent
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.show_status_error(f"Could not open folder: {folder}")

    # -- dialogs --------------------------------------------------------------

    def _show_dialog(self, dialog) -> None:
        """Show *dialog* non-modally and suspend the global shortcuts.

        Because shortcuts use ``ApplicationShortcut`` context they would
        otherwise fire while a dialog is open (e.g. ``J`` scrolling the browser
        behind a help dialog). They are re-enabled when the dialog closes.
        """
        self._active_dialog = dialog
        self._set_all_shortcuts_enabled(False)
        dialog.finished.connect(self._on_dialog_finished)
        dialog.show()

    def _on_dialog_finished(self, _result: int) -> None:
        self._active_dialog = None
        self._set_all_shortcuts_enabled(True)
        # A dialog may return focus to search without a fresh focusChanged
        # signal, so restore the typing guard after re-enabling shortcuts.
        from PySide6.QtWidgets import QApplication

        self._on_app_focus_changed(None, QApplication.focusWidget())

    def _set_all_shortcuts_enabled(self, enabled: bool) -> None:
        for shortcut in self._shortcuts.values():
            shortcut.setEnabled(enabled)

    def _open_action_dialog(self, sample_id: int) -> None:
        details = self._controller.service.sample_details(sample_id)
        dialog = ActionDialog(
            details,
            on_add=self._controller.add_to_selection,
            on_remove=self._controller.remove_from_selection,
            parent=self,
        )
        self._show_dialog(dialog)

    def _show_help(self) -> None:
        self._show_dialog(HelpDialog(parent=self))

    def _show_command_dialog(self, initial_command: str = "") -> None:
        """Show the vim-style command dialog."""
        dialog = CommandDialog(interpreter=self._command_interpreter, parent=self)
        if initial_command:
            dialog.set_initial_command(initial_command)
        self._show_dialog(dialog)

    def _show_command_palette(self) -> None:
        actions = {
            "Add": self._add_focused,
            "Remove": self._remove_focused,
            "Navigate Up": self._controller.navigate_up,
            "Clear Filter": lambda: (self._browser.clear_filter(), self._browser.focus_list()),
            "Open Help": self._show_help,
            "Open Settings": self._show_settings,
            "Command Mode": self._show_command_dialog,
            "Show Manual (/man)": lambda: self._show_command_dialog("man"),
        }
        self._show_dialog(CommandPaletteDialog(actions, parent=self))

    def _show_settings(self) -> None:
        dialog = SettingsDialog(
            on_audio_output_changed=self._apply_audio_output_mode,
            settings=self._settings(),
            parent=self,
        )
        self._show_dialog(dialog)

    def _apply_audio_output_mode(self, selection) -> None:
        if self._audio_player_factory is None:
            return
        player, warning = self._audio_player_factory(selection)
        self._controller.replace_player(player)
        if warning:
            self.show_status_error(warning)
        elif getattr(selection, "device_index", None) is not None:
            self.show_status_error(f"Audio output: device #{selection.device_index}")
        else:
            self.show_status_error("Audio output: System Default")

    # -- test / introspection helpers for dialogs -----------------------------

    @property
    def active_dialog(self):
        return self._active_dialog

    # -- QSettings persistence ------------------------------------------------

    def _settings(self) -> QSettings:
        return QSettings(SETTINGS_ORG, SETTINGS_APP)

    def _restore_settings(self) -> None:
        s = self._settings()
        geometry = s.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        for name, splitter in self._named_splitters():
            state = s.value(f"splitter/{name}")
            if state is not None:
                splitter.restoreState(state)

    def _save_settings(self) -> None:
        s = self._settings()
        s.setValue("window/geometry", self.saveGeometry())
        for name, splitter in self._named_splitters():
            s.setValue(f"splitter/{name}", splitter.saveState())

    def _named_splitters(self):
        return (
            ("main", self._main_splitter),
            ("top", self._top_splitter),
            ("bottom", self._bottom_splitter),
        )

    # -- Qt event overrides ---------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Handle fallback key presses not consumed by window shortcuts."""
        # The "/" shortcut normally focuses the browser filter. Keep this
        # fallback so direct key events still behave correctly if shortcut
        # delivery changes on a platform.
        focused = self.focusWidget()
        is_text_input = isinstance(focused, QLineEdit)

        if event.key() == Qt.Key.Key_Slash and not is_text_input:
            self._focus_filter()
            event.accept()
            return

        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Stop the poll timer and close the audio player (joining its worker
        # thread) before the window tears down, so nothing outlives it.
        self._error_clear_timer.stop()
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            # Each window registered an application-wide mouse/key filter.
            # Remove it at close so a later window receives its own events once.
            app.removeEventFilter(self)
        self._controller.shutdown()
        self._save_settings()
        super().closeEvent(event)

    # -- test / introspection helpers ----------------------------------------

    @property
    def preview(self) -> PreviewWidget:
        return self._preview

    @property
    def session_summary(self) -> SessionSummaryWidget:
        return self._session

    @property
    def browser(self) -> BrowserWidget:
        return self._browser

    @property
    def selection(self) -> SelectionWidget:
        return self._selection

    @property
    def controller(self) -> BrowserController:
        return self._controller


def _format_time(seconds: float | None) -> str:
    """Format seconds as ``m:ss`` (``0:00`` when unknown)."""
    total = int(seconds or 0)
    return f"{total // 60}:{total % 60:02d}"


def _format_playback(snapshot) -> str:
    """Render a playback snapshot for the status bar's centre section.

    e.g. ``PLAYING — sample.wav [0:03 / 0:09]`` or ``IDLE``.
    """
    status = snapshot.status.name if snapshot is not None else "IDLE"
    if snapshot is None or snapshot.path is None:
        return status
    name = Path(snapshot.path).name
    elapsed = _format_time(snapshot.position_seconds)
    duration = _format_time(snapshot.duration_seconds)
    return f"{status} — {name} [{elapsed} / {duration}]"
