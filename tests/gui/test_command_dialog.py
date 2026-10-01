"""Tests for the CommandDialog widget."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sample_manager.gui.command_interpreter import CommandDef, CommandInterpreter, CommandResult
from sample_manager.gui.dialogs import CommandDialog


@pytest.fixture
def dialog(qtbot):
    """Create a CommandDialog for testing."""
    dlg = CommandDialog()
    qtbot.addWidget(dlg)
    return dlg


class TestCommandDialog:
    def test_dialog_creation(self, dialog):
        """Test dialog initializes properly."""
        assert dialog.windowTitle() == "Command"
        assert dialog.objectName() == "CommandDialog"

    def test_input_field_has_focus(self, dialog):
        """Test that input field gets focus on open."""
        dialog.show()
        QApplication.processEvents()
        assert dialog._input.hasFocus()

    def test_output_shows_welcome_message(self, dialog):
        """Test that welcome message is shown initially."""
        output_text = dialog._output.toPlainText()
        assert "Command Mode" in output_text
        assert "man" in output_text

    def test_execute_man_command(self, dialog, qtbot):
        """Test executing /man command."""
        dialog._input.setText("man")
        qtbot.keyPress(dialog._input, Qt.Key.Key_Return)
        
        output_text = dialog._output.toPlainText()
        assert "$ /man" in output_text
        assert "SAMPLE MANAGER" in output_text
        assert "USER MANUAL" in output_text

    def test_execute_commands_command(self, dialog, qtbot):
        """Test executing /commands command."""
        dialog._input.setText("commands")
        qtbot.keyPress(dialog._input, Qt.Key.Key_Return)
        
        output_text = dialog._output.toPlainText()
        assert "$ /commands" in output_text
        assert "Available Commands" in output_text

    def test_slash_prefix_added_automatically(self, dialog, qtbot):
        """Test that '/' is added if missing."""
        dialog._input.setText("help")
        qtbot.keyPress(dialog._input, Qt.Key.Key_Return)
        
        output_text = dialog._output.toPlainText()
        assert "$ /help" in output_text

    def test_empty_input_does_nothing(self, dialog, qtbot):
        """Test that empty input doesn't execute."""
        initial_output = dialog._output.toPlainText()
        dialog._input.setText("")
        qtbot.keyPress(dialog._input, Qt.Key.Key_Return)
        
        # Output should be unchanged
        assert dialog._output.toPlainText() == initial_output

    def test_error_displayed_for_unknown_command(self, dialog, qtbot):
        """Test that errors are displayed properly."""
        dialog._input.setText("unknown")
        qtbot.keyPress(dialog._input, Qt.Key.Key_Return)
        
        output_text = dialog._output.toPlainText()
        assert "ERROR:" in output_text
        assert "Unknown command" in output_text

    def test_input_cleared_after_execution(self, dialog, qtbot):
        """Test that input field is cleared after executing."""
        dialog._input.setText("man")
        qtbot.keyPress(dialog._input, Qt.Key.Key_Return)
        
        assert dialog._input.text() == ""

    def test_set_initial_command(self, dialog):
        """Test setting initial command pre-fills input."""
        dialog.set_initial_command("man overview")
        assert dialog._input.text() == "man overview"
        # Text should be selected
        assert dialog._input.hasSelectedText()

    def test_custom_interpreter(self, qtbot):
        """Test using custom interpreter with registered commands."""
        interp = CommandInterpreter()
        
        def custom_handler(args):
            return CommandResult(True, f"Custom: {' '.join(args)}")
        
        interp.register(CommandDef(
            name="test",
            handler=custom_handler,
            description="Test command",
        ))
        
        dialog = CommandDialog(interpreter=interp)
        qtbot.addWidget(dialog)
        
        dialog._input.setText("test foo bar")
        qtbot.keyPress(dialog._input, Qt.Key.Key_Return)
        
        output_text = dialog._output.toPlainText()
        assert "Custom: foo bar" in output_text

    def test_escape_closes_dialog(self, dialog, qtbot):
        """Test that Escape key closes the dialog."""
        dialog.show()
        qtbot.keyPress(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()

    def test_monospace_font_used(self, dialog):
        """Test that monospace font is used for command aesthetics."""
        font = dialog._input.font()
        assert font.styleHint() == font.StyleHint.TypeWriter
