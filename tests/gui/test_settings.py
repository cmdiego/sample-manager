"""Settings page and runtime audio-output configuration tests."""

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QLabel

from sample_manager.audio.player import PlaybackSnapshot, PlaybackStatus
from sample_manager.gui.app import create_main_window
from sample_manager.gui.app import _build_player
from sample_manager.gui.dialogs import SettingsDialog
from sample_manager.gui.settings import (
    AUDIO_OUTPUT_DEVICE_KEY,
    AUDIO_OUTPUT_MODE_KEY,
    AudioOutputMode,
    AudioOutputSelection,
    load_audio_output_selection,
    load_audio_output_mode,
    save_audio_output_mode,
    save_audio_output_selection,
)
from sample_manager.audio.devices import AudioOutputDevice


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


class FakePlayer:
    def __init__(self) -> None:
        self.closed = False

    def play(self, path) -> None:
        pass

    def play_from_start(self, path) -> None:
        pass

    def snapshot(self) -> PlaybackSnapshot:
        return PlaybackSnapshot(PlaybackStatus.IDLE, None, 0.0, None, None)

    def close(self) -> None:
        self.closed = True


def test_audio_output_defaults_to_system_device(tmp_path):
    assert load_audio_output_mode(_settings(tmp_path)) is AudioOutputMode.SYSTEM_DEFAULT


def test_audio_output_mode_round_trips_and_invalid_values_degrade(tmp_path):
    settings = _settings(tmp_path)
    save_audio_output_mode(AudioOutputMode.DISABLED, settings)
    assert load_audio_output_mode(settings) is AudioOutputMode.DISABLED

    settings.setValue(AUDIO_OUTPUT_MODE_KEY, "removed-mode")
    assert load_audio_output_mode(settings) is AudioOutputMode.SYSTEM_DEFAULT


def test_specific_audio_device_round_trips(tmp_path):
    settings = _settings(tmp_path)
    selection = AudioOutputSelection(AudioOutputMode.SPECIFIC_DEVICE, 7)
    save_audio_output_selection(selection, settings)

    assert load_audio_output_selection(settings) == selection
    assert settings.value(AUDIO_OUTPUT_DEVICE_KEY) == 7


def test_settings_dialog_places_audio_output_in_io_tab(tmp_path, qtbot):
    settings = _settings(tmp_path)
    changed = []
    devices = (
        AudioOutputDevice(2, "MacBook Speakers", "Core Audio", 2, 48000.0, True),
        AudioOutputDevice(4, "Studio DAC", "Core Audio", 2, 96000.0, False),
    )
    dialog = SettingsDialog(
        changed.append,
        settings=settings,
        device_provider=lambda: devices,
    )
    qtbot.addWidget(dialog)

    assert dialog.findChild(type(dialog.audio_output_combo), "AudioOutputMode") is not None
    assert dialog.audio_output_combo.currentData() == AudioOutputMode.SYSTEM_DEFAULT.value
    labels = [
        dialog.audio_output_combo.itemText(index)
        for index in range(dialog.audio_output_combo.count())
    ]
    assert any("MacBook Speakers" in label and "system default" in label for label in labels)
    assert any("Studio DAC" in label for label in labels)
    dialog.audio_output_combo.setCurrentIndex(
        dialog.audio_output_combo.findData(AudioOutputMode.DISABLED.value)
    )
    dialog._save()

    assert changed == [AudioOutputSelection(AudioOutputMode.DISABLED)]
    assert load_audio_output_mode(settings) is AudioOutputMode.DISABLED


def test_settings_defaults_to_none_when_no_devices_are_available(tmp_path, qtbot):
    settings = _settings(tmp_path)
    dialog = SettingsDialog(
        settings=settings,
        device_provider=lambda: (),
    )
    qtbot.addWidget(dialog)

    assert dialog.audio_output_combo.count() == 1
    assert dialog.audio_output_combo.currentText() == "None"
    assert dialog.audio_output_combo.currentData() == AudioOutputMode.DISABLED.value
    assert "No audio output" in dialog._audio_output_description.text()


def test_settings_defaults_to_none_when_device_discovery_fails(tmp_path, qtbot):
    def fail_discovery():
        raise RuntimeError("Core Audio unavailable")

    dialog = SettingsDialog(
        settings=_settings(tmp_path),
        device_provider=fail_discovery,
    )
    qtbot.addWidget(dialog)

    assert dialog.audio_output_combo.currentText() == "None"
    error_label = dialog.findChild(QLabel, "AudioDeviceError")
    assert error_label is not None
    assert "Core Audio unavailable" in error_label.text()


def test_settings_restores_specific_device(tmp_path, qtbot):
    settings = _settings(tmp_path)
    save_audio_output_selection(
        AudioOutputSelection(AudioOutputMode.SPECIFIC_DEVICE, 4),
        settings,
    )
    devices = (
        AudioOutputDevice(4, "Studio DAC", "Core Audio", 2, 96000.0, False),
    )
    changed = []
    dialog = SettingsDialog(
        changed.append,
        settings=settings,
        device_provider=lambda: devices,
    )
    qtbot.addWidget(dialog)

    assert dialog.audio_output_combo.currentData() == "device:4"
    dialog._save()
    assert changed == [AudioOutputSelection(AudioOutputMode.SPECIFIC_DEVICE, 4)]


def test_settings_action_opens_dialog(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    window.show()

    window._settings_action.trigger()
    assert isinstance(window.active_dialog, SettingsDialog)
    window.active_dialog.close()


def test_command_comma_opens_settings(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    QApplication.setActiveWindow(window)

    assert window._settings_action.shortcut() == QKeySequence("Meta+,")
    qtbot.keyClick(window, Qt.Key_Comma, Qt.KeyboardModifier.MetaModifier)
    assert isinstance(window.active_dialog, SettingsDialog)
    window.active_dialog.close()


def test_applying_audio_mode_replaces_and_closes_player(populated_service, qtbot):
    service, _root = populated_service
    original = FakePlayer()
    replacement = FakePlayer()
    requested = []

    def factory(mode):
        requested.append(mode)
        return replacement, None

    window = create_main_window(
        service,
        player=original,
        audio_player_factory=factory,
    )
    qtbot.addWidget(window)
    selection = AudioOutputSelection(AudioOutputMode.SYSTEM_DEFAULT)
    window._apply_audio_output_mode(selection)

    assert requested == [selection]
    assert original.closed
    assert window.controller.player is replacement
    window.close()
    assert replacement.closed


def test_disabling_audio_removes_player(populated_service, qtbot):
    service, _root = populated_service
    original = FakePlayer()
    window = create_main_window(
        service,
        player=original,
        audio_player_factory=lambda mode: (None, "Audio output disabled in Settings"),
    )
    qtbot.addWidget(window)
    window._apply_audio_output_mode(AudioOutputSelection(AudioOutputMode.DISABLED))

    assert original.closed
    assert window.controller.player is None
    assert "disabled" in window._status_error.text().lower()
    window.close()


def test_player_factory_routes_to_selected_device(monkeypatch):
    monkeypatch.setattr(
        "sample_manager.audio.backends.is_available",
        lambda name: True,
    )
    player, warning = _build_player(
        AudioOutputSelection(AudioOutputMode.SPECIFIC_DEVICE, 9)
    )
    try:
        assert warning is None
        assert player._output._device == 9
    finally:
        player.close()
