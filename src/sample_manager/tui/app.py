"""Sample Manager TUI — main Textual application."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Static

from ..audio import AudioPlayer, PlaybackStatus, WaveformData, WaveformService
from ..config import get_config_path, load_config, normalize_config
from ..db import Db
from ..migrations import apply_migrations
from .data import TuiDataSource
from .keybindings import resolve_key
from .widgets.help_screen import HelpScreen
from .nav_state import NavState, NavItem, build_items
from .widgets.action_pane import ActionPane
from .widgets.browser_zone import BrowserZone
from .widgets.file_tree import SampleListWidget
from .widgets.selection_list import SelectedFilesListWidget
from .widgets.session_summary import SessionSummaryWidget
from .widgets.top_display import TopDisplayWidget


def _open_db() -> Db | None:
    config_path = get_config_path()
    if not config_path.exists():
        return None
    cfg = load_config(config_path)
    normalized = normalize_config(cfg)
    db_path = normalized.get("db_path")
    if not db_path:
        return None
    db = Db(db_path)
    db.connect()
    apply_migrations(db)
    return db


class SampleManagerApp(App):
    """Keyboard-driven TUI for browsing and selecting samples."""

    CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"

    TITLE = "Sample Manager"

    # Extra inline CSS for the grid container (tcss file covers widget styles)
    CSS = """
    #main-grid {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 3fr 1fr;
        grid-rows: 2fr 3fr;
        height: 1fr;
    }
    """

    def __init__(
        self,
        *,
        audio_player: AudioPlayer | None = None,
        waveform_service: WaveformService | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._audio_player = audio_player if audio_player is not None else AudioPlayer()
        self._waveform_service = (
            waveform_service if waveform_service is not None else WaveformService()
        )
        self._db: Db | None = None
        self._data: TuiDataSource | None = None
        self._state: NavState | None = None
        self._indexed: dict[str, int] = {}
        self._library_roots: tuple[Path, ...] = ()
        self._active_pane = "browser"
        self._stage_items: tuple[NavItem, ...] = ()
        self._stage_focused_index = 0
        # Typeahead filter state
        self._filter_active: bool = False
        self._filter_query: str = ""
        self._filter_focused_index: int = 0
        self._last_auditioned_path: Path | None = None
        self._waveform_path: Path | None = None
        self._waveform_data: WaveformData | None = None
        self._waveform_generation = 0
        # Waveform navigation mode state
        self._waveform_nav_active: bool = False
        self._nav_cursor_fraction: float = 0.0
        self._nav_display_width: int = 80

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        _placeholder = NavState.initial(Path("/"), [])
        with Container(id="main-grid"):
            yield TopDisplayWidget(id="top-display")
            yield SessionSummaryWidget(id="session-summary")
            yield BrowserZone(_placeholder, id="browser-zone")
            yield SelectedFilesListWidget(id="selection-list")
        yield Static(
            "  sampleman  ·  j/k move  ·  Tab pane  ·  r root  ·  Return select  ·  a add  ·  d remove  ·  / filter  ·  ? help  ·  q quit",
            id="status-bar",
        )
        yield Footer()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.set_interval(0.2, self._poll_audio)
        self.call_after_refresh(self._initialize)

    def _initialize(self) -> None:
        """Open indexed roots and choose the configured default when present."""
        self._db = _open_db()
        if self._db is None:
            self._set_status("  Config not found. Run `sampleman init`, then `sampleman scan <path>`.")
            return

        self._data = TuiDataSource(self._db)
        roots = self._data.get_library_roots()
        if not roots:
            self._set_status("  No indexed library roots. Run `sampleman scan <path>` or use GUI Add Folder.")
            return

        # Skip stale database roots so opening the TUI never crashes on a
        # folder that has been moved or disconnected.
        self._library_roots = tuple(
            path for row in roots
            if (path := Path(row["path"])).is_dir()
        )
        if not self._library_roots:
            self._set_status("  Indexed library folders are unavailable. Reconnect a folder or scan a new one.")
            return
        configured = normalize_config(load_config(get_config_path())).get(
            "default_library_root"
        )
        preferred = Path(configured) if configured else None
        root_path = (
            preferred if preferred in self._library_roots else self._library_roots[0]
        )
        self._load_root(root_path)

    def on_unmount(self) -> None:
        self._audio_player.close()
        if self._db is not None:
            self._db.close()
            self._db = None

    # ── data helpers ───────────────────────────────────────────────────────

    def _load_root(self, root_path: Path) -> None:
        """Reset Browser navigation to a root while preserving the Stage."""
        self._indexed = self._data.get_indexed_files(root_path)
        selection_ids = self._data.get_selection_ids()
        items = build_items(root_path, self._indexed, selection_ids, root=root_path)
        self._state = NavState.initial(
            root_path, items, selection_ids=selection_ids,
            library_roots=list(self._library_roots),
        )
        self._active_pane = "browser"
        self._filter_active = False
        self._filter_query = ""
        self._filter_focused_index = 0
        self._refresh_ui()

    def _next_library_root(self) -> None:
        """Cycle to the next available indexed root with the r key."""
        if self._state is None or len(self._library_roots) < 2:
            return
        index = self._library_roots.index(self._state.current_root)
        self._load_root(self._library_roots[(index + 1) % len(self._library_roots)])

    def _visible_items(self) -> tuple[NavItem, ...]:
        """Return items filtered by the active typeahead query."""
        if self._state is None:
            return ()
        items = self._state.items
        if not self._filter_query:
            return items
        q = self._filter_query.lower()
        return tuple(it for it in items if q in it.name.lower())

    # ── UI refresh ─────────────────────────────────────────────────────────

    def _refresh_ui(self) -> None:
        """Reconcile Browser, Stage, preview, and status from current state."""
        if self._state is None:
            return

        # Build a filtered view of the current state for the sample list
        filtered = self._visible_items()
        # Keep the rendered cursor and the action target on the same filtered
        # index. The underlying directory cursor is left intact for Escape.
        filtered_index = min(self._filter_focused_index, len(filtered) - 1)
        display_state = NavState(
            library_roots=self._state.library_roots,
            current_root=self._state.current_root,
            current_dir=self._state.current_dir,
            dir_stack=self._state.dir_stack,
            items=filtered,
            focused_index=filtered_index if self._filter_query else self._state.focused_index,
            selection_ids=self._state.selection_ids,
        )

        browser: BrowserZone = self.query_one("#browser-zone", BrowserZone)
        browser.set_class(self._active_pane == "browser", "active-pane")
        browser.sample_list.update(
            display_state,
            empty_label="no matches" if self._filter_query else "empty directory",
        )
        browser.filters_panel.update_filter(self._filter_query)

        # Session summary
        selection_ids = self._data.get_selection_ids()
        total_bytes = self._data.get_selection_total_size()
        destination = self._data.get_active_destination()
        self.query_one("#session-summary", SessionSummaryWidget).update(
            count=len(selection_ids),
            total_bytes=total_bytes,
            destination=destination,
        )

        # Selected files list
        selected_rows = [
            (sid, row) for sid in sorted(selection_ids)
            if (row := self._data.get_sample_details(sid)) is not None
        ]
        # Keep the visible Stage cursor and action target in the same order.
        self._stage_items = tuple(
            NavItem(
                name=row.get("filename", "?"),
                path=self._data.get_sample_path(sid) or Path(row.get("filename", "?")),
                is_dir=False,
                sample_id=sid,
                is_selected=True,
            )
            for sid, row in selected_rows
        )
        self._stage_focused_index = min(
            self._stage_focused_index, max(0, len(self._stage_items) - 1)
        )
        self.query_one("#selection-list", SelectedFilesListWidget).update(
            [row for _sid, row in selected_rows],
            focused_index=self._stage_focused_index,
            active=self._active_pane == "stage",
        )

        # Top display — update with focused item
        focused = self._effective_focused_item()
        details = self._data.get_sample_details(focused.sample_id) if (focused and focused.sample_id) else None
        top_display = self.query_one("#top-display", TopDisplayWidget)
        top_display.update_focus(focused, details)
        self._request_waveform(focused, top_display)

        self._set_status(self._build_status())
        self._audition_focused()

    def _build_status(self) -> str:
        if self._state is None:
            return ""
        item = self._effective_focused_item()
        focused_name = item.name if item else "(empty)"
        sel_count = len(self._state.selection_ids)
        depth = len(self._state.dir_stack)
        back_hint = "  h/← back" if depth > 0 else ""
        filter_hint = f"  /{self._filter_query}" if self._filter_active else ""
        playback = self._audio_player.snapshot()
        audio_hint = f"  |  audio:{playback.status.value}"
        if playback.error:
            audio_hint += f" ({playback.error})"
        pane_hint = "Stage" if self._active_pane == "stage" else "Browser"
        root_hint = (
            f"{self._library_roots.index(self._state.current_root) + 1}/"
            f"{len(self._library_roots)}"
            if self._library_roots else "1/1"
        )
        return (
            f"  {self._state.current_dir}"
            f"{filter_hint}"
            f"  |  {pane_hint} · root {root_hint}"
            f"  |  {focused_name}"
            f"  |  sel:{sel_count}"
            f"{audio_hint}"
            f"  |  j/k move · Tab pane · r root · Space play/pause · Return select · a add · d remove · / filter · ? help · q quit"
            f"{back_hint}"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)

    # ── key handling ───────────────────────────────────────────────────────

    def on_key(self, event) -> None:
        """Route keys to the active pane, filter, playback, or modal action."""
        # Playback is global; filter mode must not consume transport keys.
        if event.key in ("space", "ctrl+space") and self._state is not None:
            event.stop()
            if event.key == "space":
                self._toggle_playback()
            else:
                self._resume_playback()
            return

        # Waveform navigation mode intercepts movement and confirm/exit keys.
        if self._waveform_nav_active:
            nav_keys = {
                "left": "fine_left",
                "h": "fine_left",
                "right": "fine_right",
                "l": "fine_right",
                "shift+left": "coarse_left",
                "shift+right": "coarse_right",
                "home": "home",
                "end": "end",
            }
            if event.key in nav_keys:
                event.stop()
                self._waveform_nav_move(nav_keys[event.key])
                return
            if event.key in ("enter",):
                event.stop()
                self._exit_waveform_nav(seek=True)
                return
            if event.key in ("escape",):
                event.stop()
                self._exit_waveform_nav(seek=False)
                return
            # All other keys (space, j/k, etc.) fall through.

        # In filter mode, capture raw characters before KEYMAP lookup
        if self._filter_active:
            if event.key == "escape":
                self._cancel_filter()
                event.stop()
                return
            if event.key == "backspace":
                self._filter_query = self._filter_query[:-1]
                self._filter_focused_index = 0
                if not self._filter_query:
                    self._cancel_filter()
                else:
                    self._refresh_ui()
                event.stop()
                return
            # Arrows and Return navigate search results; letters remain text so
            # users can type names containing j, k, or l.
            if event.key in ("up", "down", "left", "right", "enter", "tab"):
                pass  # fall through to KEYMAP
            elif event.character and event.character.isprintable():
                self._filter_query += event.character
                self._filter_focused_index = 0
                self._refresh_ui()
                event.stop()
                return
            else:
                return

        if self._state is None:
            return

        # Activate waveform nav mode (w key, outside KEYMAP to keep it exclusive).
        if event.key == "w" and not self._filter_active:
            event.stop()
            self._enter_waveform_nav()
            return

        action = resolve_key(event.key)
        if action is None:
            return

        event.stop()

        if action == "quit":
            self.exit()
        elif action == "move_up":
            if self._active_pane == "stage":
                self._stage_focused_index = max(0, self._stage_focused_index - 1)
            elif self._filter_query:
                self._filter_focused_index = max(0, self._filter_focused_index - 1)
            else:
                self._state = self._state.move_up()
            self._refresh_ui()
        elif action == "move_down":
            if self._active_pane == "stage":
                if self._stage_items:
                    self._stage_focused_index = min(
                        len(self._stage_items) - 1, self._stage_focused_index + 1
                    )
            elif self._filter_query:
                self._filter_focused_index = min(
                    len(self._visible_items()) - 1, self._filter_focused_index + 1
                )
            else:
                self._state = self._state.move_down()
            self._refresh_ui()
        elif action == "go_back":
            if self._active_pane == "stage":
                self._cycle_pane_focus()
            else:
                self._handle_go_back()
        elif action == "enter":
            self._handle_enter()
        elif action == "select_or_descend":
            self._handle_select_or_descend()
        elif action == "add_to_selection":
            self._add_focused()
        elif action == "remove_from_selection":
            self._remove_focused()
        elif action == "activate_filter":
            self._start_filter()
        elif action == "cancel_or_back":
            if self._filter_active:
                self._cancel_filter()
            elif self._active_pane == "stage":
                self._cycle_pane_focus()
            else:
                self._handle_go_back()
        elif action == "show_help":
            self.push_screen(HelpScreen())
        elif action == "command_palette":
            self.action_command_palette()
        elif action == "cycle_pane_focus":
            self._cycle_pane_focus()
        elif action == "next_library_root":
            self._next_library_root()
        elif action == "toggle_playback":
            self._toggle_playback()
        elif action == "resume_playback":
            self._resume_playback()

    # ── playback ──────────────────────────────────────────────────────────

    def _effective_focused_item(self) -> NavItem | None:
        """Return the row actually highlighted in the filtered or directory view."""
        if self._active_pane == "stage":
            return (
                self._stage_items[self._stage_focused_index]
                if self._stage_items else None
            )
        if self._filter_query:
            visible = self._visible_items()
            return visible[self._filter_focused_index] if visible else None
        return self._state.focused_item if self._state is not None else None

    def _audition_focused(self) -> None:
        item = self._effective_focused_item()
        if item is None or item.is_dir:
            self._last_auditioned_path = None
            return
        if item.path == self._last_auditioned_path:
            return
        self._last_auditioned_path = item.path
        self._audio_player.play(item.path)

    def _toggle_playback(self) -> None:
        """Pause or resume the current sample, starting the focus if idle."""
        playback = self._audio_player.snapshot()
        if playback.status in (PlaybackStatus.PLAYING, PlaybackStatus.LOADING):
            self._audio_player.pause()
            self._set_status(self._build_status())
            return
        if playback.status is PlaybackStatus.PAUSED and playback.path is not None:
            self._audio_player.play(playback.path)
            self._set_status(self._build_status())
            return
        item = self._effective_focused_item()
        if item is not None and not item.is_dir:
            self._last_auditioned_path = item.path
            self._audio_player.play_from_start(item.path)
        self._set_status(self._build_status())

    def _resume_playback(self) -> None:
        playback = self._audio_player.snapshot()
        if playback.status is PlaybackStatus.PAUSED and playback.path is not None:
            self._audio_player.play(playback.path)
        self._set_status(self._build_status())

    def _poll_audio(self) -> None:
        if self._state is not None:
            playback = self._audio_player.snapshot()
            progress = 0.0
            if playback.duration_seconds and playback.duration_seconds > 0:
                progress = playback.position_seconds / playback.duration_seconds
            self.query_one("#top-display", TopDisplayWidget).set_playback_progress(
                playback.path,
                progress,
            )
            self._set_status(self._build_status())

    # ── waveform navigation mode ───────────────────────────────────────────

    def _enter_waveform_nav(self) -> None:
        """Activate waveform nav mode, initialising cursor at current playback position."""
        if self._waveform_data is None:
            return  # nothing to navigate
        snapshot = self._audio_player.snapshot()
        duration = snapshot.duration_seconds or 0.0
        if duration > 0:
            self._nav_cursor_fraction = max(0.0, min(1.0, snapshot.position_seconds / duration))
        else:
            self._nav_cursor_fraction = 0.0
        self._waveform_nav_active = True
        self._sync_nav_cursor()

    def _exit_waveform_nav(self, *, seek: bool) -> None:
        """Exit waveform nav mode, optionally seeking to the cursor position."""
        if seek:
            snapshot = self._audio_player.snapshot()
            duration = snapshot.duration_seconds or 0.0
            self._audio_player.seek(self._nav_cursor_fraction * duration)
        self._waveform_nav_active = False
        self._sync_nav_cursor()

    def _waveform_nav_move(self, direction: str) -> None:
        """Move the waveform nav cursor in *direction*."""
        braille_cols = max(1, self._nav_display_width // 2)
        fine = 1.0 / braille_cols
        coarse = fine * 10
        if direction == "fine_left":
            self._nav_cursor_fraction = max(0.0, self._nav_cursor_fraction - fine)
        elif direction == "fine_right":
            self._nav_cursor_fraction = min(1.0, self._nav_cursor_fraction + fine)
        elif direction == "coarse_left":
            self._nav_cursor_fraction = max(0.0, self._nav_cursor_fraction - coarse)
        elif direction == "coarse_right":
            self._nav_cursor_fraction = min(1.0, self._nav_cursor_fraction + coarse)
        elif direction == "home":
            self._nav_cursor_fraction = 0.0
        elif direction == "end":
            self._nav_cursor_fraction = 1.0
        self._sync_nav_cursor()

    def _sync_nav_cursor(self) -> None:
        """Push the current nav cursor (or None when inactive) to the top display."""
        try:
            top_display = self.query_one("#top-display", TopDisplayWidget)
        except Exception:  # noqa: BLE001 - widget may not be mounted in unit tests
            return
        fraction = self._nav_cursor_fraction if self._waveform_nav_active else None
        top_display.set_nav_cursor(fraction)

    # ── waveform ──────────────────────────────────────────────────────────

    def _request_waveform(
        self,
        item: NavItem | None,
        top_display: TopDisplayWidget,
    ) -> None:
        if item is None or item.is_dir:
            self._waveform_generation += 1
            self._waveform_path = None
            self._waveform_data = None
            return

        if item.path == self._waveform_path:
            if self._waveform_data is not None:
                top_display.set_waveform_data(self._waveform_data)
            else:
                top_display.set_waveform_loading(item.path)
            return

        self._waveform_generation += 1
        generation = self._waveform_generation
        self._waveform_path = item.path
        self._waveform_data = None
        top_display.set_waveform_loading(item.path)
        self.run_worker(
            self._load_waveform(item.path, generation),
            name="waveform",
            group="waveform",
            exclusive=True,
            exit_on_error=False,
        )

    async def _load_waveform(self, path: Path, generation: int) -> None:
        try:
            data = await asyncio.to_thread(self._waveform_service.load, path)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 - render domain/backend errors
            if generation == self._waveform_generation and path == self._waveform_path:
                self.query_one("#top-display", TopDisplayWidget).set_waveform_error(
                    path,
                    str(exc) or exc.__class__.__name__,
                )
            return

        if generation != self._waveform_generation or path != self._waveform_path:
            return
        self._waveform_data = data
        self.query_one("#top-display", TopDisplayWidget).set_waveform_data(data)

    # ── filter ─────────────────────────────────────────────────────────────

    def _start_filter(self) -> None:
        """Start a fresh typeahead query in the current directory."""
        self._active_pane = "browser"
        self._filter_active = True
        self._filter_query = ""
        self._filter_focused_index = 0
        self._refresh_ui()

    def _cycle_pane_focus(self) -> None:
        """Move keyboard actions between Browser and the persistent Stage."""
        self._active_pane = "stage" if self._active_pane == "browser" else "browser"
        if self._active_pane == "stage":
            # Search typing must stop when Tab leaves Browser, while the
            # underlying directory cursor remains available on return.
            self._filter_active = False
            self._filter_query = ""
            self._filter_focused_index = 0
        self._refresh_ui()

    def _cancel_filter(self) -> None:
        """Restore the directory cursor and leave typeahead mode."""
        self._filter_active = False
        self._filter_query = ""
        self._filter_focused_index = 0
        self._refresh_ui()

    # ── navigation ─────────────────────────────────────────────────────────

    def _handle_enter(self) -> None:
        # In filter mode, navigate within filtered results
        item = self._effective_focused_item()

        if item is None:
            return

        if item.is_dir:
            selection_ids = self._data.get_selection_ids()
            new_items = build_items(
                item.path, self._indexed, selection_ids, root=self._state.current_root
            )
            self._state = self._state.enter_dir(item.path, new_items)
            self._cancel_filter()
        else:
            self.push_screen(
                ActionPane(item, item.is_selected),
                callback=self._on_action_pane_dismissed,
            )

    def _handle_select_or_descend(self) -> None:
        """Return key: descend into a directory or toggle file selection.

        Digitakt-inspired: the Return key is a "soft select" that either enters a
        directory or adds/removes the focused file from the persistent selection buffer.
        The l/→ key keeps its existing behavior (open the ActionPane modal).
        """
        item = self._effective_focused_item()

        if item is None:
            return

        if self._active_pane == "stage":
            self._remove_focused()
            return

        if item.is_dir:
            selection_ids = self._data.get_selection_ids()
            new_items = build_items(
                item.path, self._indexed, selection_ids, root=self._state.current_root
            )
            self._state = self._state.enter_dir(item.path, new_items)
            self._cancel_filter()
        else:
            if item.sample_id is None:
                return
            # Toggle: add if not yet selected, remove if already selected
            if item.is_selected:
                self._data.remove_from_selection(item.sample_id)
            else:
                self._data.add_to_selection(item.sample_id)
            selection_ids = self._data.get_selection_ids()
            self._state = self._state.with_selection(selection_ids)
            self._refresh_ui()

    def _handle_go_back(self) -> None:
        if not self._state.dir_stack:
            return
        parent_dir = self._state.dir_stack[-1]
        came_from = self._state.current_dir.name
        selection_ids = self._data.get_selection_ids()
        parent_items = build_items(
            parent_dir, self._indexed, selection_ids, root=self._state.current_root
        )
        self._state = self._state.go_back(parent_items, restore_focus_name=came_from)
        self._refresh_ui()

    def _add_focused(self) -> None:
        """Add the currently visible row, including a non-first search hit."""
        if self._active_pane == "stage":
            return
        item = self._effective_focused_item()
        if item is None or item.sample_id is None:
            return
        self._data.add_to_selection(item.sample_id)
        selection_ids = self._data.get_selection_ids()
        self._state = self._state.with_selection(selection_ids)
        self._refresh_ui()

    def _remove_focused(self) -> None:
        """Remove the currently visible row from the persistent selection."""
        item = self._effective_focused_item()
        if item is None or item.sample_id is None:
            return
        self._data.remove_from_selection(item.sample_id)
        selection_ids = self._data.get_selection_ids()
        self._state = self._state.with_selection(selection_ids)
        self._refresh_ui()

    def _on_action_pane_dismissed(self, result: str | None) -> None:
        if result == "add":
            self._add_focused()
        elif result == "remove":
            self._remove_focused()
