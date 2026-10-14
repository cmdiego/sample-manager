"""Qt application construction and ``run_gui()`` entry point.

``run_gui()`` builds a ``QApplication``, opens the database through the same
``_get_db()`` path every CLI command uses, constructs a ``LibraryBrowserService``
+ ``BrowserController`` + ``MainWindow``, and enters the Qt event loop.

Importing this module must not require a running display — that is why the
``QApplication`` is created lazily inside ``run_gui()``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QApplication

from ..services.library_browser import LibraryBrowserService
from .controller import BrowserController
from .main_window import SETTINGS_APP, SETTINGS_ORG, MainWindow
from .settings import (
    AudioOutputMode,
    AudioOutputSelection,
    load_audio_output_selection,
)


def _load_stylesheet() -> str:
    qss = Path(__file__).with_name("theme.qss")
    try:
        return qss.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_application(argv: list[str] | None = None) -> QApplication:
    """Return the singleton ``QApplication`` (creating it if needed)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else [])
    app.setOrganizationName(SETTINGS_ORG)
    app.setApplicationName(SETTINGS_APP)
    stylesheet = _load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)
    return app


def create_main_window(
    service: LibraryBrowserService,
    player=None,
    waveform_service=None,
    audio_player_factory=None,
    preferred_root_path: Path | None = None,
    on_library_selected: Callable[[Path], None] | None = None,
) -> MainWindow:
    """Wire a controller + main window on top of a browser service."""
    controller = BrowserController(service, player=player)
    return MainWindow(
        controller,
        waveform_service=waveform_service,
        audio_player_factory=audio_player_factory,
        preferred_root_path=preferred_root_path,
        on_library_selected=on_library_selected,
    )


def _record_selected_root(path: Path) -> None:
    """Keep GUI library choices aligned with the CLI's configured default."""
    from ..config import add_library_root, get_config_path, load_config, save_config

    config_path = get_config_path()
    config, _message = add_library_root(
        load_config(config_path), str(path), set_as_default=True
    )
    save_config(config, config_path)


def _build_player(selection: AudioOutputSelection | AudioOutputMode):
    """Build a player for the selected I/O mode and return an optional warning."""
    from ..audio.backends import is_available
    from ..audio.player import AudioPlayer
    from ..audio.sounddevice_output import SoundDeviceOutput

    if isinstance(selection, AudioOutputMode):
        selection = AudioOutputSelection(selection)
    if selection.mode is AudioOutputMode.DISABLED:
        return None, "Audio output disabled in Settings"
    if not is_available("sounddevice"):
        return None, "System audio unavailable (sounddevice not installed)"
    device = (
        selection.device_index
        if selection.mode is AudioOutputMode.SPECIFIC_DEVICE
        else None
    )
    return AudioPlayer(output=SoundDeviceOutput(device=device)), None


def _build_audio(selection: AudioOutputSelection | None = None):
    """Construct ``(AudioPlayer, WaveformService, warning)`` for the GUI.

    The default mode opens the operating system's default output device. Audio
    can be explicitly disabled in Settings. Imported lazily so numpy and
    sounddevice are never pulled in at GUI import time.
    """
    from ..audio.waveform import WaveformService

    selected = selection if selection is not None else load_audio_output_selection()
    player, warning = _build_player(selected)
    return player, WaveformService(), warning


def run_gui(
    argv: list[str] | None = None,
    *,
    simulation: bool = False,
    simulation_temp: bool = False,
) -> int:
    """Launch the Qt GUI and return the process exit code."""
    if argv is None:
        argv = sys.argv
    argv, simulation, simulation_temp = _consume_simulation_flags(
        argv, simulation, simulation_temp
    )

    if simulation_temp:
        return _run_temporary_simulation(argv)

    # A desktop launch should reach its Add Folder screen on a fresh install.
    # Keep simulation-temp ahead of this call so test sessions never write to
    # the user's config directory.
    _ensure_gui_setup()

    # Open the DB via the shared CLI helper so config resolution matches the
    # rest of the app. Imported lazily to avoid a hard cli.py import at module
    # load time.
    from ..cli import _get_db

    db = _get_db()
    try:
        service = LibraryBrowserService(db)
        app = build_application(argv)
        player, waveform_service, warning = _build_audio()
        window = create_main_window(
            service,
            player=player,
            waveform_service=waveform_service,
            audio_player_factory=_build_player,
            preferred_root_path=_configured_default_root(),
            on_library_selected=_record_selected_root,
        )
        if warning:
            window.show_status_error(warning)
        window.show()
        if simulation:
            from .simulation import run_simulation_shell

            return run_simulation_shell(window)
        return app.exec()
    finally:
        db.close()


def _configured_default_root() -> Path | None:
    """Read the configured startup root after the shared DB setup succeeds."""
    from ..config import get_config_path, load_config, normalize_config

    path = normalize_config(load_config(get_config_path())).get("default_library_root")
    return Path(path) if path else None


def _ensure_gui_setup() -> bool:
    """Create the same starter config and profiles as `sampleman init`.

    A fresh desktop launch has no terminal setup step. Both helpers are
    idempotent and leave existing config/profile content intact.

    Returns:
        True only when a new config was created on this launch.
    """
    from ..config import ensure_config_exists, load_config
    from ..profiles import create_example_profiles, get_profiles_dir

    config_path, created = ensure_config_exists()
    create_example_profiles(get_profiles_dir(load_config(config_path)))
    return created


def _consume_simulation_flags(
    argv: list[str], simulation: bool, simulation_temp: bool
) -> tuple[list[str], bool, bool]:
    """Remove app-level simulation flags before argv reaches QApplication."""
    cleaned: list[str] = []
    for arg in argv:
        if arg == "--simulation":
            simulation = True
            continue
        if arg == "--simulation-temp":
            simulation = True
            simulation_temp = True
            continue
        cleaned.append(arg)
    return cleaned, simulation, simulation_temp


def _run_temporary_simulation(argv: list[str]) -> int:
    """Launch the JSON shell against a disposable sample library and DB."""
    from .simulation import (
        create_temporary_simulation_environment,
        run_simulation_shell,
    )

    env = create_temporary_simulation_environment()
    try:
        app = build_application(argv)
        window = create_main_window(env.service)
        window.show()
        app.processEvents()
        return run_simulation_shell(window, root=env.root)
    finally:
        env.close()
