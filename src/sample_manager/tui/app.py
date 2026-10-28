"""Sample Manager TUI — main Textual application."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from pathlib import Path
from typing import Callable

from rich.markup import escape

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Static, OptionList, Button
from .widgets.browse_columns import BrowseColumns

from ..audio import AudioPlayer, PlaybackStatus, WaveformData, WaveformService
from ..audio.decode_cache import shared_decode_cache
from ..audio.metadata import ContainerMetadata, read_metadata
from ..audio.backends import BackendUnavailable
from .widgets.metadata_panel import MetadataPanel
from .widgets.metadata_screen import MetadataScreen
from .widgets.directory_screen import DirectoryScreen
from ..services.stage_workspace import StageWorkspace
from .widgets.stage_path_screen import StagePathScreen
from ..services.sample_analysis import StoredWaveformService, backfill_analysis
from ..config import (
    add_library_root, ensure_config_exists, get_config_path, load_config,
    normalize_config, save_config,
)
from ..normalize import norm_rel_path
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
from .widgets.top_display import TopDisplayWidget
from .widgets.transport import TransportBar
from .widgets.waveform import WaveformWidget


# Rows on each side of the cursor decoded ahead of time.
PREFETCH_NEIGHBORS = 3
# Sleep between files during the post-scan analysis backfill, so it leaves
# the GIL to the Python audio callback.
ANALYSIS_BACKFILL_PAUSE_SECONDS = 0.005


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
        Binding("f7", "stage_new_folder", "Stage Folder", priority=True),
    ]

    def __init__(
        self,
        *,
        audio_player: AudioPlayer | None = None,
        waveform_service: WaveformService | None = None,
        preferences: TuiPreferences | None = None,
        player_factory: Callable[[TuiPreferences], AudioPlayer] = build_tui_player,
        config_path: Path | None = None,
        device_provider=None,
        metadata_reader: Callable[[Path], ContainerMetadata] = read_metadata,
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
            else StoredWaveformService(decoder=(
                self._audio_player.waveform_decoder
                if isinstance(getattr(type(self._audio_player), "waveform_decoder", None), property)
                else shared_decode_cache()
            ))
        )
        self._metadata_reader = metadata_reader
        self._metadata_path: Path | None = None
        self._metadata_generation = 0
        self._db: Db | None = None
        self._data: TuiDataSource | None = None
        self._state: NavState | None = None
        self._indexed: dict[str, int] = {}
        self._library_roots: tuple[Path, ...] = ()
        self._view = "browse"
        self._saved_search = None
        self._preview_focused = False
        self._active_pane = "browser"
        self._stage_items: tuple[NavItem, ...] = ()
        self._stage_focused_index = 0
        self._stage_current_folder_id: int | None = None
        self._stage_entries: tuple[dict, ...] = ()
        self._stage_restore_target: tuple[bool, int | None] | None = None
        self._scan_in_progress = False
        self._scan_message = ""
        self._analysis_cancel = threading.Event()
        self._analysis_serial = threading.Lock()
        self._audio_poll_timer = None
        self._transport_path: Path | None = None
        # Typeahead filter state
        self._filter_active: bool = False
        self._filter_query: str = ""
        self._filter_focused_index: int = 0
        self._filter_results: tuple[NavItem, ...] = ()
        self._tag_filter: str | None = None
        self._facet_key = None
        self._facets: list[dict] = []
        self._summaries: dict[int, dict] = {}
        self._last_auditioned_path: Path | None = None
        self._waveform_path: Path | None = None
        self._waveform_data: WaveformData | None = None
        self._waveform_generation = 0
        self._waveform_identity = None
        # Waveform navigation mode state
        self._waveform_nav_active: bool = False
        self._nav_cursor_fraction: float = 0.0
        self._nav_display_width: int = 80
        # Session-local identities survive sorting, selection and folder revisits.
        self._browser_cursors: dict[Path, tuple[Path | None, int]] = {}
        self._stage_cursors: dict[int | None, tuple[tuple[bool, int | None], int]] = {}

    # ── compose ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Keep browsing dominant and share a compact preview across both panes."""
        placeholder = NavState.initial(Path("/"), [])
        yield Static("Sample Manager · F4 Add Folder to begin", id="library-header", markup=False)
        with Horizontal(id="view-tabs"):
            for label, action in (("Browse", "browse"), ("Search", "search"), ("Stage", "stage"), ("Arrangements", "arrangements"), ("Settings", "settings")):
                button = Button(label, id="view-" + action)
                button.can_focus = False
                yield button
        yield TopDisplayWidget(id="top-display")
        with Container(id="main-grid"):
            yield BrowserZone(placeholder, id="browser-zone")
            yield SelectedFilesListWidget(id="selection-list")
        with Horizontal(id="stage-actions"):
            for label, action in (("Tag all · Alt+T", "stage-tag-all"),
                                  ("Arrange · Alt+4", "stage-arrange"),
                                  ("Clear Stage · Alt+C", "stage-clear-all")):
                button = Button(label, id=action)
                button.can_focus = False
                yield button
        yield TransportBar(id="transport-bar")
        yield Static("F4 Add Folder · F2 Settings", id="status-bar", markup=False)
        yield Static("F1 Commands · ? Help · q Quit", id="shortcut-bar", markup=False)

    def on_resize(self, event) -> None:
        """Reserve useful list space on short terminals and balance narrow panes."""
        self.set_class(event.size.height < 30, "compact")
        self.set_class(event.size.width < 100, "narrow")

    # ── lifecycle ──────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._audio_poll_timer = self.set_interval(1 / 30, self._poll_audio, pause=True)
        self._apply_theme(self._preferences.theme)
        self.call_after_refresh(self._initialize)

    def _initialize(self) -> None:
        """Open indexed roots and choose the configured default when present."""
        if not self._preferences_supplied:
            self._apply_preferences(load_tui_preferences(self._config_path), persist=False)
        self._db = _open_db(self._config_path) if self._config_path else _open_db()
        self._bind_analysis_database()
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
        self._analysis_cancel.set()
        self._audio_player.close()
        close_waveforms = getattr(self._waveform_service, "close", None)
        if close_waveforms is not None:
            close_waveforms()
        if self._db is not None:
            self._db.close()
            self._db = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Views are explicit buttons; bulk actions share the service layer."""
        action = event.button.id or ""
        if action.startswith("view-"):
            event.stop()
            target = action.removeprefix("view-")
            if target == "settings":
                self.action_show_settings()
            elif target == "arrangements":
                self.action_show_arrangements()
            else:
                self._switch_view(target)
        elif action == "stage-arrange":
            event.stop()
            self.action_show_arrangements()
        elif action == "stage-tag-all":
            event.stop()
            self._bulk_tag_stage()
        elif action == "stage-clear-all":
            event.stop()
            self._clear_stage_confirmed()

    def _switch_view(self, view: str) -> None:
        """Retain view-local search and the shared Stage/navigation cursors."""
        if self._state is None:
            return
        self._leave_preview()
        if self._filter_active or self._filter_query:
            self._saved_search = (self._state.current_root, self._filter_query, self._filter_results, self._filter_focused_index, self._tag_filter)
        self._filter_active, self._filter_query, self._filter_results = False, "", ()
        self._view = view
        self._active_pane = "stage" if view == "stage" else "browser"
        if view == "search":
            self._filter_active = True
            if self._saved_search is not None and self._saved_search[0] == self._state.current_root:
                _, self._filter_query, self._filter_results, self._filter_focused_index, self._tag_filter = self._saved_search
                # Hidden views may outlive rescans/tag edits; retain cursor intent
                # but rebuild membership before any action can use a stale ID.
                self._reload_filter_results()
        self.set_class(view == "stage", "stage-view")
        self.set_class(view == "search", "search-view")
        self._refresh_ui(audition=False)

    def _profiles_path(self) -> Path:
        """Respect this session's config rather than a global/default profile path."""
        from ..profiles import get_profiles_dir
        path = self._config_path or get_config_path()
        return get_profiles_dir(load_config(path) if path.is_file() else {})

    def action_show_arrangements(self) -> None:
        """Open saved arrangement/preview/history workflows without changing Stage."""
        if self._db is None or isinstance(self.screen, ModalScreen):
            return
        from .widgets.arrangements_screen import ArrangementsScreen
        try:
            self.push_screen(ArrangementsScreen(self._db.path, self._profiles_path(),
                                               lambda: self._refresh_ui(audition=False)))
        except Exception as exc:
            self.notify(f"Could not open arrangements: {exc}", severity="error")

    def _bulk_tag_stage(self) -> None:
        """Apply a typed tag through the same validation as single-sample edits."""
        if self._db is None:
            return
        ids = tuple(self._data.get_selection_ids())
        def apply(text):
            """Capture selected IDs before opening the modal."""
            for sid in ids:
                self._data.add_sample_tag(sid, text)
            self._facet_key = None
            self._refresh_ui(audition=False)
        self.push_screen(StagePathScreen("Tag all Stage samples", f"Attach a tag to {len(ids)} samples.", apply))

    def _clear_stage_confirmed(self) -> None:
        """Clear persistent Stage only after reviewing the affected selection."""
        if self._db is None:
            return
        from .widgets.confirm_screen import ConfirmScreen
        from ..repos.selection_repo import SelectionRepo
        def apply(yes):
            """Cancellation leaves both virtual folders and samples untouched."""
            if yes and self._db is not None:
                SelectionRepo(self._db).clear()
                self._stage_current_folder_id = None
                self._refresh_ui(audition=False)
        self.push_screen(ConfirmScreen(f"Clear {len(self._data.get_selection_ids())} staged samples and all virtual Stage folders? Source files stay in place.", "Clear Stage"), callback=apply)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Apply explicit column choices without stealing h/l directory keys."""
        if event.option_list.id not in ("folder-column", "tag-column") or self._state is None:
            return
        event.stop()
        columns = self.query_one(BrowseColumns)
        self._active_pane = "browser"
        if event.option_list.id == "folder-column":
            path = columns.paths[event.option_index]
            if path == self._state.current_dir.parent:
                self._handle_go_back()
            elif path != self._state.current_dir:
                self._enter_browser_directory(path)
        else:
            self._tag_filter = columns.tags[event.option_index]
            if self._tag_filter is None:
                self._cancel_filter()
            else:
                self._filter_active = False
                self._filter_query = "tag:" + self._tag_filter
                self._filter_results = self._data.tagged_samples(self._state.current_root, self._tag_filter, self._state.current_dir)
                self._filter_focused_index = 0
                self._refresh_ui(audition=False)
        for view in columns.query(OptionList):
            view.can_focus = False
        event.option_list.blur()

    def action_focus_columns(self) -> None:
        """Additive column entry leaves Tab and Ctrl-directional pane contracts intact."""
        columns = self.query_one(BrowseColumns)
        if self.has_class("narrow"):
            self.notify("Folder/tag columns appear at 100 columns; widen the terminal.")
            return
        self._filter_active = False
        for view in columns.query(OptionList):
            view.can_focus = True
        columns.query_one("#folder-column", OptionList).focus()

    # ── settings ───────────────────────────────────────────────────────────

    def get_system_commands(self, screen):
        """Make Settings searchable from Textual's existing command palette."""
        yield from super().get_system_commands(screen)
        yield SystemCommand("Arrangements", "Save Stage, preview, export and revert", self.action_show_arrangements)
        yield SystemCommand("Browse View", "Return to folder browsing", lambda: self._switch_view("browse"))
        yield SystemCommand("Search View", "Restore library search", lambda: self._switch_view("search"))
        yield SystemCommand("Stage View", "Work with Stage and bulk actions", lambda: self._switch_view("stage"))
        yield SystemCommand("Browse Columns", "Focus folder/tag columns (Alt+Left/Right)", self.action_focus_columns)
        yield SystemCommand("Settings", "Audio output and auto-audition preferences", self.action_show_settings)
        yield SystemCommand("Add Folder", "Index a sample folder and select its library", self.action_add_library)
        yield SystemCommand("Rescan Library", "Index added, changed, and removed samples", self.action_rescan_library)
        yield SystemCommand("New Stage Folder", "Create virtual sample folders and subfolders", self.action_stage_new_folder)
        yield SystemCommand("Move Stage Item", "Move a staged sample or folder", self.action_stage_move)
        yield SystemCommand("Rename Stage Folder", "Rename the focused virtual Stage folder", self.action_stage_rename)
        yield SystemCommand("Inspect Item", "List directory contents or inspect embedded audio metadata", self.action_show_metadata)
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

    async def _save_preferences(self, preferences: TuiPreferences) -> None:
        """Keep device construction/closure and YAML writes off the UI thread."""
        changed = any(getattr(preferences, key) != getattr(self._preferences, key)
                      for key in ("audio_output", "engine", "buffer_frames", "cache_mb"))
        replacement = await asyncio.to_thread(self._player_factory, preferences) if changed else None
        try:
            await asyncio.to_thread(save_tui_preferences, preferences, self._config_path)
        except Exception:
            if replacement is not None:
                await asyncio.to_thread(replacement.close)
            raise
        old_player = None
        if replacement is not None:
            old_player, self._audio_player = self._audio_player, replacement
            self._last_auditioned_path = None
            if isinstance(self._waveform_service, StoredWaveformService) and isinstance(
                getattr(type(replacement), "waveform_decoder", None), property
            ):
                self._waveform_service.bind_decoder(replacement.waveform_decoder)
        self._preferences = preferences
        self._apply_theme(preferences.theme)
        if old_player is not None:
            await asyncio.to_thread(old_player.close)
        self._poll_audio()
        self._refresh_ui(audition=False)
        self.notify("Settings saved")

    def _apply_preferences(self, preferences: TuiPreferences, *, persist: bool) -> None:
        """Replace output only when necessary, and retain it if saving fails."""
        replacement = (
            self._player_factory(preferences)
            if any(getattr(preferences, key) != getattr(self._preferences, key)
                   for key in ("audio_output", "engine", "buffer_frames", "cache_mb")) else None
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
            if isinstance(self._waveform_service, StoredWaveformService) and isinstance(
                getattr(type(replacement), "waveform_decoder", None), property
            ):
                self._waveform_service.bind_decoder(replacement.waveform_decoder)
        self._preferences = preferences
        if self.is_running:
            self._apply_theme(preferences.theme)

    def _apply_theme(self, name: str) -> None:
        """Use named neutral tokens, with optional validated YAML colour overrides."""
        from textual.theme import Theme
        tokens = dict(primary="#638fba", accent="#638fba")
        if name == "light":
            tokens.update(background="#f5f5f3", surface="#ffffff", panel="#e8e8e5", foreground="#242424")
        else:
            tokens.update(background="#181a1d", surface="#202328", panel="#282c32", foreground="#e5e6e8")
        path = self._config_path or get_config_path()
        if path.is_file():
            config = load_config(path)
            config = config if isinstance(config, dict) else {}
            raw = config.get("tui", {}).get("theme_tokens", {}) if isinstance(config.get("tui"), dict) else {}
            if isinstance(raw, dict):
                from textual.color import Color
                for key, value in raw.items():
                    if key in tokens and isinstance(value, str):
                        try:
                            Color.parse(value)
                        except Exception:
                            continue  # Bad hand-edited tokens cannot prevent launch.
                        tokens[key] = value
        # Theme construction validates colour tokens before switching the view.
        self.register_theme(Theme(name="sample-manager-" + name, dark=name == "dark", **tokens))
        self.theme = "sample-manager-" + name

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
                self._bind_analysis_database()
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
            # A rescan may reflect edited native tags on the current file.
            self._metadata_path = None
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
            self._start_analysis_backfill(result.library_root_id)
        finally:
            self._scan_in_progress = False
            if self.is_running:
                self._set_status(self._build_status() if self._state else self._scan_message)

    # ── scan-time analysis ─────────────────────────────────────────────────

    def _bind_analysis_database(self) -> None:
        """Point DB-backed waveforms at the open database, when supported."""
        bind = getattr(self._waveform_service, "bind_database", None)
        if bind is not None:
            bind(self._db.path if self._db is not None else None)

    def _start_analysis_backfill(self, library_root_id: int) -> None:
        """Analyse new and changed samples after a scan, off the UI thread."""
        if self._db is None or not hasattr(self._waveform_service, "bind_database"):
            return
        self._analysis_cancel.set()
        self._analysis_cancel = threading.Event()
        self.run_worker(
            self._backfill_analysis(self._db.path, library_root_id, self._analysis_cancel),
            name="analysis-backfill", group="analysis-backfill", exclusive=True,
            exit_on_error=False,
        )

    async def _backfill_analysis(
        self, db_path: str, library_root_id: int, cancel: threading.Event,
    ) -> None:
        """Cooperatively cancel old executor jobs and serialize actual passes."""
        def run():
            """Only the latest uncancelled pass can reach decoding/storage."""
            with self._analysis_serial:
                if cancel.is_set():
                    return None
                with Db(db_path) as worker_db:
                    return backfill_analysis(
                        worker_db, library_root_id=library_root_id, cancel=cancel,
                        pause_seconds=ANALYSIS_BACKFILL_PAUSE_SECONDS,
                    )

        try:
            result = await asyncio.to_thread(run)
        except asyncio.CancelledError:
            cancel.set()
            return
        except Exception as exc:  # noqa: BLE001 - analysis is optional; browsing keeps working
            self.notify(f"Sample analysis failed: {exc}", severity="warning", timeout=8)
            return
        if result is not None and result.failed and self.is_running:
            self.notify(f"Analysis failed for {result.failed} samples; retry with sampleman analyze", severity="warning")
        if result is not None and result.analyzed and self.is_running:
            self._facet_key = None
            self._refresh_ui(audition=False)
            self.notify(f"Analyzed {result.analyzed} samples", timeout=4)

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
        self._facet_key = None
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
        self._filter_results = (
            self._data.tagged_samples(self._state.current_root, self._tag_filter, self._state.current_dir)
            if self._tag_filter and self._filter_query == "tag:" + self._tag_filter
            else self._data.search_samples(self._state.current_root, self._filter_query)
        )
        self._filter_focused_index = next(
            (index for index, item in enumerate(self._filter_results) if item.path == previous),
            max(0, min(self._filter_focused_index, len(self._filter_results) - 1)),
        )

    # ── data helpers ───────────────────────────────────────────────────────

    def _load_root(self, root_path: Path) -> None:
        """Reset Browser navigation to a root while preserving the Stage."""
        self._remember_browser_cursor()
        self._indexed = self._data.get_indexed_files(root_path)
        selection_ids = self._data.get_selection_ids()
        items = build_items(root_path, self._indexed, selection_ids, root=root_path)
        self._state = NavState.initial(
            root_path, items, selection_ids=selection_ids,
            library_roots=list(self._library_roots),
        )
        self._state = self._restore_browser_cursor(self._state)
        self._view = "browse"
        self.remove_class("stage-view", "search-view")
        self._preview_focused = False
        self._active_pane = "browser"
        self._filter_active = False
        self._tag_filter = None
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

        # One facet snapshot per library/scan/tag change, reused on cursor moves.
        facet_key = (self._state.current_root, self._state.current_dir, len(self._indexed), self._scan_message)
        if facet_key != self._facet_key and isinstance(self._data, TuiDataSource):
            self._facets, self._summaries = self._data.browse_facets(self._state.current_root, self._state.current_dir)
            self._facet_key = facet_key
        self.query_one(BrowseColumns).update_choices(self._state, self._facets)
        # Build a filtered view of the current state for the sample list
        selection_ids = self._data.get_selection_ids()
        self._filter_results = tuple(
            replace(item, is_selected=item.sample_id in selection_ids)
            for item in self._filter_results
        )
        filtered = tuple(
            replace(item, duration_seconds=summary.get("duration_seconds"),
                    loudness_lufs=summary.get("loudness_lufs"))
            if (summary := self._summaries.get(item.sample_id)) is not None else item
            for item in self._visible_items()
        )
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
        browser.set_class(self._active_pane == "browser" and not self._preview_focused, "active-pane")
        browser.sample_list.update(
            display_state,
            empty_label="no matches" if self._filter_query else "empty directory",
        )
        browser.filters_panel.update_filter(
            self._filter_query, active=self._filter_active,
            count=len(filtered) if self._filter_query else None,
        )

        # Stage owns its totals so a separate summary no longer consumes rows.
        total_bytes = self._data.get_selection_total_size()
        destination = self._data.get_active_destination()
        relative = self._state.current_dir.relative_to(self._state.current_root)
        location = relative.as_posix() if relative.parts else "/"
        browser.border_title = f"Browser · {escape(location)}"
        self.query_one("#library-header", Static).update(
            f"Sample Manager   ·   Library: {self._state.current_root.name}   ·   F1 Commands"
        )

        # Selected files list
        selected_rows = [
            (sid, row) for sid in sorted(selection_ids)
            if (row := self._data.get_sample_details(sid)) is not None
        ]
        # Stage entries include virtual folders and a parent row; sample IDs
        # remain the same persistent selection shared with the CLI and GUI.
        rows = self._build_stage_rows(selected_rows)
        self._stage_entries = tuple(rows)
        self._stage_items = tuple(
            NavItem(
                name=row.get("filename", "?"),
                path=(Path(row["virtual_path"]) if row.get("is_dir") else
                      self._data.get_sample_path(row["sample_id"]) or Path(row.get("filename", "?"))),
                is_dir=bool(row.get("is_dir")),
                sample_id=row.get("sample_id"),
                is_selected=not row.get("is_dir", False),
            ) for row in rows
        )
        if self._stage_restore_target is not None:
            for index, row in enumerate(rows):
                key = (bool(row.get("is_dir")), row.get("folder_id") if row.get("is_dir") else row.get("sample_id"))
                if key == self._stage_restore_target:
                    self._stage_focused_index = index
                    break
            self._stage_restore_target = None
        self._stage_focused_index = min(self._stage_focused_index, max(0, len(rows) - 1))
        workspace = self._get_stage_workspace()
        self.query_one("#selection-list", SelectedFilesListWidget).update(
            rows, focused_index=self._stage_focused_index,
            active=self._active_pane == "stage" and not self._preview_focused,
            total_bytes=total_bytes, destination=destination,
            sample_count=len(selection_ids),
            folder_path=workspace.path(self._stage_current_folder_id) if workspace else "",
        )

        # Top display — update with focused item
        focused = self._effective_focused_item()
        details = self._data.get_sample_details(focused.sample_id) if (focused and focused.sample_id) else None
        top_display = self.query_one("#top-display", TopDisplayWidget)
        top_display.set_class(self._preview_focused, "active-pane")
        top_display.update_focus(focused, details)
        self._request_waveform(focused, top_display)
        self._request_metadata(focused, top_display.metadata_panel)

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
        for distance in range(1, self._preferences.prefetch_depth + 1):
            for position in (index + distance, index - distance):
                if 0 <= position < len(items) and not items[position].is_dir:
                    nearest_first.append(items[position].path)
        prefetch(nearest_first)

    def _build_status(self) -> str:
        """Keep operational feedback separate from the active mode's shortcuts."""
        if self._state is None:
            return "F4 Add Folder to start your sample library"
        playback = self._audio_player.snapshot()
        audio = "Audio disabled" if self._preferences.audio_output == "disabled" else playback.status.value.capitalize()
        if playback.duration_seconds:
            audio += f" · {playback.position_seconds:.1f} / {playback.duration_seconds:.1f}s"
        if playback.error:
            audio += f" · {playback.error}"
        pane = "Preview" if self._preview_focused else ("Stage" if self._active_pane == "stage" else "Browser")
        return f"{self._scan_message + ' · ' if self._scan_message else ''}{pane} · {audio}"

    def _build_shortcuts(self) -> str:
        """Show only applicable primary keys, keeping extended actions in F1."""
        if self._state is None:
            return "F4 Add Folder · F2 Settings · F1 Commands · ? Help · q Quit"
        if self._preview_focused:
            return "h/l Seek · j/k Scroll details · Enter Confirm seek · Ctrl+↓ Return · Esc Cancel"
        if self._waveform_nav_active:
            return "←/→ Seek · Shift+←/→ Coarse · Enter Confirm · Esc Cancel · ? Help"
        if self._filter_active:
            return "↑/↓ Results · Enter Toggle · Space Play · Shift+Space Type space · Esc Clear"
        if self._active_pane == "stage":
            item = self._effective_focused_item()
            if item and item.is_dir:
                return "h Parent · j/k Move · l Open · n Folder · m Move · F1 Commands"
            return "Enter/d Remove · h Parent · j/k Move · l Actions · n Folder · m Move"
        item = self._effective_focused_item()
        if item and item.is_dir:
            return "h Parent · j/k Move · l/Enter Open · / Search · Tab Stage · F1 Commands"
        return "Enter Toggle · h Parent · j/k Move · l Actions · / Search · Tab Stage"

    def _set_status(self, text: str) -> None:
        """Ignore late updates while a modal or teardown hides the base screen."""
        try:
            self.query_one("#status-bar", Static).update(text)
            self.query_one("#shortcut-bar", Static).update(self._build_shortcuts())
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
        if action in ("stage_new_folder", "stage_move", "stage_rename"):
            if self._get_stage_workspace() is None:
                return "Open an indexed library first (F4)."
            if action != "stage_new_folder":
                if self._active_pane != "stage" or not self._stage_entries:
                    return "Focus an item in Stage first (Tab)."
                entry = self._stage_entries[self._stage_focused_index]
                if entry.get("is_parent"):
                    return "Choose a Stage sample or folder, not the parent entry."
                if action == "stage_rename" and not entry.get("is_dir"):
                    return "Choose a Stage folder to rename."
        if action == "show_metadata":
            item = self._effective_focused_item()
            if item is None:
                return "Choose a directory or sample first."
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
        if action == "remove_from_selection" and self._active_pane == "stage" and self._stage_entries:
            entry = self._stage_entries[self._stage_focused_index]
            if entry.get("is_dir") and not entry.get("is_parent"):
                return None
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
        view_action = resolve_key(event.key)
        if view_action in ("view_browse", "view_search", "view_stage", "show_arrangements", "focus_columns", "stage_tag_all", "stage_clear"):
            event.stop()
            self._execute_command(view_action)
            return
        if self.screen_stack and isinstance(self.focused, OptionList) and self.focused.id in ("folder-column", "tag-column"):
            if event.key in ("escape", "alt+right", "alt+left"):
                event.stop()
                if event.key == "escape":
                    focused = self.focused
                    for view in self.query_one(BrowseColumns).query(OptionList):
                        view.can_focus = False
                    focused.blur()
                else:
                    self.query_one("#tag-column" if event.key == "alt+right" else "#folder-column", OptionList).focus()
            return
        # Directional controls bypass search typing and seeking, while modal
        # dialogs retain ownership of their keys through the guard above.
        # Legacy terminals send Ctrl+H as byte 0x08, which Textual names
        # Backspace. Preserve deletion in search and leave DEL (0x7f) alone;
        # modal text fields have already returned above.
        pane_key = event.key
        if (
            pane_key == "backspace"
            and event.character == "\x08"
            and not self._filter_active
        ):
            pane_key = "ctrl+h"
        pane_action = resolve_key(pane_key)
        if pane_action and pane_action.startswith("focus_pane_"):
            event.stop()
            event.prevent_default()
            self._execute_command(pane_action)
            return
        if self._preview_focused:
            if event.key in ("j", "down", "k", "up"):
                event.stop()
                event.prevent_default()
                panel = self.query_one(TopDisplayWidget).metadata_panel
                panel.scroll_relative(y=1 if event.key in ("j", "down") else -1, animate=False)
                return
            if event.key in ("escape", "enter"):
                event.stop()
                self._leave_preview(seek=event.key == "enter")
                self._refresh_ui(audition=False)
                return
            # Loading/empty previews must not navigate the retained lower pane.
            if event.key in ("h", "l", "left", "right") and not self._waveform_nav_active:
                event.stop()
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
        if self._filter_active and not self._preview_focused:
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
            "show_metadata": self.action_show_metadata,
            "stage_new_folder": self.action_stage_new_folder,
            "stage_move": self.action_stage_move,
            "stage_rename": self.action_stage_rename,
            "focus_columns": self.action_focus_columns,
            "show_arrangements": self.action_show_arrangements,
            "stage_tag_all": self._bulk_tag_stage,
            "stage_clear": self._clear_stage_confirmed,
            "view_browse": lambda: self._switch_view("browse"),
            "view_search": lambda: self._switch_view("search"),
            "view_stage": lambda: self._switch_view("stage"),
        }
        if action in app_actions:
            app_actions[action]()
            return
        if self._state is None:
            return
        if action.startswith("focus_pane_"):
            self._focus_pane_direction(action.removeprefix("focus_pane_"))
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
                self._stage_go_back()
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
                if self._stage_current_folder_id is None:
                    self._cycle_pane_focus()
                else:
                    self._stage_go_back()
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
        self._wake_transport()

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
        self._wake_transport()
        self._set_status(self._build_status())

    def _resume_playback(self) -> None:
        """Resume a paused sample unless output has been disabled in Settings."""
        if self._preferences.audio_output == "disabled":
            return
        playback = self._audio_player.snapshot()
        if playback.status is PlaybackStatus.PAUSED and playback.path is not None:
            self._audio_player.play(playback.path)
        self._wake_transport()
        self._set_status(self._build_status())

    def _wake_transport(self) -> None:
        """Commands wake polling, including the loading interval before sound."""
        if self._audio_poll_timer is not None:
            self._audio_poll_timer.resume()

    def _poll_audio(self) -> None:
        """Refresh only transport/progress; stop polling when playback settles."""
        try:
            top_display = self.query_one("#top-display", TopDisplayWidget)
            transport = self.query_one(TransportBar)
        except NoMatches:
            return
        playback = self._audio_player.snapshot()
        progress = playback.position_seconds / playback.duration_seconds if playback.duration_seconds else 0
        top_display.set_playback_progress(playback.path, progress)
        stats_fn = getattr(self._audio_player, "engine_stats", None)
        stats = stats_fn() if stats_fn else {}
        transport.update_playback(playback, stats if isinstance(stats, dict) else {})
        if playback.path is not None and playback.path != self._transport_path:
            self._transport_path = playback.path
            transport.query_one(WaveformWidget).set_loading(playback.path)
            self.run_worker(self._load_transport_waveform(playback.path),
                            group="transport-waveform", exclusive=True, exit_on_error=False)
        self._set_status(self._build_status())
        if playback.status not in (PlaybackStatus.PLAYING, PlaybackStatus.LOADING):
            if self._audio_poll_timer is not None:
                self._audio_poll_timer.pause()

    async def _load_transport_waveform(self, path: Path) -> None:
        """Keep waveform completion tied to the sounding sample, not focus."""
        try:
            data = await asyncio.to_thread(self._waveform_service.load, path)
            if self._transport_path == path:
                self.query_one("#transport-waveform", WaveformWidget).set_data(data)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if self.is_running and self._transport_path == path:
                self.query_one("#transport-waveform", WaveformWidget).set_error(path, str(exc))

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
            self._wake_transport()
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
        self._set_status(self._build_status())

    # ── persistent virtual Stage folders ──────────────────────────────────

    def _get_stage_workspace(self) -> StageWorkspace | None:
        """Use folder capabilities when the data adapter provides persistence."""
        workspace = getattr(self._data, "stage_workspace", None)
        return workspace if isinstance(workspace, StageWorkspace) else None

    def _build_stage_rows(self, selected_rows: list[tuple[int, dict]]) -> list[dict]:
        """Render direct children of the current virtual folder, folders first."""
        workspace = self._get_stage_workspace()
        if workspace is None:
            return [dict(row, sample_id=sid) for sid, row in selected_rows]
        folders = workspace.folders()
        current = next((row for row in folders if row["id"] == self._stage_current_folder_id), None)
        if self._stage_current_folder_id is not None and current is None:
            self._stage_current_folder_id = None
        rows = []
        if current is not None:
            rows.append({"filename": "..", "is_dir": True, "is_parent": True,
                         "folder_id": current["parent_id"], "virtual_path": workspace.path(current["parent_id"])})
        rows.extend(
            {"filename": folder["name"], "is_dir": True, "folder_id": folder["id"],
             "virtual_path": workspace.path(folder["id"])}
            for folder in folders if folder["parent_id"] == self._stage_current_folder_id
        )
        placements = workspace.placements()
        rows.extend(dict(row, sample_id=sid) for sid, row in selected_rows if placements.get(sid) == self._stage_current_folder_id)
        return rows

    def _stage_add_sample(self, sample_id: int) -> bool:
        """Target the open Stage folder without moving an existing selection."""
        try:
            workspace = self._get_stage_workspace()
            if workspace is not None:
                workspace.stage_sample(sample_id, self._stage_current_folder_id)
            else:
                self._data.add_to_selection(sample_id)
        except Exception as exc:  # noqa: BLE001 - stale destinations/storage errors stay visible
            self.notify(f"Could not add to Stage: {exc}", severity="error")
            return False
        return True

    def _remember_stage_cursor(self) -> None:
        """Remember a folder/sample identity and fallback row before leaving it."""
        if not self._stage_entries:
            return
        entry = self._stage_entries[self._stage_focused_index]
        if entry.get("is_parent"):
            return  # Reentering should restore a real item, not the parent row.
        target = (bool(entry.get("is_dir")), entry.get("folder_id") if entry.get("is_dir") else entry.get("sample_id"))
        self._stage_cursors[self._stage_current_folder_id] = (target, self._stage_focused_index)

    def _stage_open_focused(self) -> bool:
        """Open a folder/parent row; return False for a sample action."""
        if not self._stage_entries:
            return False
        entry = self._stage_entries[self._stage_focused_index]
        if not entry.get("is_dir"):
            return False
        if entry.get("is_parent"):
            self._stage_go_back()
            return True
        self._remember_stage_cursor()
        self._stage_current_folder_id = entry["folder_id"]
        remembered = self._stage_cursors.get(self._stage_current_folder_id)
        self._stage_restore_target = remembered[0] if remembered else None
        # Skip the parent row when first entering a nonempty Stage folder.
        # Repeated l can then descend multiple levels without bouncing back.
        self._stage_focused_index = remembered[1] if remembered else 1
        self._refresh_ui(audition=False)
        return True

    def _stage_go_back(self) -> None:
        """Ascend Stage folders, keeping h/Left within the active pane at root."""
        workspace = self._get_stage_workspace()
        if self._stage_current_folder_id is None or workspace is None:
            return
        self._remember_stage_cursor()
        previous = self._stage_current_folder_id
        try:
            self._stage_current_folder_id = workspace.folder(previous)["parent_id"]
        except ValueError:
            self._stage_current_folder_id = None
        self._stage_restore_target = (True, previous)
        self._refresh_ui(audition=False)

    def action_stage_new_folder(self) -> None:
        """Create a folder/path under the open Stage destination."""
        self._show_stage_editor("stage_new_folder")

    def action_stage_move(self) -> None:
        """Move a captured Stage sample or folder to another virtual path."""
        self._show_stage_editor("stage_move")

    def action_stage_rename(self) -> None:
        """Rename the captured Stage folder without altering its contents."""
        self._show_stage_editor("stage_rename")

    def _show_stage_editor(self, action: str) -> None:
        """Capture IDs before displaying a form; validation errors stay editable."""
        if isinstance(self.screen, ModalScreen):
            return
        reason = self._command_unavailable(action)
        if reason:
            self.notify(reason, severity="warning")
            return
        workspace = self._get_stage_workspace()
        parent_id = self._stage_current_folder_id
        try:
            current_path = workspace.path(parent_id)
        except ValueError:
            # Another client can clear Stage while this view remains open.
            # Refresh to root and require a fresh choice rather than targeting
            # a stale destination or silently modifying a neighboring item.
            self._stage_current_folder_id = None
            self._refresh_ui(audition=False)
            self.notify("Stage folder changed. Choose a folder and try again.", severity="warning")
            return
        entry = dict(self._stage_entries[self._stage_focused_index]) if action != "stage_new_folder" else {}
        folder = bool(entry.get("is_dir"))
        title = {"stage_new_folder": "New Stage folder", "stage_move": "Move Stage item", "stage_rename": "Rename Stage folder"}[action]
        note = (f"Inside {current_path} · Use Drums/Kicks for subfolders; / starts at Stage root."
                if action == "stage_new_folder" else
                "Destination Stage folder: / for root. Missing folders will be created."
                if action == "stage_move" else "Enter a new name for this virtual folder.")
        initial = current_path if action == "stage_move" else entry.get("filename", "") if action == "stage_rename" else ""

        def apply(text: str) -> None:
            """Commit against the captured source and change view only on success."""
            if action == "stage_new_folder":
                self._stage_current_folder_id = workspace.create_folder(text, parent_id)
                self._stage_focused_index = 0
            elif action == "stage_move":
                self._stage_current_folder_id = (
                    workspace.move_folder(entry["folder_id"], text) if folder
                    else workspace.move_sample(entry["sample_id"], text)
                )
                self._stage_restore_target = (folder, entry["folder_id"] if folder else entry["sample_id"])
            else:
                workspace.rename_folder(entry["folder_id"], text)
                self._stage_restore_target = (True, entry["folder_id"])
            if self._waveform_nav_active:
                self._exit_waveform_nav(seek=False)
            self._preview_focused = False
            self._active_pane = "stage"
            self._filter_active, self._filter_query = False, ""
            self._filter_results = ()
            self._filter_focused_index = 0

        self.push_screen(StagePathScreen(title, note, apply, initial), self._on_stage_edit_completed)

    def _on_stage_edit_completed(self, changed: bool) -> None:
        """Refresh after dismissal so cancel preserves the original view exactly."""
        if changed:
            self._refresh_ui(audition=False)

    # ── native file metadata ──────────────────────────────────────────────

    def _directory_sample_id(self, path: Path) -> int | None:
        """Resolve inspector files using the same root-relative index as Browser."""
        if self._state is None:
            return None
        try:
            relative = norm_rel_path(path.relative_to(self._state.current_root))
        except ValueError:
            return None
        return self._indexed.get(relative)

    def _directory_sample_selected(self, path: Path) -> bool | None:
        """Expose eligibility and current Stage membership to the inspector."""
        sample_id = self._directory_sample_id(path)
        return sample_id in self._data.get_selection_ids() if sample_id is not None else None

    def _directory_change_stage(self, path: Path, action: str) -> str:
        """Stage one indexed file into the open destination, keeping tree focus."""
        sample_id = self._directory_sample_id(path)
        if sample_id is None or path.is_symlink():
            raise ValueError("This file is not an indexed sample. Rescan the library with F5 first.")
        selected = sample_id in self._data.get_selection_ids()
        remove = action == "remove" or (action == "toggle" and selected)
        if remove:
            self._data.remove_from_selection(sample_id)
        else:
            if not path.is_file():
                raise ValueError("This sample file is no longer available.")
            if not self._stage_add_sample(sample_id):
                raise ValueError("Could not add sample to the current Stage folder.")
        self._state = self._state.with_selection(self._data.get_selection_ids())
        self._refresh_ui(audition=False)
        return f"{'Removed from' if remove else 'Added to'} Stage: {path.name}"

    def action_show_metadata(self) -> None:
        """Inspect the focused directory contents or sample metadata."""
        if isinstance(self.screen, ModalScreen):
            return
        item = self._effective_focused_item()
        if item is None:
            self.notify("Choose a directory or sample first.")
            return
        if item.is_dir:
            if self._active_pane == "stage":
                self._stage_open_focused()
                return
            self.push_screen(DirectoryScreen(
                item.path, sample_selected=self._directory_sample_selected,
                change_stage=self._directory_change_stage,
            ))
            return
        panel = self.query_one(TopDisplayWidget).metadata_panel
        self.push_screen(MetadataScreen(panel))

    def _request_metadata(self, item: NavItem | None, panel: MetadataPanel) -> None:
        """Read once per focused target, independently of waveform decoding."""
        path = item.path if item is not None and not item.is_dir else None
        if path == self._metadata_path:
            return
        self._metadata_path = path
        self._metadata_generation += 1
        if path is None:
            return
        self.run_worker(
            self._load_metadata(path, self._metadata_generation, panel),
            name="embedded-metadata", group="embedded-metadata",
            exclusive=True, exit_on_error=False,
        )

    async def _load_metadata(self, path: Path, generation: int, panel: MetadataPanel) -> None:
        """Discard late reads after focus changes; file errors never stop browsing."""
        metadata = None
        error = ""
        try:
            metadata = await asyncio.to_thread(self._metadata_reader, path)
        except asyncio.CancelledError:
            return
        except BackendUnavailable:
            error = "Metadata reader unavailable. Install sample-manager[audio]."
        except Exception as exc:  # noqa: BLE001 - malformed files are nonfatal
            error = f"Metadata unavailable: {exc}"
        if generation == self._metadata_generation and path == self._metadata_path:
            # The panel reference stays valid while the full view is open.
            panel.set_result(path, metadata, error)

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

        try:
            stat = item.path.stat()
            identity = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            identity = None
        if item.path == self._waveform_path and identity == self._waveform_identity:
            # The preview retains this sample's widget. Reapplying data would
            # reset its cursors; reapplying loading would erase a decode error.
            # Its original worker still owns any in-flight completion.
            return

        self._waveform_generation += 1
        generation = self._waveform_generation
        self._waveform_path = item.path
        self._waveform_identity = identity
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
        # Preview may receive focus while decoding is still in flight.
        if self._preview_focused and not self._waveform_nav_active:
            self._enter_waveform_nav()

    # ── filter ─────────────────────────────────────────────────────────────

    def _start_filter(self) -> None:
        """Start a fresh typeahead query in the current directory."""
        # Search reuses Left/Right for browser navigation. End waveform mode
        # without seeking so one key press never controls both interfaces.
        if self._waveform_nav_active:
            self._exit_waveform_nav(seek=False)
        self._preview_focused = False
        self._active_pane = "browser"
        self._filter_active = True
        self._tag_filter = None
        self._filter_query = ""
        self._filter_focused_index = 0
        self._filter_results = ()
        self._refresh_ui(audition=False)

    def on_paste(self, event) -> None:
        """Accept pasted search text without interpreting it as app commands."""
        if self._filter_active and not self._preview_focused and len(self.screen_stack) <= 1:
            text = " ".join(event.text.splitlines())
            self._update_filter_query(self._filter_query + text)
            event.stop()

    def _leave_preview(self, *, seek: bool = False) -> None:
        """Return to the retained sample pane, cancelling unconfirmed seeking."""
        self._preview_focused = False
        if self._waveform_nav_active:
            self._exit_waveform_nav(seek=seek)

    def _focus_pane_direction(self, direction: str) -> None:
        """Follow the visible three-pane layout, stopping at its outer edges."""
        if direction == "up":
            if not self._preview_focused:
                self._preview_focused = True
                if not self._waveform_nav_active:
                    self._enter_waveform_nav()
                self._refresh_ui(audition=False)
            return
        if self._preview_focused:
            # Preview spans the full row, so it has no horizontal neighbour.
            if direction == "down":
                self._leave_preview()
                self._refresh_ui(audition=False)
            return
        target = {"left": "browser", "right": "stage"}.get(direction)
        if target is not None and target != self._active_pane:
            self._cycle_pane_focus()

    def _cycle_pane_focus(self) -> None:
        """Move keyboard actions between Browser and the persistent Stage."""
        self._leave_preview()
        self._active_pane = "stage" if self._active_pane == "browser" else "browser"
        if self._view in ("stage", "search"):
            self._view = "browse"
            self.remove_class("stage-view", "search-view")
        if self._active_pane == "stage":
            # Stop search typing when leaving Browser, retaining its directory cursor.
            self._filter_active = False
            self._filter_query = ""
            self._filter_focused_index = 0
            self._filter_results = ()
        self._refresh_ui()

    def _cancel_filter(self) -> None:
        """Restore the directory cursor and leave typeahead mode."""
        self._filter_active = False
        self._tag_filter = None
        self._filter_query = ""
        self._filter_focused_index = 0
        self._filter_results = ()
        self._refresh_ui()

    # ── navigation ─────────────────────────────────────────────────────────

    def _remember_browser_cursor(self) -> None:
        """Remember the underlying directory cursor without capturing search hits."""
        if self._state is not None:
            item = self._state.focused_item
            self._browser_cursors[self._state.current_dir] = (
                item.path if item else None, self._state.focused_index,
            )

    def _restore_browser_cursor(self, state: NavState) -> NavState:
        """Restore by path; removed items fall back to the nearest valid row."""
        remembered = self._browser_cursors.get(state.current_dir)
        if remembered is None or not state.items:
            return state
        path, index = remembered
        target = next((i for i, item in enumerate(state.items) if item.path == path), max(0, min(index, len(state.items) - 1)))
        return replace(state, focused_index=target)

    def _enter_browser_directory(self, path: Path) -> None:
        """Use identical remembered entry behavior for l/Right and Return."""
        self._remember_browser_cursor()
        items = build_items(path, self._indexed, self._data.get_selection_ids(), root=self._state.current_root)
        self._state = self._restore_browser_cursor(self._state.enter_dir(path, items))
        self._cancel_filter()

    def _handle_enter(self) -> None:
        """Enter folders with cursor memory, or keep existing sample actions."""
        item = self._effective_focused_item()

        if item is None:
            return

        if item.is_dir and self._active_pane == "stage":
            self._stage_open_focused()
            return

        if item.is_dir:
            self._enter_browser_directory(item.path)
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
            if not self._stage_open_focused():
                self._remove_focused()
            return

        if item.is_dir:
            self._enter_browser_directory(item.path)
        else:
            if item.sample_id is None:
                return
            # Toggle: add if not yet selected, remove if already selected
            if item.is_selected:
                self._data.remove_from_selection(item.sample_id)
            else:
                if not self._stage_add_sample(item.sample_id):
                    return
            selection_ids = self._data.get_selection_ids()
            self._state = self._state.with_selection(selection_ids)
            self._refresh_ui()

    def _handle_go_back(self) -> None:
        """Remember the child cursor, then highlight that folder in its parent."""
        if not self._state.dir_stack:
            return
        self._remember_browser_cursor()
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
        if not self._stage_add_sample(item.sample_id):
            return
        selection_ids = self._data.get_selection_ids()
        self._state = self._state.with_selection(selection_ids)
        self._refresh_ui()

    def _remove_focused(self) -> None:
        """Remove the currently visible row from the persistent selection."""
        if self._active_pane == "stage" and self._stage_entries:
            entry = self._stage_entries[self._stage_focused_index]
            if entry.get("is_dir"):
                workspace = self._get_stage_workspace()
                if entry.get("is_parent") or workspace is None:
                    return
                try:
                    workspace.remove_folder(entry["folder_id"])
                    self._stage_cursors.pop(entry["folder_id"], None)
                except ValueError as exc:
                    self.notify(str(exc), severity="warning")
                self._refresh_ui(audition=False)
                return
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
                    if not self._stage_add_sample(sample_id):
                        return
                else:
                    self._data.remove_from_selection(sample_id)
                self._state = self._state.with_selection(self._data.get_selection_ids())
                self._refresh_ui(audition=False)
            except Exception as exc:  # noqa: BLE001 - a scan can remove the captured sample
                self.notify(f"Could not update Stage: {exc}", severity="error")
