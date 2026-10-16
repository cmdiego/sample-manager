"""Sample Manager TUI — main Textual application."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Callable

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Container
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

from ..audio import AudioPlayer, PlaybackStatus, WaveformData, WaveformService
from ..audio.decode_cache import shared_decode_cache
from ..config import (
    add_library_root, ensure_config_exists, get_config_path, load_config,
    normalize_config, save_config,
)
from ..db import Db
from ..migrations import apply_migrations
from .data import TuiDataSource
from .keybindings import WAVEFORM_KEYMAP, resolve_key
from .settings import (
    TuiPreferences, build_tui_player, load_tui_preferences, save_tui_preferences,
)
from .widgets.help_screen import HelpScreen
from .widgets.commands_screen import CommandsScreen
from .widgets.settings_screen import SettingsScreen
from .widgets.tags_screen import TagsScreen
from .nav_state import NavState, NavItem, build_items
from .widgets.action_pane import ActionPane
from .widgets.add_library_screen import AddLibraryScreen
from .widgets.browser_zone import BrowserZone
from .widgets.file_tree import SampleListWidget
from .widgets.selection_list import SelectedFilesListWidget
from .widgets.session_summary import SessionSummaryWidget
from .widgets.top_display import TopDisplayWidget


# Rows on each side of the cursor decoded ahead of time.
PREFETCH_NEIGHBORS = 3


def _open_db(config_path: Path | None = None) -> Db | None:
    """Open the configured shared database when explicit setup exists."""
    config_path = config_path if config_path is not None else get_config_path()
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
    BINDINGS = [
        Binding("f1", "show_commands", "Commands", priority=True),
        Binding("f2", "show_settings", "Settings", priority=True),
        Binding("f4", "add_library", "Add Folder", priority=True),
        Binding("f5", "rescan_library", "Rescan", priority=True),
        Binding("f6", "edit_tags", "Tags", priority=True),
    ]

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
        preferences: TuiPreferences | None = None,
        player_factory: Callable[[TuiPreferences], AudioPlayer] = build_tui_player,
        config_path: Path | None = None,
        device_provider=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._preferences = preferences if preferences is not None else TuiPreferences()
        self._preferences_supplied = preferences is not None
        self._player_factory = player_factory
        self._config_path = config_path
        self._device_provider = device_provider
        self._audio_player = (
            audio_player if audio_player is not None else player_factory(self._preferences)
        )
        self._waveform_service = (
            waveform_service if waveform_service is not None
            else WaveformService(decoder=shared_decode_cache())
        )
        self._db: Db | None = None
        self._data: TuiDataSource | None = None
        self._state: NavState | None = None
        self._indexed: dict[str, int] = {}
        self._library_roots: tuple[Path, ...] = ()
        self._active_pane = "browser"
        self._stage_items: tuple[NavItem, ...] = ()
        self._stage_focused_index = 0
        self._scan_in_progress = False
        self._scan_message = ""
        self._audio_poll_timer = None
        # Typeahead filter state
        self._filter_active: bool = False
        self._filter_query: str = ""
        self._filter_focused_index: int = 0
        self._filter_results: tuple[NavItem, ...] = ()
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
            "  \\ commands · F2 settings · F4 add folder · / search · ? help · q quit",
            id="status-bar",
            markup=False,
        )
        yield Footer()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._audio_poll_timer = self.set_interval(0.2, self._poll_audio)
        self.call_after_refresh(self._initialize)

    def _initialize(self) -> None:
        """Open indexed roots and choose the configured default when present."""
        if not self._preferences_supplied:
            self._apply_preferences(load_tui_preferences(self._config_path), persist=False)
        self._db = _open_db(self._config_path) if self._config_path else _open_db()
        if self._db is None:
            self._set_status("  F4 Add Folder to start your sample library · F2 Settings · q Quit")
            return

        self._data = TuiDataSource(self._db)
        roots = self._data.get_library_roots()
        if not roots:
            self._set_status("  No sample libraries yet. Press F4 Add Folder to index your samples.")
            return

        # Skip stale database roots so opening the TUI never crashes on a
        # folder that has been moved or disconnected.
        self._library_roots = tuple(
            path for row in roots
            if (path := Path(row["path"])).is_dir()
        )
        if not self._library_roots:
            self._set_status("  Library folders are unavailable. Reconnect them or press F4 Add Folder.")
            return
        configured = normalize_config(load_config(self._config_path or get_config_path())).get(
            "default_library_root"
        )
        preferred = Path(configured) if configured else None
        root_path = (
            preferred if preferred in self._library_roots else self._library_roots[0]
        )
        self._load_root(root_path)

    def on_unmount(self) -> None:
        if self._audio_poll_timer is not None:
            self._audio_poll_timer.stop()
        self._state = None
        self._audio_player.close()
        if self._db is not None:
            self._db.close()
            self._db = None

    # ── settings ───────────────────────────────────────────────────────────

    def get_system_commands(self, screen):
        """Make Settings searchable from Textual's existing command palette."""
        yield from super().get_system_commands(screen)
        yield SystemCommand("Settings", "Audio output and auto-audition preferences", self.action_show_settings)
        yield SystemCommand("Add Folder", "Index a sample folder and select its library", self.action_add_library)
        yield SystemCommand("Rescan Library", "Index added, changed, and removed samples", self.action_rescan_library)
        yield SystemCommand("Sample Tags", "Add or remove tags for the focused sample", self.action_edit_tags)

    def action_show_settings(self) -> None:
        """Open preferences from F2, including before a library is configured."""
        if isinstance(self.screen, ModalScreen):
            return
        if self._waveform_nav_active:
            self._exit_waveform_nav(seek=False)
        kwargs = {"device_provider": self._device_provider} if self._device_provider else {}
        self.push_screen(SettingsScreen(
            self._preferences,
            on_save=self._save_preferences,
            config_path=self._config_path or get_config_path(),
            database_path=str(self._db.path) if self._db is not None else "Not connected",
            library_path=str(self._state.current_root) if self._state else "No library selected",
            **kwargs,
        ))

    def _save_preferences(self, preferences: TuiPreferences) -> None:
        """Save explicitly and apply the choices without auditioning a sample."""
        self._apply_preferences(preferences, persist=True)
        self._refresh_ui(audition=False)
        self.notify("Settings saved")

    def _apply_preferences(self, preferences: TuiPreferences, *, persist: bool) -> None:
        """Replace output only when necessary, and retain it if saving fails."""
        replacement = (
            self._player_factory(preferences)
            if preferences.audio_output != self._preferences.audio_output else None
        )
        try:
            if persist:
                save_tui_preferences(preferences, self._config_path)
        except Exception:
            if replacement is not None:
                replacement.close()
            raise
        if replacement is not None:
            old_player = self._audio_player
            self._audio_player = replacement
            old_player.close()
            self._last_auditioned_path = None
        self._preferences = preferences

    # ── background library scanning ────────────────────────────────────────

    def action_add_library(self) -> None:
        """Collect a new root even when the TUI has no configuration yet."""
        if isinstance(self.screen, ModalScreen):
            return
        if self._scan_in_progress:
            self.notify("Wait for the current library scan to finish")
            return
        self.push_screen(AddLibraryScreen(), callback=self._on_library_chosen)

    def _on_library_chosen(self, root: Path | None) -> None:
        """Initialize missing storage only after a valid path is submitted."""
        if root is None:
            return
        try:
            if self._data is None:
                from ..profiles import create_example_profiles, get_profiles_dir

                config_path, _created = ensure_config_exists(self._config_path)
                create_example_profiles(get_profiles_dir(load_config(config_path)))
                self._db = _open_db(config_path)
                if self._db is None:
                    raise ValueError("Set db_path in configuration before adding a folder")
                self._data = TuiDataSource(self._db)
            self._start_library_scan(root, activate=True)
        except Exception as exc:  # noqa: BLE001 - show configuration/storage errors in the TUI
            self.notify(f"Could not add folder: {exc}", severity="error", timeout=8)

    def action_rescan_library(self) -> None:
        """Start one background scan while leaving navigation responsive."""
        if isinstance(self.screen, ModalScreen):
            return
        if self._state is None or self._data is None:
            self.notify("No library selected. Press F4 Add Folder first.")
            return
        self._start_library_scan(self._state.current_root)

    def _start_library_scan(self, root: Path, *, activate: bool = False) -> None:
        """Share one background scanner between adding and rescanning folders."""
        if self._scan_in_progress:
            self.notify("A library scan is already running")
            return
        self._scan_in_progress = True
        self._scan_message = f"Scanning {root.name}…"
        self._set_status(self._build_status() if self._state else self._scan_message)
        self.run_worker(
            self._rescan_library(root, activate=activate), name="library-rescan", group="library-rescan",
            exit_on_error=False,
        )

    async def _rescan_library(self, root: Path, *, activate: bool = False) -> None:
        """Run blocking I/O off-thread and refresh the TUI on its event loop."""
        try:
            result = await asyncio.to_thread(self._data.scan_directory, root)
            if activate:
                self._activate_added_library(root)
            else:
                self._refresh_after_scan(root)
        except asyncio.CancelledError:
            return  # Shutdown discards UI updates; the independent scan can finish.
        except Exception as exc:  # noqa: BLE001 - leave navigation available on failure
            self._scan_message = f"Scan failed: {exc}"
            self.notify(self._scan_message, severity="error", timeout=8)
        else:
            self._scan_message = (
                f"Scanned {root.name}: {result.inserted} new, "
                f"{result.updated} updated, {result.pruned} removed"
            )
            self.notify(self._scan_message, timeout=8)
        finally:
            self._scan_in_progress = False
            if self.is_running:
                self._set_status(self._build_status() if self._state else self._scan_message)

    def _activate_added_library(self, root: Path) -> None:
        """Select a completed scan and persist the same root for the next launch."""
        self._library_roots = tuple(
            path for row in self._data.get_library_roots()
            if (path := Path(row["path"])).is_dir()
        )
        if root not in self._library_roots:
            raise ValueError("The sample folder disappeared while scanning")
        self._load_root(root)
        try:
            config_path = self._config_path or get_config_path()
            config, _message = add_library_root(load_config(config_path), str(root), set_as_default=True)
            save_config(config, config_path)
        except Exception as exc:  # noqa: BLE001 - indexing already succeeded; retain its usable view
            self.notify(f"Folder indexed, but startup preference could not be saved: {exc}", severity="warning", timeout=8)

    def _refresh_after_scan(self, scanned_root: Path) -> None:
        """Preserve browsing/search focus and refresh Stage after index changes."""
        if self._state is None:
            return
        selected = self._data.get_selection_ids()
        state = self._state.with_selection(selected)
        if state.current_root == scanned_root:
            self._indexed = self._data.get_indexed_files(scanned_root)
            directory = state.current_dir if state.current_dir.is_dir() else scanned_root
            items = build_items(directory, self._indexed, selected, root=scanned_root)
            focused_path = state.focused_item.path if state.focused_item else None
            focused_index = next(
                (index for index, item in enumerate(items) if item.path == focused_path),
                min(max(0, state.focused_index), len(items) - 1),
            )
            self._state = replace(
                state, current_dir=directory, items=tuple(items), focused_index=focused_index,
                dir_stack=state.dir_stack if directory == state.current_dir else (),
            )
            self._reload_filter_results()
        else:
            # The user may have switched roots during scanning. Refresh Stage
            # membership without moving their current browser to the old root.
            self._state = state
        self._refresh_ui(audition=False)

    # ── sample tagging ─────────────────────────────────────────────────────

    def action_edit_tags(self, sample_id: int | None = None) -> None:
        """Open tags for the focused Browser/Stage sample, capturing its ID."""
        if isinstance(self.screen, ModalScreen) or self._data is None:
            return
        if sample_id is None:
            item = self._effective_focused_item()
            sample_id = item.sample_id if item is not None else None
        if sample_id is None:
            self.notify("Focus an indexed sample to edit its tags")
            return
        try:
            details = self._data.get_sample_details(sample_id)
            if details is None:
                raise ValueError("This sample is no longer indexed")
            tags = self._data.get_sample_tags(sample_id)
        except Exception as exc:  # noqa: BLE001 - stale samples leave navigation available
            self.notify(f"Could not open tags: {exc}", severity="error")
            return
        self.push_screen(TagsScreen(
            details["filename"], tags,
            on_add=lambda text: self._change_sample_tag(sample_id, text),
            on_remove=lambda text: self._change_sample_tag(sample_id, text, remove=True),
        ))

    def _change_sample_tag(self, sample_id: int, text: str, *, remove: bool = False) -> list[dict]:
        """Persist one attachment edit and update visible metadata/search hits."""
        if remove:
            self._data.remove_sample_tag(sample_id, text)
        else:
            self._data.add_sample_tag(sample_id, text)
        self._reload_filter_results()
        self._refresh_ui(audition=False)
        return self._data.get_sample_tags(sample_id)

    def _reload_filter_results(self) -> None:
        """Rerun an active query after index/tag edits, keeping a surviving hit."""
        if not self._filter_query or self._state is None:
            return
        previous = (
            self._filter_results[self._filter_focused_index].path
            if 0 <= self._filter_focused_index < len(self._filter_results) else None
        )
        self._filter_results = self._data.search_samples(self._state.current_root, self._filter_query)
        self._filter_focused_index = next(
            (index for index, item in enumerate(self._filter_results) if item.path == previous),
            max(0, min(self._filter_focused_index, len(self._filter_results) - 1)),
        )

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
        self._filter_results = ()
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
        return self._filter_results if self._filter_query else self._state.items

    def _update_filter_query(self, query: str) -> None:
        """Query once per edit, preserving the directory cursor for Escape."""
        self._filter_query = query
        self._filter_focused_index = 0
        self._filter_results = (
            self._data.search_samples(self._state.current_root, query)
            if query and self._state is not None and self._data is not None else ()
        )
        # Typing should not audition every intermediate search prefix.
        self._refresh_ui(audition=False)

    # ── UI refresh ─────────────────────────────────────────────────────────

    def _refresh_ui(self, *, audition: bool = True) -> None:
        """Reconcile Browser, Stage, preview, and status from current state."""
        if self._state is None:
            return

        # Build a filtered view of the current state for the sample list
        selection_ids = self._data.get_selection_ids()
        self._filter_results = tuple(
            replace(item, is_selected=item.sample_id in selection_ids)
            for item in self._filter_results
        )
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
        browser.filters_panel.update_filter(
            self._filter_query, active=self._filter_active,
            count=len(filtered) if self._filter_query else None,
        )

        # Session summary
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
        if audition:
            self._audition_focused()
        self._prefetch_neighbors()

    def _prefetch_neighbors(self) -> None:
        """Decode the rows around the cursor so the next audition starts from RAM."""
        prefetch = getattr(self._audio_player, "prefetch", None)
        if prefetch is None or self._preferences.audio_output == "disabled":
            return
        if self._active_pane == "stage":
            items, index = self._stage_items, self._stage_focused_index
        else:
            items = self._visible_items()
            index = (
                self._filter_focused_index if self._filter_query
                else (self._state.focused_index if self._state is not None else -1)
            )
        if index < 0 or not items:
            return
        nearest_first = []
        for distance in range(1, PREFETCH_NEIGHBORS + 1):
            for position in (index + distance, index - distance):
                if 0 <= position < len(items) and not items[position].is_dir:
                    nearest_first.append(items[position].path)
        prefetch(nearest_first)

    def _build_status(self) -> str:
        if self._state is None:
            return ""
        item = self._effective_focused_item()
        focused_name = item.name if item else "(empty)"
        sel_count = len(self._state.selection_ids)
        depth = len(self._state.dir_stack)
        back_hint = "  h/← back" if depth > 0 else ""
        filter_hint = f"  Search: {self._filter_query}" if self._filter_active else ""
        playback = self._audio_player.snapshot()
        audio_hint = (
            "  |  audio:disabled" if self._preferences.audio_output == "disabled"
            else f"  |  audio:{playback.status.value}"
        )
        if playback.error:
            audio_hint += f" ({playback.error})"
        pane_hint = "Stage" if self._active_pane == "stage" else "Browser"
        root_hint = (
            f"{self._library_roots.index(self._state.current_root) + 1}/"
            f"{len(self._library_roots)}"
            if self._library_roots else "1/1"
        )
        return (
            f"  {self._scan_message + ' | ' if self._scan_message else ''}"
            f"\\ commands · F2 settings · F5 rescan | {self._state.current_dir}"
            f"{filter_hint}"
            f"  |  {pane_hint} · root {root_hint}"
            f"  |  {focused_name}"
            f"  |  sel:{sel_count}"
            f"{audio_hint}"
            f"  |  j/k move · Tab pane · r root · Space play/pause · Return select · a add · d remove · / filter · ? help · q quit"
            f"{back_hint}"
        )

    def _set_status(self, text: str) -> None:
        """Ignore late worker/timer updates after the status view is removed."""
        try:
            self.query_one("#status-bar", Static).update(text)
        except NoMatches:
            return

    # ── key handling ───────────────────────────────────────────────────────

    def action_show_commands(self) -> None:
        """Open leader discovery without changing the underlying interaction mode."""
        if isinstance(self.screen, HelpScreen):
            # These are two views of the same help flow; replace rather than
            # stacking them so Escape always returns to the original browser.
            self.pop_screen()
        if isinstance(self.screen, CommandsScreen):
            self.screen.dismiss(None)
        elif not isinstance(self.screen, ModalScreen):
            self.push_screen(CommandsScreen(self._command_unavailable), self._on_command_chosen)

    def _on_command_chosen(self, action: str | None) -> None:
        """Execute after modal dismissal, rechecking any background state changes."""
        if action is None:
            return
        reason = self._command_unavailable(action)
        if reason:
            self.notify(reason, title="Command unavailable")
        else:
            self._execute_command(action)

    def _command_unavailable(self, action: str) -> str | None:
        """Explain actionable prerequisites while keeping every command discoverable."""
        if action in ("add_library", "rescan_library") and self._scan_in_progress:
            return "A library scan is already running."
        if action in ("quit", "show_help", "show_commands", "command_palette", "show_settings", "add_library"):
            return None
        if self._state is None:
            return "Add a sample folder first (F4)."
        if action == "next_library_root" and len(self._library_roots) < 2:
            return "Add another library folder first (F4)."
        if action == "waveform_nav_enter":
            if self._filter_active:
                return "Leave search first (Esc)."
            if self._waveform_data is None:
                return "Choose a sample and wait for its waveform."
        if action in WAVEFORM_KEYMAP.values() and not self._waveform_nav_active:
            return "Enter waveform navigation first (w)."
        item = self._effective_focused_item()
        if action in ("enter", "select_or_descend") and item is None:
            return "Choose an item in Browser or Stage first."
        if action in ("add_to_selection", "remove_from_selection", "edit_tags"):
            if item is None or item.is_dir or item.sample_id is None:
                return "Choose an indexed sample first."
            if action == "add_to_selection" and item.is_selected:
                return "This sample is already in Stage."
            if action == "remove_from_selection" and not item.is_selected:
                return "This sample is not in Stage."
        if action in ("toggle_playback", "resume_playback"):
            if self._preferences.audio_output == "disabled":
                return "Enable audio output in Settings (F2)."
            playback = self._audio_player.snapshot()
            if action == "resume_playback" and (
                playback.status is not PlaybackStatus.PAUSED or playback.path is None
            ):
                return "No paused sample to resume."
            if action == "toggle_playback" and playback.status not in (
                PlaybackStatus.PLAYING, PlaybackStatus.LOADING, PlaybackStatus.PAUSED,
            ) and (item is None or item.is_dir):
                return "Choose a sample to play first."
        return None

    def on_key(self, event) -> None:
        """Route keys to the active pane, filter, playback, or modal action."""
        # Controls and dialogs own their input. Unhandled keys must not mutate
        # the hidden browser or quit the app while a modal is open.
        if len(self.screen_stack) > 1:
            if event.key == "backslash" and isinstance(self.screen, HelpScreen):
                event.stop()
                self.action_show_commands()
            return
        # The leader also works during search; dismissing it preserves the query.
        # Real dialog Inputs still own backslashes (paths/tag names) above.
        if event.key == "backslash":
            event.stop()
            self.action_show_commands()
            return
        # Playback is global; filter mode must not consume transport keys.
        if event.key in ("space", "ctrl+space") and self._state is not None:
            event.stop()
            self._execute_command(resolve_key(event.key))
            return

        # Waveform navigation mode intercepts movement and confirm/exit keys.
        if self._waveform_nav_active:
            if event.key in WAVEFORM_KEYMAP:
                event.stop()
                self._execute_command(WAVEFORM_KEYMAP[event.key])
                return
            # All other keys (space, j/k, etc.) fall through.

        # In filter mode, capture raw characters before KEYMAP lookup
        if self._filter_active:
            if event.key == "escape":
                self._cancel_filter()
                event.stop()
                return
            if event.key == "backspace":
                # An empty field is still an active search. Otherwise the next
                # typed letter could unexpectedly become a browser command.
                self._update_filter_query(self._filter_query[:-1])
                event.stop()
                return
            if event.key in ("slash", "/") and not self._filter_query:
                # Treat repeated activation keys as activation, not query text.
                event.stop()
                return
            if event.key == "shift+space":
                self._update_filter_query(self._filter_query + " ")
                event.stop()
                return
            # Arrows and Return navigate search results; letters remain text so
            # users can type names containing j, k, or l.
            if event.key in ("up", "down", "left", "right", "enter", "tab"):
                pass  # fall through to KEYMAP
            elif event.character and event.character.isprintable():
                self._update_filter_query(self._filter_query + event.character)
                event.stop()
                return
            else:
                return

        action = resolve_key(event.key)
        if action is not None:
            event.stop()
            self._execute_command(action)

    def _execute_command(self, action: str) -> None:
        """Keep direct shortcuts and leader selections on the same dispatch path."""
        app_actions = {
            "quit": self.exit,
            "show_help": lambda: self.push_screen(HelpScreen()),
            "show_commands": self.action_show_commands,
            "command_palette": self.action_command_palette,
            "show_settings": self.action_show_settings,
            "add_library": self.action_add_library,
            "rescan_library": self.action_rescan_library,
            "edit_tags": self.action_edit_tags,
        }
        if action in app_actions:
            app_actions[action]()
            return
        if self._state is None:
            return
        if action == "waveform_nav_enter":
            # Keep the current sample/query intact; search owns letter input.
            if not self._filter_active:
                self._enter_waveform_nav()
            return
        if action in WAVEFORM_KEYMAP.values():
            if self._waveform_nav_active:
                if action in ("waveform_seek_confirm", "waveform_nav_exit"):
                    self._exit_waveform_nav(seek=action == "waveform_seek_confirm")
                else:
                    self._waveform_nav_move(action.removeprefix("waveform_seek_"))
            return
        if action == "move_up":
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
            if self._filter_active:
                self._cancel_filter()
            elif self._active_pane == "stage":
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
        """Preview a newly focused sample when automatic audition is enabled."""
        if not self._preferences.auto_audition or self._preferences.audio_output == "disabled":
            return
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
        if self._preferences.audio_output == "disabled":
            return
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
        """Resume a paused sample unless output has been disabled in Settings."""
        if self._preferences.audio_output == "disabled":
            return
        playback = self._audio_player.snapshot()
        if playback.status is PlaybackStatus.PAUSED and playback.path is not None:
            self._audio_player.play(playback.path)
        self._set_status(self._build_status())

    def _poll_audio(self) -> None:
        if self._state is not None:
            # App timers can tick while screen children are being unmounted.
            # Missing views mean teardown, not a playback failure.
            try:
                top_display = self.query_one("#top-display", TopDisplayWidget)
            except NoMatches:
                return
            playback = self._audio_player.snapshot()
            progress = 0.0
            if playback.duration_seconds and playback.duration_seconds > 0:
                progress = playback.position_seconds / playback.duration_seconds
            top_display.set_playback_progress(
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
            # The preview retains this sample's widget. Reapplying data would
            # reset its cursors; reapplying loading would erase a decode error.
            # Its original worker still owns any in-flight completion.
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
        # Search reuses Left/Right for browser navigation. End waveform mode
        # without seeking so one key press never controls both interfaces.
        if self._waveform_nav_active:
            self._exit_waveform_nav(seek=False)
        self._active_pane = "browser"
        self._filter_active = True
        self._filter_query = ""
        self._filter_focused_index = 0
        self._filter_results = ()
        self._refresh_ui(audition=False)

    def on_paste(self, event) -> None:
        """Accept pasted search text without interpreting it as app commands."""
        if self._filter_active and len(self.screen_stack) <= 1:
            text = " ".join(event.text.splitlines())
            self._update_filter_query(self._filter_query + text)
            event.stop()

    def _cycle_pane_focus(self) -> None:
        """Move keyboard actions between Browser and the persistent Stage."""
        self._active_pane = "stage" if self._active_pane == "browser" else "browser"
        if self._active_pane == "stage":
            # Search typing must stop when Tab leaves Browser, while the
            # underlying directory cursor remains available on return.
            self._filter_active = False
            self._filter_query = ""
            self._filter_focused_index = 0
            self._filter_results = ()
        self._refresh_ui()

    def _cancel_filter(self) -> None:
        """Restore the directory cursor and leave typeahead mode."""
        self._filter_active = False
        self._filter_query = ""
        self._filter_focused_index = 0
        self._filter_results = ()
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
                callback=lambda result, sid=item.sample_id: self._on_action_pane_dismissed(result, sid),
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

    def _on_action_pane_dismissed(self, result: str | None, sample_id: int | None) -> None:
        """Apply file actions to their captured subject after background refresh."""
        if sample_id is None:
            return
        if result == "tags":
            self.action_edit_tags(sample_id)
        elif result in ("add", "remove"):
            try:
                if self._data.get_sample_details(sample_id) is None:
                    raise ValueError("This sample is no longer indexed")
                if result == "add":
                    self._data.add_to_selection(sample_id)
                else:
                    self._data.remove_from_selection(sample_id)
                self._state = self._state.with_selection(self._data.get_selection_ids())
                self._refresh_ui(audition=False)
            except Exception as exc:  # noqa: BLE001 - a scan can remove the captured sample
                self.notify(f"Could not update Stage: {exc}", severity="error")
