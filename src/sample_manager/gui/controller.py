"""``BrowserController`` — coordinates the service, models, and navigation state.

The controller is the seam between the framework-neutral ``LibraryBrowserService``
and the Qt views. It owns one browser model, one selection model, and the current
navigation path, and it emits Qt signals when navigation or selection changes so
widgets can react without knowing about the service.

It never holds a ``Db`` — only a ``LibraryBrowserService``. No SQL lives here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal

from ..services.library_browser import (
    LibraryBrowserService,
    LibraryRoot,
    SelectionSummary,
)
from .models.browser_model import BrowserListModel
from .models.selection_model import SelectionListModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..audio.player import AudioPlayer, PlaybackSnapshot

# How often to poll the audio player for a fresh playback snapshot.
_PLAYBACK_POLL_MS = 200


class BrowserController(QObject):
    """Owns models + navigation state; bridges service and widgets via signals."""

    current_path_changed = Signal(Path)
    selection_changed = Signal(SelectionSummary)
    focus_changed = Signal(int)  # sample_id, or -1 for none
    playback_changed = Signal(object)  # PlaybackSnapshot

    def __init__(
        self,
        service: LibraryBrowserService,
        player: "AudioPlayer | None" = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._player = player
        self._browser_model = BrowserListModel(parent=self)
        self._selection_model = SelectionListModel(service, parent=self)
        self._current_path: Path | None = None
        self._current_root: LibraryRoot | None = None
        self._focused_sample_id: int | None = None
        self._selection_model.reset_from_service()

        # Poll the player on a timer and re-broadcast snapshots as a signal so
        # widgets never call into the player directly.
        self._playback_timer: QTimer | None = None
        if self._player is not None:
            self._start_playback_timer()

    # -- accessors ------------------------------------------------------------

    @property
    def service(self) -> LibraryBrowserService:
        return self._service

    @property
    def player(self) -> "AudioPlayer | None":
        return self._player

    @property
    def browser_model(self) -> BrowserListModel:
        return self._browser_model

    @property
    def selection_model(self) -> SelectionListModel:
        return self._selection_model

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    @property
    def current_root(self) -> LibraryRoot | None:
        return self._current_root

    def library_roots(self) -> tuple[LibraryRoot, ...]:
        return self._service.library_roots()

    # -- navigation -----------------------------------------------------------

    def load_root(self, root: LibraryRoot) -> None:
        """Populate the browser model from a root's top-level directory."""
        self._current_root = root
        self.navigate_to(root.path)

    def navigate_to(self, path: Path) -> None:
        """List *path* and reset the browser model, then announce the change."""
        items = self._service.list_directory(path)
        self._browser_model.reset_with(items)
        self._current_path = path
        self.current_path_changed.emit(path)

    def search(self, query: str) -> int:
        """Show root-wide search hits, or restore the current directory when cleared."""
        if self._current_root is None or self._current_path is None:
            return 0
        items = (
            self._service.search_samples(self._current_root, query)
            if query.strip()
            else self._service.list_directory(self._current_path)
        )
        self._browser_model.reset_with(items)
        return len(items)

    def navigate_up(self) -> None:
        """Ascend to the parent directory, stopping at the current root."""
        if self._current_path is None:
            return
        if self._current_root is not None and self._current_path == self._current_root.path:
            return
        parent = self._current_path.parent
        # Never climb above the root that contains us.
        if self._current_root is not None:
            try:
                parent.relative_to(self._current_root.path)
            except ValueError:
                parent = self._current_root.path
        self.navigate_to(parent)

    # -- selection ------------------------------------------------------------

    def toggle_selection(self, sample_id: int) -> None:
        """Add or remove *sample_id* from the persistent selection buffer."""
        if sample_id in self._service.selection_ids():
            self._service.remove_from_selection(sample_id)
        else:
            self._service.add_to_selection(sample_id)
        self._refresh_after_selection()

    def add_to_selection(self, sample_id: int) -> None:
        """Add *sample_id* to the selection buffer (idempotent)."""
        # A stale or forged drag payload must not trigger a foreign-key error.
        if self._service.sample_details(sample_id) is None:
            return
        self._service.add_to_selection(sample_id)
        self._refresh_after_selection()

    def remove_from_selection(self, sample_id: int) -> None:
        """Remove *sample_id* from the selection buffer (idempotent)."""
        self._service.remove_from_selection(sample_id)
        self._refresh_after_selection()

    def _refresh_after_selection(self) -> None:
        """Sync both models + the summary after any selection mutation.

        Uses an in-place ``update_selection`` on the browser model (dataChanged,
        not a reset) so the focused row is preserved.
        """
        self._browser_model.update_selection(self._service.selection_ids())
        self._selection_model.reset_from_service()
        self.selection_changed.emit(self._service.selection_summary())

    def selection_summary(self) -> SelectionSummary:
        return self._service.selection_summary()

    # -- focus ----------------------------------------------------------------

    def set_focus(self, sample_id: int | None) -> None:
        """Announce which sample is focused and auto-audition it.

        Focusing a **file** loads/plays it (auto-audition). Focusing nothing (a
        directory row, or clearing) leaves the current track untouched so the
        user can keep hearing the last sample while browsing folders.
        """
        self._focused_sample_id = sample_id
        self.focus_changed.emit(sample_id if sample_id is not None else -1)
        if sample_id is None or self._player is None:
            return
        path = self._service.sample_path(sample_id)
        if path is not None:
            self._player.play(path)

    def toggle_focused_playback(self) -> None:
        """Pause active playback, resume a pause, or start the focused sample."""
        if self._player is None:
            return
        from ..audio.player import PlaybackStatus

        snapshot = self._player.snapshot()
        if snapshot.status in (PlaybackStatus.PLAYING, PlaybackStatus.LOADING):
            self._player.pause()
            return
        if snapshot.status is PlaybackStatus.PAUSED and snapshot.path is not None:
            self._player.play(snapshot.path)
            return
        if self._focused_sample_id is None:
            return
        path = self._service.sample_path(self._focused_sample_id)
        if path is not None:
            self._player.play_from_start(path)

    def resume_playback(self) -> None:
        """Resume a paused track from the checkpoint owned by AudioPlayer."""
        if self._player is None:
            return
        from ..audio.player import PlaybackStatus

        snapshot = self._player.snapshot()
        if snapshot.status is PlaybackStatus.PAUSED and snapshot.path is not None:
            self._player.play(snapshot.path)

    # -- playback -------------------------------------------------------------

    def _poll_playback(self) -> None:
        if self._player is None:
            return
        self.playback_changed.emit(self._player.snapshot())

    def replace_player(self, player: "AudioPlayer | None") -> None:
        """Replace the playback engine after an I/O setting change."""
        if player is self._player:
            return
        if self._playback_timer is not None:
            self._playback_timer.stop()
            self._playback_timer.deleteLater()
            self._playback_timer = None
        old_player = self._player
        self._player = player
        if old_player is not None:
            old_player.close()
        if self._player is not None:
            self._start_playback_timer()
            self.playback_changed.emit(self._player.snapshot())
        else:
            from ..audio.player import PlaybackSnapshot, PlaybackStatus

            self.playback_changed.emit(
                PlaybackSnapshot(PlaybackStatus.IDLE, None, 0.0, None, None)
            )

    def _start_playback_timer(self) -> None:
        self._playback_timer = QTimer(self)
        self._playback_timer.setInterval(_PLAYBACK_POLL_MS)
        self._playback_timer.timeout.connect(self._poll_playback)
        self._playback_timer.start()

    def shutdown(self) -> None:
        """Stop the poll timer and close the player. Safe to call repeatedly.

        Called from ``MainWindow.closeEvent`` so no daemon audio thread or timer
        outlives the window.
        """
        if self._playback_timer is not None:
            self._playback_timer.stop()
            self._playback_timer = None
        if self._player is not None:
            self._player.close()
            self._player = None
