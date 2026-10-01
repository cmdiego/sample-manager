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
) -> MainWindow:
    """Wire a controller + main window on top of a browser service."""
    controller = BrowserController(service, player=player)
    return MainWindow(
        controller,
        waveform_service=waveform_service,
        audio_player_factory=audio_player_factory,
    )


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
