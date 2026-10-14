"""Qt dialogs used by the GUI: file action, help, and command palette.

Presentation-only. Dialogs take plain callbacks / DTOs and never touch the DB or
the service directly; they invoke callbacks the controller/window supplies. All
three close on ``Escape`` (QDialog default ``reject``) and expose stable
``objectName``s for testing.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..services.library_browser import SampleDetails
from .command_interpreter import CommandInterpreter, CommandResult
from .shortcuts import SHORTCUT_HELP
from .settings import (
    AudioOutputMode,
    AudioOutputSelection,
    load_audio_output_selection,
    save_audio_output_selection,
)


def _human_size(num: int | None) -> str:
    if not num:
        return "—"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


class ActionDialog(QDialog):
    """Per-file action dialog opened by ``L`` / double-click on a file.

    Shows the file name and metadata and offers Add / Remove / Close. Audio
    playback is intentionally absent — that lands in Phase 4.
    """

    def __init__(
        self,
        details: SampleDetails | None,
        on_add: Callable[[int], None],
        on_remove: Callable[[int], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ActionDialog")
        self.setWindowTitle("Sample Actions")
        self._details = details
        self._on_add = on_add
        self._on_remove = on_remove

        layout = QVBoxLayout(self)

        title = QLabel(details.filename if details else "Unknown sample")
        title.setObjectName("ActionTitle")
        title.setWordWrap(True)
        font = title.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        if details is not None:
            fmt = getattr(details, "format", None) or details.ext or "—"
            meta = QLabel(
                f"Format: {fmt}\n"
                f"Size: {_human_size(details.size_bytes)}\n"
                f"Sample ID: {details.id}"
            )
            meta.setObjectName("ActionMeta")
            layout.addWidget(meta)

        buttons = QHBoxLayout()
        self._add_button = QPushButton("Add")
        self._add_button.setObjectName("ActionAddButton")
        self._add_button.clicked.connect(self._handle_add)
        self._remove_button = QPushButton("Remove")
        self._remove_button.setObjectName("ActionRemoveButton")
        self._remove_button.clicked.connect(self._handle_remove)
        self._close_button = QPushButton("Close")
        self._close_button.setObjectName("ActionCloseButton")
        self._close_button.clicked.connect(self.reject)
        buttons.addWidget(self._add_button)
        buttons.addWidget(self._remove_button)
        buttons.addWidget(self._close_button)
        layout.addLayout(buttons)

    def _handle_add(self) -> None:
        if self._details is not None:
            self._on_add(self._details.id)
        self.accept()

    def _handle_remove(self) -> None:
        if self._details is not None:
            self._on_remove(self._details.id)
        self.accept()


class HelpDialog(QDialog):
    """Modal-style help dialog listing every keyboard shortcut."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpDialog")
        self.setWindowTitle("Keyboard Shortcuts")

        layout = QVBoxLayout(self)

        table = QTableWidget(len(SHORTCUT_HELP), 2)
        table.setObjectName("HelpTable")
        table.setHorizontalHeaderLabels(["Key(s)", "Action"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        for row, (keys, action) in enumerate(SHORTCUT_HELP):
            table.setItem(row, 0, QTableWidgetItem(keys))
            table.setItem(row, 1, QTableWidgetItem(action))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        self._table = table

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        box.accepted.connect(self.accept)
        layout.addWidget(box)

    @property
    def table(self) -> QTableWidget:
        return self._table


class CommandPaletteDialog(QDialog):
    """Minimal command palette: a filter field over a static action list.

    *actions* maps a display label to a zero-arg callback. Activating an entry
    (Return / double-click) runs its callback and closes the palette.
    """

    def __init__(self, actions: dict[str, Callable[[], None]], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CommandPaletteDialog")
        self.setWindowTitle("Command Palette")
        self._actions = dict(actions)

        layout = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setObjectName("PaletteFilter")
        self._filter.setPlaceholderText("Type to filter actions…")
        layout.addWidget(self._filter)

        self._list = QListWidget()
        self._list.setObjectName("PaletteList")
        for label in self._actions:
            QListWidgetItem(label, self._list)
        if self._list.count():
            self._list.setCurrentRow(0)
        layout.addWidget(self._list)

        self._filter.textChanged.connect(self._on_filter)
        self._filter.returnPressed.connect(self._activate_current)
        self._list.itemActivated.connect(self._on_item_activated)
        self._list.itemDoubleClicked.connect(self._on_item_activated)

    @property
    def list_widget(self) -> QListWidget:
        return self._list

    @property
    def filter_field(self) -> QLineEdit:
        return self._filter

    def _on_filter(self, text: str) -> None:
        needle = text.strip().lower()
        first_visible: int | None = None
        for row in range(self._list.count()):
            item = self._list.item(row)
            visible = needle in item.text().lower()
            item.setHidden(not visible)
            if visible and first_visible is None:
                first_visible = row
        if first_visible is not None:
            self._list.setCurrentRow(first_visible)

    def _activate_current(self) -> None:
        item = self._list.currentItem()
        if item is not None and not item.isHidden():
            self._run(item.text())

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        self._run(item.text())

    def _run(self, label: str) -> None:
        callback = self._actions.get(label)
        self.accept()
        if callback is not None:
            callback()

    def trigger(self, label: str) -> None:
        """Programmatic activation of an action by label (used by tests)."""
        self._run(label)


class CommandDialog(QDialog):
    """Vim-style command input and output dialog.

    Shows a command input field (with '/' prefix) and displays command output
    in a text area. Supports command history and tab completion.
    """

    def __init__(self, interpreter: CommandInterpreter | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CommandDialog")
        self.setWindowTitle("Command")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self._interpreter = interpreter or CommandInterpreter()
        self._history: list[str] = []
        self._history_pos = -1

        layout = QVBoxLayout(self)

        # Command input
        input_layout = QHBoxLayout()
        self._prompt_label = QLabel("/")
        self._prompt_label.setObjectName("CommandPrompt")
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._prompt_label.setFont(font)
        input_layout.addWidget(self._prompt_label)

        self._input = QLineEdit()
        self._input.setObjectName("CommandInput")
        self._input.setFont(font)
        self._input.setPlaceholderText("Type command (e.g., man, help, commands)...")
        input_layout.addWidget(self._input)

        layout.addLayout(input_layout)

        # Output area
        output_label = QLabel("Output:")
        output_label.setObjectName("CommandOutputLabel")
        layout.addWidget(output_label)

        self._output = QTextEdit()
        self._output.setObjectName("CommandOutput")
        self._output.setReadOnly(True)
        self._output.setFont(font)
        layout.addWidget(self._output)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Connect signals
        self._input.returnPressed.connect(self._execute_command)

        # Show welcome message
        self._show_output(
            "Command Mode\n\n"
            "Type a command and press Return. Try:\n"
            "  man          - Show user manual\n"
            "  commands     - List all commands\n"
            "  help         - Alias for man\n\n"
            "Press Escape to close."
        )

        # Focus input
        self._input.setFocus()

    def _execute_command(self) -> None:
        """Execute the command from input field."""
        cmd_text = self._input.text().strip()
        if not cmd_text:
            return

        # Add '/' prefix if not present
        if not cmd_text.startswith("/"):
            cmd_text = f"/{cmd_text}"

        # Add to history
        if cmd_text not in self._history:
            self._history.append(cmd_text)
        self._history_pos = len(self._history)

        # Execute
        result = self._interpreter.execute(cmd_text)

        # Display output
        output_lines = [f"$ {cmd_text}", ""]
        if result.error:
            output_lines.append(f"ERROR: {result.error}")
        else:
            output_lines.append(result.output)

        self._show_output("\n".join(output_lines))

        # Clear input
        self._input.clear()

    def _show_output(self, text: str) -> None:
        """Display text in output area."""
        self._output.setPlainText(text)
        # Scroll to top
        cursor = self._output.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self._output.setTextCursor(cursor)

    def set_initial_command(self, cmd: str) -> None:
        """Pre-fill the input with a command (without '/' prefix)."""
        self._input.setText(cmd)
        self._input.selectAll()


class SettingsDialog(QDialog):
    """Application settings with audio output controls under the I/O tab."""

    def __init__(
        self,
        on_audio_output_changed=None,
        settings=None,
        device_provider=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("Settings")
        self._on_audio_output_changed = on_audio_output_changed
        self._settings = settings
        if device_provider is None:
            from ..audio.devices import list_output_devices

            device_provider = list_output_devices
        self._device_provider = device_provider

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setObjectName("SettingsTabs")
        layout.addWidget(tabs)

        io_page = QWidget()
        io_page.setObjectName("SettingsIoPage")
        io_layout = QVBoxLayout(io_page)
        output_group = QGroupBox("Audio Output")
        output_group.setObjectName("AudioOutputGroup")
        form = QFormLayout(output_group)

        self._audio_output = QComboBox()
        self._audio_output.setObjectName("AudioOutputMode")
        device_error = None
        try:
            devices = self._device_provider()
        except Exception as exc:  # noqa: BLE001 - display backend discovery errors
            devices = ()
            device_error = str(exc) or exc.__class__.__name__
        if devices:
            self._audio_output.addItem(
                "System Default Output",
                AudioOutputMode.SYSTEM_DEFAULT.value,
            )
            for device in devices:
                default_marker = " — system default" if device.is_system_default else ""
                self._audio_output.addItem(
                    f"{device.name} ({device.host_api}, {device.max_output_channels} ch)"
                    f"{default_marker}",
                    f"device:{device.index}",
                )
        self._audio_output.addItem("None", AudioOutputMode.DISABLED.value)
        current = load_audio_output_selection(settings)
        current_data = current.mode.value
        if current.mode is AudioOutputMode.SPECIFIC_DEVICE:
            current_data = f"device:{current.device_index}"
        selected_index = self._audio_output.findData(current_data)
        if selected_index < 0:
            selected_index = self._audio_output.findData(AudioOutputMode.DISABLED.value)
        self._audio_output.setCurrentIndex(selected_index)
        form.addRow("Output device:", self._audio_output)

        self._audio_output_description = QLabel()
        self._audio_output_description.setObjectName("AudioOutputDescription")
        self._audio_output_description.setWordWrap(True)
        form.addRow("", self._audio_output_description)
        self._audio_output.currentIndexChanged.connect(self._update_audio_description)
        self._update_audio_description()
        if device_error:
            discovery_error = QLabel(f"Device discovery failed: {device_error}")
            discovery_error.setObjectName("AudioDeviceError")
            discovery_error.setWordWrap(True)
            form.addRow("", discovery_error)
        io_layout.addWidget(output_group)
        io_layout.addStretch(1)
        tabs.addTab(io_page, "I/O")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setObjectName("SettingsButtons")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def audio_output_combo(self) -> QComboBox:
        return self._audio_output

    def _save(self) -> None:
        value = str(self._audio_output.currentData())
        if value.startswith("device:"):
            selection = AudioOutputSelection(
                AudioOutputMode.SPECIFIC_DEVICE,
                int(value.split(":", 1)[1]),
            )
        else:
            selection = AudioOutputSelection(AudioOutputMode(value))
        save_audio_output_selection(selection, self._settings)
        if self._on_audio_output_changed is not None:
            self._on_audio_output_changed(selection)
        self.accept()

    def _update_audio_description(self) -> None:
        value = str(self._audio_output.currentData())
        if value == AudioOutputMode.DISABLED.value:
            text = "No audio output device will be used."
        elif value == AudioOutputMode.SYSTEM_DEFAULT.value:
            text = "Follows the output device selected by the operating system."
        else:
            text = "Routes playback directly to the selected audio output device."
        self._audio_output_description.setText(text)
