"""Editable terminal settings with device discovery and explicit Save/Cancel."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static, Switch

from ...audio import list_output_devices
from ..settings import TuiPreferences


class SettingsScreen(ModalScreen):
    """Edit playback preferences without letting keys affect Browser or Stage."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    SettingsScreen { align: center middle; }
    #tui-settings {
        width: 74; max-width: 95%; height: 25; max-height: 95%;
        border: round $accent; background: $surface; padding: 0 2;
    }
    #tui-settings-title { height: 2; text-style: bold; }
    #tui-settings-body { height: 1fr; }
    #tui-settings-body Label { margin-top: 1; }
    #tui-settings-body Static { height: auto; }
    #tui-settings-buttons { height: 3; align-horizontal: right; }
    #tui-settings-buttons Button { margin-left: 1; }
    #tui-settings-error { color: $error; }
    #tui-settings-hint { height: 1; color: $text-muted; }
    """

    def __init__(
        self,
        preferences: TuiPreferences,
        *,
        on_save: Callable[[TuiPreferences], None],
        config_path: Path,
        database_path: str,
        library_path: str,
        device_provider=list_output_devices,
    ) -> None:
        super().__init__()
        self._preferences = preferences
        self._on_save = on_save
        self._config_path = config_path
        self._database_path = database_path
        self._library_path = library_path
        self._device_error = ""
        # Keep portable choices available when no audio hardware can be queried.
        self._outputs = [("System Default Output", "system_default")]
        try:
            devices = device_provider()
        except Exception as exc:  # noqa: BLE001 - report optional backend failures
            devices = ()
            self._device_error = f"Device discovery unavailable: {exc}"
        self._outputs.extend(
            (f"{device.name} ({device.host_api}, {device.max_output_channels} ch)",
             f"device:{device.index}")
            for device in devices
        )
        self._outputs.append(("Disabled — no playback", "disabled"))
        if preferences.audio_output not in {value for _label, value in self._outputs}:
            # Preserve a disconnected device choice until the user changes it.
            self._outputs.append((f"Unavailable {preferences.audio_output}", preferences.audio_output))

    def compose(self) -> ComposeResult:
        """Keep actions visible even in a standard 80×24 terminal."""
        with Vertical(id="tui-settings"):
            yield Static("Settings", id="tui-settings-title")
            with VerticalScroll(id="tui-settings-body"):
                yield Label("Audio output")
                yield Select(
                    self._outputs, value=self._preferences.audio_output,
                    allow_blank=False, id="tui-audio-output",
                )
                if self._device_error:
                    yield Static(self._device_error, markup=False)
                yield Label("Auto-audition while browsing results")
                yield Switch(self._preferences.auto_audition, id="tui-auto-audition")
                yield Static("Space still plays or pauses when auto-audition is off.")
                yield Label("Current library")
                yield Static(self._library_path, markup=False)
                yield Label("Configuration")
                yield Static(str(self._config_path), markup=False)
                yield Label("Database")
                yield Static(self._database_path, markup=False)
                yield Static("", id="tui-settings-error", markup=False)
            with Horizontal(id="tui-settings-buttons"):
                yield Button("Save", id="tui-settings-save", variant="primary")
                yield Button("Cancel", id="tui-settings-cancel")
            yield Static("Tab move · Enter choose · Esc cancel", id="tui-settings-hint")

    def on_mount(self) -> None:
        """Start keyboard navigation at the first editable control."""
        self.query_one("#tui-audio-output", Select).focus()

    def action_cancel(self) -> None:
        """Discard unsaved values and return to the previous TUI view."""
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Persist on Save; retain the modal and show any save error in place."""
        event.stop()
        if event.button.id == "tui-settings-cancel":
            self.dismiss()
            return
        if event.button.id != "tui-settings-save":
            return
        preferences = TuiPreferences(
            self.query_one("#tui-auto-audition", Switch).value,
            str(self.query_one("#tui-audio-output", Select).value),
        )
        try:
            self._on_save(preferences)
        except Exception as exc:  # noqa: BLE001 - preserve edits after write/backend failure
            self.query_one("#tui-settings-error", Static).update(f"Could not save settings: {exc}")
            return
        self.dismiss()
