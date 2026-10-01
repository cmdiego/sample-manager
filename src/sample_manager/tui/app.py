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
        # Typeahead filter state
        self._filter_active: bool = False
        self._filter_query: str = ""
        self._last_auditioned_path: Path | None = None
        self._waveform_path: Path | None = None
        self._waveform_data: WaveformData | None = None
        self._waveform_generation = 0

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        _placeholder = NavState.initial(Path("/"), [])
        with Container(id="main-grid"):
            yield TopDisplayWidget(id="top-display")
            yield SessionSummaryWidget(id="session-summary")
            yield BrowserZone(_placeholder, id="browser-zone")
            yield SelectedFilesListWidget(id="selection-list")
        yield Static(
            "  sampleman  ·  j/k move  ·  Return select  ·  l enter  ·  h back  ·  a add  ·  d remove  ·  / filter  ·  ? help  ·  q quit",
            id="status-bar",
        )
        yield Footer()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.set_interval(0.2, self._poll_audio)
        self.call_after_refresh(self._initialize)

    def _initialize(self) -> None:
        self._db = _open_db()
        if self._db is None:
            self._set_status("  Config not found. Run `sampleman init`, then `sampleman config add-root <path>`.")
            return

        self._data = TuiDataSource(self._db)
        roots = self._data.get_library_roots()
        if not roots:
            self._set_status("  No library roots configured. Run `sampleman config add-root <path>`.")
            return

        root_path = Path(roots[0]["path"])
        self._load_root(root_path)

    def on_unmount(self) -> None:
        self._audio_player.close()
        if self._db is not None:
            self._db.close()
            self._db = None

    # ── data helpers ───────────────────────────────────────────────────────

    def _load_root(self, root_path: Path) -> None:
        self._indexed = self._data.get_indexed_files(root_path)
        selection_ids = self._data.get_selection_ids()
        items = build_items(root_path, self._indexed, selection_ids)
        self._state = NavState.initial(root_path, items, selection_ids=selection_ids)
        self._refresh_ui()

    def _visible_items(self) -> tuple[NavItem, ...]:
        """Return items filtered by the active typeahead query."""
        if self._state is None:
            return ()
        items = self._state.items
        if not self._filter_query:
            return items
        q = self._filter_query.lower()
        return tuple(it for it in items if it.name.lower().startswith(q))

    # ── UI refresh ─────────────────────────────────────────────────────────

    def _refresh_ui(self) -> None:
        if self._state is None:
            return

        # Build a filtered view of the current state for the sample list
        filtered = self._visible_items()
        display_state = NavState(
            library_roots=self._state.library_roots,
            current_root=self._state.current_root,
            current_dir=self._state.current_dir,
            dir_stack=self._state.dir_stack,
            items=filtered,
            focused_index=0 if filtered else -1,
            selection_ids=self._state.selection_ids,
        )

        browser: BrowserZone = self.query_one("#browser-zone", BrowserZone)
        browser.sample_list.update(display_state)
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
        sel_items = [
            row for sid in sorted(selection_ids)
            if (row := self._data.get_sample_details(sid)) is not None
        ]
        self.query_one("#selection-list", SelectedFilesListWidget).update(sel_items)

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
        item = self._state.focused_item
        focused_name = item.name if item else "(empty)"
        sel_count = len(self._state.selection_ids)
        depth = len(self._state.dir_stack)
        back_hint = "  h/← back" if depth > 0 else ""
        filter_hint = f"  /{self._filter_query}" if self._filter_active else ""
        playback = self._audio_player.snapshot()
        audio_hint = f"  |  audio:{playback.status.value}"
        if playback.error:
            audio_hint += f" ({playback.error})"
        return (
            f"  {self._state.current_dir}"
            f"{filter_hint}"
            f"  |  {focused_name}"
            f"  |  sel:{sel_count}"
            f"{audio_hint}"
            f"  |  j/k move · Space play/pause · Ctrl+Space resume · Return select · l enter · a add · d remove · / filter · ? help · q quit"
            f"{back_hint}"
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)

    # ── key handling ───────────────────────────────────────────────────────

    def on_key(self, event) -> None:
        # Playback is global; filter mode must not consume transport keys.
        if event.key in ("space", "ctrl+space") and self._state is not None:
            event.stop()
            if event.key == "space":
                self._toggle_playback()
            else:
                self._resume_playback()
            return

        # In filter mode, capture raw characters before KEYMAP lookup
        if self._filter_active:
            if event.key == "escape":
                self._cancel_filter()
                event.stop()
                return
            if event.key == "backspace":
                self._filter_query = self._filter_query[:-1]
                if not self._filter_query:
                    self._cancel_filter()
                else:
                    self._refresh_ui()
                event.stop()
                return
            if event.character and event.character.isprintable():
                self._filter_query += event.character
                self._refresh_ui()
                event.stop()
                return
            # Allow navigation keys through even in filter mode
            if event.key in ("j", "k", "up", "down", "l", "right", "enter"):
                pass  # fall through to KEYMAP
            else:
                return

        if self._state is None:
            return

        action = resolve_key(event.key)
        if action is None:
            return

        event.stop()

        if action == "quit":
            self.exit()
        elif action == "move_up":
            self._state = self._state.move_up()
            self._refresh_ui()
        elif action == "move_down":
            self._state = self._state.move_down()
            self._refresh_ui()
        elif action == "go_back":
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
            else:
                self._handle_go_back()
        elif action == "show_help":
            self.push_screen(HelpScreen())
        elif action == "command_palette":
            self.action_command_palette()
        elif action == "cycle_pane_focus":
            pass  # future: tab between browser and selection list
        elif action == "toggle_playback":
            self._toggle_playback()
        elif action == "resume_playback":
            self._resume_playback()

    # ── playback ──────────────────────────────────────────────────────────

    def _effective_focused_item(self) -> NavItem | None:
        if self._filter_query:
            visible = self._visible_items()
            return visible[0] if visible else None
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
        playback = self._audio_player.snapshot()
        if playback.status in (PlaybackStatus.PLAYING, PlaybackStatus.LOADING):
            self._audio_player.pause()
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
        self._filter_active = True
        self._filter_query = ""
        self._refresh_ui()

    def _cancel_filter(self) -> None:
        self._filter_active = False
        self._filter_query = ""
        self._refresh_ui()

    # ── navigation ─────────────────────────────────────────────────────────

    def _handle_enter(self) -> None:
        # In filter mode, navigate within filtered results
        item = self._state.focused_item
        if self._filter_query:
            # Find what's actually visible and use its focused item
            visible = self._visible_items()
            if not visible:
                return
            item = visible[0]

        if item is None:
            return

        if item.is_dir:
            selection_ids = self._data.get_selection_ids()
            new_items = build_items(item.path, self._indexed, selection_ids)
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
        item = self._state.focused_item
        if self._filter_query:
            # In filter mode, act on the first visible item
            visible = self._visible_items()
            if not visible:
                return
            item = visible[0]

        if item is None:
            return

        if item.is_dir:
            selection_ids = self._data.get_selection_ids()
            new_items = build_items(item.path, self._indexed, selection_ids)
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
        parent_items = build_items(parent_dir, self._indexed, selection_ids)
        self._state = self._state.go_back(parent_items, restore_focus_name=came_from)
        self._refresh_ui()

    def _add_focused(self) -> None:
        item = self._state.focused_item
        if item is None or item.sample_id is None:
            return
        self._data.add_to_selection(item.sample_id)
        selection_ids = self._data.get_selection_ids()
        self._state = self._state.with_selection(selection_ids)
        self._refresh_ui()

    def _remove_focused(self) -> None:
        item = self._state.focused_item
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
