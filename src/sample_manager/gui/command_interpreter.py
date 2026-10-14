"""Vim-style command interpreter for GUI commands.

Commands are prefixed with '/' similar to vim's ':' command mode. This module
provides the command registry, parser, and built-in commands like /man for help.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CommandResult:
    """Result of executing a command."""

    success: bool
    output: str
    error: str | None = None


@dataclass(frozen=True)
class CommandDef:
    """Definition of a registered command."""

    name: str
    handler: Callable[[list[str]], CommandResult]
    description: str
    usage: str | None = None
    aliases: tuple[str, ...] = ()


class CommandInterpreter:
    """Command interpreter for vim-style commands in the GUI.

    Usage:
        interpreter = CommandInterpreter()
        interpreter.register(CommandDef(
            name="example",
            handler=lambda args: CommandResult(True, "OK"),
            description="Example command",
        ))
        result = interpreter.execute("/example arg1 arg2")
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandDef] = {}
        self._register_builtin_commands()

    def register(self, cmd: CommandDef) -> None:
        """Register a command definition."""
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._commands[alias] = cmd

    def execute(self, input_text: str) -> CommandResult:
        """Execute a command from user input.

        Args:
            input_text: User input, expected to start with '/'

        Returns:
            CommandResult with success status, output, and optional error
        """
        if not input_text.startswith("/"):
            return CommandResult(
                success=False,
                output="",
                error="Commands must start with '/'",
            )

        # Parse command and arguments
        parts = input_text[1:].strip().split()
        if not parts:
            return CommandResult(
                success=False,
                output="",
                error="No command specified",
            )

        cmd_name = parts[0]
        args = parts[1:]

        # Look up command
        cmd = self._commands.get(cmd_name)
        if not cmd:
            return CommandResult(
                success=False,
                output="",
                error=f"Unknown command: {cmd_name}",
            )

        # Execute
        try:
            return cmd.handler(args)
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=f"Command error: {e}",
            )

    def list_commands(self) -> list[CommandDef]:
        """List all registered commands (excluding aliases)."""
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)
        return sorted(result, key=lambda c: c.name)

    def get_completions(self, prefix: str) -> list[str]:
        """Get command name completions for a given prefix.

        Args:
            prefix: Partial command (may or may not include leading '/')

        Returns:
            List of matching command names with '/' prefix
        """
        if prefix.startswith("/"):
            prefix = prefix[1:]

        matches = []
        for cmd_name in self._commands:
            if cmd_name.startswith(prefix):
                matches.append(f"/{cmd_name}")

        return sorted(set(matches))

    def _register_builtin_commands(self) -> None:
        """Register built-in commands."""
        self.register(
            CommandDef(
                name="man",
                handler=self._cmd_man,
                description="Show the user manual",
                usage="/man [section]",
                aliases=("help", "h"),
            )
        )

        self.register(
            CommandDef(
                name="commands",
                handler=self._cmd_commands,
                description="List all available commands",
                usage="/commands",
                aliases=("cmds",),
            )
        )

    def _cmd_man(self, args: list[str]) -> CommandResult:
        """Show comprehensive user manual."""
        section = args[0] if args else "overview"

        manual_sections = {
            "overview": _MANUAL_OVERVIEW,
            "navigation": _MANUAL_NAVIGATION,
            "library": _MANUAL_LIBRARY,
            "selection": _MANUAL_SELECTION,
            "arrangement": _MANUAL_ARRANGEMENT,
            "tags": _MANUAL_TAGS,
            "export": _MANUAL_EXPORT,
            "shortcuts": _MANUAL_SHORTCUTS,
            "commands": _MANUAL_COMMANDS,
        }

        content = manual_sections.get(section)
        if not content:
            available = ", ".join(manual_sections.keys())
            return CommandResult(
                success=False,
                output="",
                error=f"Unknown manual section: {section}\nAvailable: {available}",
            )

        return CommandResult(success=True, output=content)

    def _cmd_commands(self, args: list[str]) -> CommandResult:
        """List all available commands."""
        commands = self.list_commands()
        lines = ["Available Commands:", ""]

        for cmd in commands:
            aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            usage_str = f"\n  Usage: {cmd.usage}" if cmd.usage else ""
            lines.append(f"/{cmd.name}{aliases_str}")
            lines.append(f"  {cmd.description}{usage_str}")
            lines.append("")

        return CommandResult(success=True, output="\n".join(lines))


# -- Manual Content --

_MANUAL_OVERVIEW = """
SAMPLE MANAGER — USER MANUAL

Sample Manager is a cross-platform tool for organizing, searching, and exporting
music sample libraries. It provides a fast keyboard-driven interface for browsing
samples, creating arrangements, and exporting them with hardware constraints.

SECTIONS:
  /man overview      - This overview
  /man navigation    - Navigation and keyboard shortcuts
  /man library       - Library scanning and browsing
  /man selection     - Working with the selection buffer
  /man arrangement   - Creating and managing arrangements
  /man tags          - Tagging and search
  /man export        - Exporting arrangements
  /man shortcuts     - Complete keyboard reference
  /man commands      - All available / commands

QUICK START:
  1. Scan a library: sampleman scan /path/to/samples
  2. Browse with J/K, preview with Space
  3. Add with A, remove with D
  4. Create arrangement: sampleman arrangement create "My Kit"
  5. Export: sampleman export "My Kit" /output/path

For CLI usage, run: sampleman --help
"""

_MANUAL_NAVIGATION = """
NAVIGATION

BROWSER (Library File Tree):
  J / K           - Move down / up
  H / L           - Collapse / expand directory
  Space           - Preview audio (if available)
  Return          - Open file action dialog
  /               - Focus search field
  ?               - Show help dialog
  Cmd+P           - Open command palette
  Esc             - Clear search or unfocus

FOCUS MANAGEMENT:
  Tab             - Cycle focus between panels
  Mouse click     - Focus clicked panel

DIALOGS:
  Esc             - Close dialog
  Return          - Activate/confirm
  Tab             - Move between fields
"""

_MANUAL_LIBRARY = """
LIBRARY MANAGEMENT

SCANNING:
  CLI: sampleman scan /path/to/library
  
  This indexes all audio files recursively. Re-running scan on the same path
  updates existing entries and adds new files.

LIBRARY ROOTS:
  Multiple library roots are supported. Each library root tracks its own set
  of samples by relative path.

BROWSING:
  - The browser shows the directory tree of indexed samples
  - Gray entries are directories
  - White entries are audio files
  - Use J/K or arrow keys to navigate
  - Use H/L to collapse/expand folders

SEARCH:
  - Press / to focus the search field
  - Type in the search field to filter by filename
  - Case-insensitive substring matching
  - Clear with Esc or by clearing the field
"""

_MANUAL_SELECTION = """
STAGE

Stage is the persistent holding area for samples you want to work with. It
survives across sessions; the underlying CLI/domain name remains Selection.

ADDING:
  A               - Add focused sample (in browser)
  Cmd+A           - Add all visible samples
  CLI: sampleman selection add --search "kick"

REMOVING:
  D               - Remove focused sample
  CLI: sampleman selection remove --ids 1,2,3

VIEWING STAGE:
  - The Stage panel shows all staged samples
  - Persisted in the database
  - Commit staged samples to the active Arrangement

CLEARING:
  CLI: sampleman selection clear
"""

_MANUAL_ARRANGEMENT = """
ARRANGEMENTS

Arrangements are saved collections of samples with export rules.

CREATING:
  CLI: sampleman arrangement create "My Kit" --profile default
       sampleman arrangement add "My Kit" --from-selection

VIRTUAL FOLDERS:
  Arrangements support virtual folder organization:
  - Folders are metadata only (no filesystem changes)
  - Organize samples hierarchically
  - Folder paths are prepended to export destinations
  
PROFILES:
  Arrangement profiles define naming templates and collision policies:
  - Template tokens: {category}, {pack}, {name}, {index}, etc.
  - Collision policies: fail, suffix, dedupe_hash

LISTING:
  CLI: sampleman arrangement list
  CLI: sampleman arrangement show "My Kit"
"""

_MANUAL_TAGS = """
TAGGING AND SEARCH

CREATING TAGS:
  CLI: sampleman tag create kick
  CLI: sampleman tag create "drum" --parent "percussion"

TAG HIERARCHY:
  - Tags can have parent-child relationships (DAG, no cycles)
  - Searching for a parent tag includes all descendants
  - Example: "drums" → "kicks", "snares", "hats"

APPLYING TAGS:
  CLI: sampleman tag apply kick --to-ids 1,2,3
  CLI: sampleman tag apply kick --to-search "808"

SEARCHING:
  CLI: sampleman search --tags kick,snare --name "dry"
  
  Search supports:
  - Tag filters (with inheritance)
  - Filename substring matching
  - Combining multiple criteria

ALIASES:
  Tags can have aliases for flexible searching:
  CLI: sampleman tag alias kick "bd" "bass-drum"
"""

_MANUAL_EXPORT = """
EXPORTING ARRANGEMENTS

Export copies/links samples to a destination with hardware constraints.

BASIC EXPORT:
  CLI: sampleman export "My Kit" /output/path
  
MODES:
  --mode copy     - Copy files (default, safe)
  --mode symlink  - Create symbolic links
  --mode move     - Move files (requires --confirm)

EXPORT PROFILES:
  Define constraints in ~/.sample_manager/profiles/:
  - max_depth: Maximum folder depth
  - max_filename_len: Maximum filename length
  - illegal_chars: Characters to sanitize
  - on_violation: autofix or fail

PREVIEW:
  CLI: sampleman arrangement preview "My Kit"
  
  Shows the export plan without executing.

HISTORY:
  All exports are recorded for revert:
  CLI: sampleman history list
  CLI: sampleman history revert <export-id> --confirm
"""

_MANUAL_SHORTCUTS = """
KEYBOARD SHORTCUTS

NAVIGATION:
  J / Down        - Next item
  K / Up          - Previous item
  H / Left        - Collapse directory
  L / Right       - Expand directory

ACTIONS:
  Space           - Preview audio
  Return          - Open action dialog
  A               - Add
  D               - Remove
  Cmd+Return      - Commit Stage to the active Arrangement (Task 008)

GLOBAL:
  /               - Focus search field
  ?               - Help dialog
  Cmd+P           - Command palette
  Cmd+,           - Settings (macOS) / Ctrl+, (others)
  Cmd+A           - Select all visible
  Esc             - Clear/unfocus/close

PLATFORM NOTES:
  - "Cmd" on macOS = "Ctrl" on Windows/Linux
  - Some shortcuts auto-adapt via Qt StandardKey
"""

_MANUAL_COMMANDS = """
COMMAND MODE

Open command mode from the command palette with Cmd+P, then choose "Command Mode".
Commands still use a leading slash once the command dialog is open.

AVAILABLE COMMANDS:
  /man [section]  - Show user manual
  /help           - Alias for /man
  /commands       - List all commands
  /cmds           - Alias for /commands

USING COMMANDS:
  1. Press Cmd+P
  2. Choose Command Mode
  3. Type command and press Return
  4. Output shown in dialog or status

COMPLETION:
  - Tab completion for command names (planned)
  - Type partial command to see matches

EXTENDING:
  Custom commands can be registered programmatically via the
  CommandInterpreter API.
"""
