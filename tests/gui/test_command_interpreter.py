"""Tests for the vim-style command interpreter."""

import pytest

from sample_manager.gui.command_interpreter import (
    CommandDef,
    CommandInterpreter,
    CommandResult,
)


class TestCommandInterpreter:
    def test_execute_without_slash_prefix_fails(self):
        interp = CommandInterpreter()
        result = interp.execute("man")
        assert not result.success
        assert "must start with '/'" in result.error

    def test_execute_empty_command_fails(self):
        interp = CommandInterpreter()
        result = interp.execute("/")
        assert not result.success
        assert "No command specified" in result.error

    def test_execute_unknown_command_fails(self):
        interp = CommandInterpreter()
        result = interp.execute("/unknown")
        assert not result.success
        assert "Unknown command" in result.error

    def test_builtin_man_command(self):
        interp = CommandInterpreter()
        result = interp.execute("/man")
        assert result.success
        assert "SAMPLE MANAGER" in result.output
        assert "USER MANUAL" in result.output

    def test_man_with_section(self):
        interp = CommandInterpreter()
        result = interp.execute("/man navigation")
        assert result.success
        assert "NAVIGATION" in result.output
        assert "BROWSER" in result.output

    def test_man_unknown_section_fails(self):
        interp = CommandInterpreter()
        result = interp.execute("/man unknown")
        assert not result.success
        assert "Unknown manual section" in result.error

    def test_builtin_commands_command(self):
        interp = CommandInterpreter()
        result = interp.execute("/commands")
        assert result.success
        assert "Available Commands" in result.output
        assert "/man" in result.output
        assert "/commands" in result.output

    def test_alias_help_for_man(self):
        interp = CommandInterpreter()
        result = interp.execute("/help")
        assert result.success
        assert "SAMPLE MANAGER" in result.output

    def test_alias_h_for_man(self):
        interp = CommandInterpreter()
        result = interp.execute("/h")
        assert result.success
        assert "SAMPLE MANAGER" in result.output

    def test_alias_cmds_for_commands(self):
        interp = CommandInterpreter()
        result = interp.execute("/cmds")
        assert result.success
        assert "Available Commands" in result.output

    def test_list_commands_excludes_aliases(self):
        interp = CommandInterpreter()
        commands = interp.list_commands()
        command_names = [c.name for c in commands]
        
        # Should have main commands
        assert "man" in command_names
        assert "commands" in command_names
        
        # Should not list aliases as separate commands
        assert "help" not in command_names
        assert "h" not in command_names
        assert "cmds" not in command_names

    def test_get_completions_with_prefix(self):
        interp = CommandInterpreter()
        completions = interp.get_completions("/ma")
        assert "/man" in completions

    def test_get_completions_without_prefix(self):
        interp = CommandInterpreter()
        completions = interp.get_completions("ma")
        assert "/man" in completions

    def test_get_completions_multiple_matches(self):
        interp = CommandInterpreter()
        completions = interp.get_completions("/c")
        assert "/commands" in completions
        # May have other commands starting with 'c'

    def test_register_custom_command(self):
        interp = CommandInterpreter()
        
        def custom_handler(args):
            return CommandResult(True, f"Custom output: {' '.join(args)}")
        
        interp.register(CommandDef(
            name="custom",
            handler=custom_handler,
            description="A custom command",
        ))
        
        result = interp.execute("/custom arg1 arg2")
        assert result.success
        assert "Custom output: arg1 arg2" in result.output

    def test_register_command_with_aliases(self):
        interp = CommandInterpreter()
        
        def custom_handler(args):
            return CommandResult(True, "OK")
        
        interp.register(CommandDef(
            name="test",
            handler=custom_handler,
            description="Test command",
            aliases=("t", "tst"),
        ))
        
        # All should work
        assert interp.execute("/test").success
        assert interp.execute("/t").success
        assert interp.execute("/tst").success

    def test_command_handler_exception_caught(self):
        interp = CommandInterpreter()
        
        def failing_handler(args):
            raise ValueError("Test error")
        
        interp.register(CommandDef(
            name="fail",
            handler=failing_handler,
            description="Failing command",
        ))
        
        result = interp.execute("/fail")
        assert not result.success
        assert "Command error" in result.error
        assert "Test error" in result.error

    def test_all_manual_sections_accessible(self):
        """Ensure all documented manual sections can be accessed."""
        interp = CommandInterpreter()
        
        sections = [
            "overview", "navigation", "library", "selection",
            "arrangement", "tags", "export", "shortcuts", "commands"
        ]
        
        for section in sections:
            result = interp.execute(f"/man {section}")
            assert result.success, f"Section {section} should be accessible"
            assert len(result.output) > 100, f"Section {section} should have content"
