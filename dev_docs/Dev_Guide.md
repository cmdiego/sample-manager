# Sample Manager - Developer Guide

## Table of Contents

1. [Quick Start](#quick-start)
2. [Installation & Setup](#installation--setup)
3. [Running the CLI](#running-the-cli)
4. [Shell Completion (Tab Autocomplete)](#shell-completion-tab-autocomplete)
5. [CLI Commands Reference](#cli-commands-reference)
6. [Configuration System](#configuration-system)
7. [Development Workflow](#development-workflow)
8. [Testing](#testing)
9. [Project Structure](#project-structure)
10. [Phase 1 Features](#phase-1-features)
11. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Initialize Sample Manager
sample init

# 3. View your configuration
sample config show

# 4. Add a library root (replace with your sample directory)
sample config add-root ~/Music/Samples --set-default

# 5. Validate configuration
sample config validate
```

---

## Installation & Setup

### Prerequisites

- Python 3.10+
- pip

### Install Dependencies

The project uses a virtual environment with dependencies already installed. If you need to reinstall:

```bash
# Create virtual environment (if needed)
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install package in development mode
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Check that the CLI is available
sample --help

# Check Python module works
python -m sample_manager --help
```

---

## Running the CLI

### Method 1: CLI Command (Recommended)

Once installed, use the `sample` command directly:

```bash
source .venv/bin/activate
sample --help
```

### Method 2: Python Module

Run as a Python module:

```bash
source .venv/bin/activate
python -m sample_manager --help
```

### Method 3: Direct Python Execution

For development/debugging:

```bash
source .venv/bin/activate
python src/sample_manager/cli.py --help  # Won't work - use methods above
```

---

## Shell Completion (Tab Autocomplete)

Sample Manager includes **automatic shell completion** powered by Typer. This enables **Tab** to autocomplete commands, options, and arguments.

### Supported Shells

- **Bash**
- **Zsh**
- **Fish**
- **PowerShell**

### Install Completion

Run this command once to install completion for your current shell:

```bash
source .venv/bin/activate
sample --install-completion
```

**Output:**
```
Completion installed for zsh.
Restart your terminal or source your shell configuration file.
```

### After Installation

Restart your terminal or reload your shell configuration:

```bash
# For Zsh
source ~/.zshrc

# For Bash
source ~/.bashrc

# For Fish
source ~/.config/fish/config.fish
```

### Using Tab Completion

Once installed, you can use **Tab** to autocomplete:

```bash
# Autocomplete commands
sample <TAB>
# Shows: init  config

# Autocomplete subcommands
sample config <TAB>
# Shows: show  validate  set  add-root  remove-root  set-default

# Autocomplete options
sample config --<TAB>
# Shows: --help

# Autocomplete validate options
sample config validate --<TAB>
# Shows: --strict  --json  --help
```

### View Completion Script

To see the completion script without installing (useful for custom installations):

```bash
sample --show-completion
```

This outputs the completion script for your current shell, which you can copy or customize.

### Manual Installation

If automatic installation doesn't work, you can manually install the completion script:

**For Zsh:**
```bash
# Generate completion script
sample --show-completion > ~/.sample-completion.zsh

# Add to ~/.zshrc
echo "source ~/.sample-completion.zsh" >> ~/.zshrc

# Reload
source ~/.zshrc
```

**For Bash:**
```bash
# Generate completion script
sample --show-completion > ~/.sample-completion.bash

# Add to ~/.bashrc
echo "source ~/.sample-completion.bash" >> ~/.bashrc

# Reload
source ~/.bashrc
```

### Benefits

- **Faster command entry** - No need to remember exact command names
- **Discover options** - Tab shows available flags and options
- **Reduce typos** - Autocomplete ensures correct spelling
- **Learn as you go** - See available commands without checking help

### Troubleshooting Completion

**Completion not working after installation:**
```bash
# Make sure you reloaded your shell
source ~/.zshrc  # or ~/.bashrc

# Verify the completion file exists
ls -la ~/.zsh/completions/_sample  # Zsh
ls -la ~/.bash_completion.d/sample  # Bash

# Try reinstalling
sample --install-completion
```

**Command not found:**
```bash
# Ensure sample is in your PATH
which sample

# If not found, activate virtual environment
source .venv/bin/activate
```

---

## CLI Commands Reference

### `sample init`

Initialize Sample Manager by creating the configuration directory and file.

```bash
sample init
```

**What it does:**
- Creates `~/.sample_manager/` directory
- Creates `config.yaml` with default settings
- Idempotent (safe to run multiple times)

**Output:**
```
✓ Created config directory and file: /Users/you/.sample_manager/config.yaml
  Edit with: /Users/you/.sample_manager/config.yaml
  Add library roots with: sample config add-root <path>
```

---

### `sample config show`

Display the effective configuration with normalized paths.

```bash
# Human-readable format
sample config show

# JSON format
sample config show --json
```

**Human-readable output:**
```
Config file: /Users/you/.sample_manager/config.yaml

db_path: /Users/you/.sample_manager/sample_manager.sqlite3
library_roots: 1 configured
  - /Users/you/Music/Samples
default_library_root: /Users/you/Music/Samples

Defaults:
  export_mode: copy
  collision_policy: suffix
  on_violation: autofix
  preview_format: table
  confirmations: True
```

**JSON output:**
```json
{
  "db_path": "/Users/you/.sample_manager/sample_manager.sqlite3",
  "library_roots": [
    "/Users/you/Music/Samples"
  ],
  "default_library_root": "/Users/you/Music/Samples",
  "defaults": {
    "export_mode": "copy",
    "collision_policy": "suffix",
    "on_violation": "autofix",
    "preview_format": "table",
    "confirmations": true
  }
}
```

---

### `sample config validate`

Validate configuration paths and settings.

```bash
# Normal mode (warnings don't fail)
sample config validate

# Strict mode (warnings cause exit code 6)
sample config validate --strict

# JSON output
sample config validate --json
```

**Validation checks:**
- `db_path` parent directory exists (warning if missing)
- Each `library_roots` entry exists and is a directory (error if not)
- `default_library_root` exists, is a directory, and matches a configured root (warning if not)

**Exit codes:**
- `0` - Valid configuration
- `6` - Validation failed (strict mode only)

**JSON output structure:**
```json
{
  "ok": true,
  "exit_code": 0,
  "errors": [],
  "warnings": [],
  "checked": [
    "db_path",
    "library_roots",
    "default_library_root"
  ],
  "effective_config": { /* normalized config */ }
}
```

---

### `sample config set`

Set a configuration value using dot notation for nested keys.

```bash
sample config set <key> <value>
```

**Examples:**

```bash
# Set top-level key
sample config set db_path ~/.sample_manager/custom.sqlite3

# Set nested keys (dot notation)
sample config set defaults.export_mode symlink
sample config set defaults.collision_policy fail

# Boolean values (parsed automatically)
sample config set defaults.confirmations false
sample config set defaults.confirmations true

# Integer values
sample config set some_number 42

# Null values
sample config set optional_value null

# JSON lists
sample config set some_list '["a", "b", "c"]'
```

**Smart value parsing:**
- `"true"` / `"false"` → `bool`
- `"null"` → `None`
- `"42"` → `int`
- `"3.14"` → `float`
- `'["a", "b"]'` → `list` (JSON)
- Everything else → `str`

**Valid nested sections:**
- `defaults.*` - Default settings section

---

### `sample config add-root`

Add a library root directory.

```bash
sample config add-root <path> [--set-default]
```

**Examples:**

```bash
# Add a library root
sample config add-root ~/Music/Samples

# Add and set as default
sample config add-root ~/Music/Samples --set-default

# Add multiple roots
sample config add-root ~/Music/Samples
sample config add-root /Volumes/External/Samples
sample config add-root ~/Downloads/Free_Samples
```

**Requirements:**
- Path must exist
- Path must be a directory
- Path is normalized (~ expansion, absolute path)
- Idempotent (adding same path twice is safe)

**Output:**
```
✓ Added library root: /Users/you/Music/Samples
✓ Added and set as default: /Users/you/Music/Samples
✓ Library root already configured: /Users/you/Music/Samples
```

---

### `sample config remove-root`

Remove a library root directory from configuration.

```bash
sample config remove-root <path>
```

**Examples:**

```bash
sample config remove-root ~/Music/Samples
sample config remove-root /Volumes/External/Samples
```

**Behavior:**
- Removes the root from `library_roots`
- Clears `default_library_root` if it matched the removed path
- Path is normalized for comparison

**Output:**
```
✓ Removed library root: /Users/you/Music/Samples
✓ Removed library root and cleared default: /Users/you/Music/Samples
```

---

### `sample config set-default`

Set the default library root (must already be configured).

```bash
sample config set-default <path>
```

**Examples:**

```bash
sample config set-default ~/Music/Samples
```

**Requirements:**
- Path must already be in `library_roots`
- Use `sample config add-root <path> --set-default` to add and set in one command

**Output:**
```
✓ Set default library root: /Users/you/Music/Samples
```

---

## Configuration System

### Config File Location

**Default:** `~/.sample_manager/config.yaml`

**Cross-platform paths:**
- macOS/Linux: `/Users/you/.sample_manager/config.yaml`
- Windows: `C:\Users\you\.sample_manager\config.yaml`

### Config File Structure

```yaml
# Database location
db_path: "~/.sample_manager/sample_manager.sqlite3"

# Library roots (directories to scan for samples)
library_roots:
  - ~/Music/Samples
  - /Volumes/External/Samples

# Default library root (optional)
default_library_root: ~/Music/Samples

# Default settings
defaults:
  export_mode: copy              # copy | symlink | move
  collision_policy: suffix       # fail | suffix | dedupe_hash
  on_violation: autofix          # autofix | fail
  preview_format: table          # table | json
  confirmations: true            # true | false
```

### Path Normalization

All paths are normalized automatically:
- `~` expands to user home directory
- Environment variables are expanded (e.g., `$HOME`)
- Relative paths are converted to absolute paths
- Paths are resolved (symlinks followed)

**Example:**
```yaml
# In config.yaml
db_path: "~/.sample_manager/db.sqlite3"

# Normalized (on macOS)
db_path: "/Users/you/.sample_manager/db.sqlite3"
```

### Config Validation Rules

**db_path:**
- Parent directory should exist (WARNING if not)
- DB file itself doesn't need to exist yet

**library_roots:**
- Each entry must exist (ERROR if not)
- Each entry must be a directory (ERROR if not)

**default_library_root:**
- Must exist (WARNING if not)
- Must be a directory (WARNING if not)
- Should match one of the `library_roots` entries (WARNING if not)

### Config Mutation Policy

Per docs/02-persistence.md §2.2:

✅ **Safe operations:**
- `sample init` - Creates config if missing (idempotent)
- `sample config set` - Explicitly updates config
- `sample config add-root` - Explicitly adds library root
- `sample config remove-root` - Explicitly removes library root
- `sample config set-default` - Explicitly sets default

❌ **Never happens automatically:**
- Config is NEVER silently rewritten during normal operations
- Running commands like `validate` or `show` never modifies config
- Operational state goes in SQLite, not YAML (future phases)

---

## Development Workflow

### Making Code Changes

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Make your changes to src/sample_manager/*.py

# 3. Run tests
pytest tests/ -v

# 4. Test CLI manually
sample init
sample config show

# 5. Check specific functionality
pytest tests/test_config_init.py -v
```

### Adding New CLI Commands

1. Add command function to `src/sample_manager/cli.py`
2. Use `@app.command()` or `@config_app.command()` decorator
3. Add tests to `tests/test_cli.py`
4. Update this documentation

**Example:**

```python
@config_app.command("example")
def config_example(
    arg: str = typer.Argument(..., help="Description"),
    option: bool = typer.Option(False, "--flag", help="Description")
):
    """Command description."""
    try:
        # Implementation
        typer.echo("✓ Success message")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
```

### Adding New Config Functions

1. Add function to `src/sample_manager/config.py`
2. Add tests to appropriate test file
3. Use the function in CLI commands

---

## Testing

### Run All Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

**Expected output:**
```
============================= test session starts ==============================
collected 50 items

tests/test_cli.py::test_init_creates_config PASSED                       [  2%]
tests/test_cli.py::test_init_idempotent PASSED                           [  4%]
...
============================== 50 passed in 0.10s =============================
```

### Run Specific Test Files

```bash
# Config initialization tests
pytest tests/test_config_init.py -v

# Config validation tests
pytest tests/test_config_validate.py -v

# Config mutation tests
pytest tests/test_config_mutations.py -v

# CLI integration tests
pytest tests/test_cli.py -v
```

### Run Single Test

```bash
pytest tests/test_cli.py::test_init_creates_config -v
```

### Run with Coverage

```bash
pytest tests/ --cov=sample_manager --cov-report=term-missing
```

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_config_init.py            # Config initialization (6 tests)
├── test_config_validate.py        # Validation logic (13 tests)
├── test_config_mutations.py       # Config mutations (15 tests)
└── test_cli.py                    # CLI integration (16 tests)
```

**Total: 50 tests**

### Writing New Tests

Use the fixtures from `conftest.py`:

```python
def test_example(tmp_home, monkeypatch, runner, sample_library_root):
    """Test description."""
    # tmp_home: Temporary HOME directory
    # monkeypatch: pytest monkeypatch fixture
    # runner: Typer CliRunner for testing CLI
    # sample_library_root: Temporary sample directory
    
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
```

---

## Project Structure

```
sample_manager/
├── .venv/                         # Virtual environment
├── src/
│   └── sample_manager/            # Main package (src layout)
│       ├── __init__.py            # Package metadata
│       ├── __main__.py            # Entry point (python -m)
│       ├── exit_codes.py          # Exit code constants
│       ├── config.py              # Config management (338 lines)
│       └── cli.py                 # CLI commands (304 lines)
├── tests/                         # Test suite
│   ├── conftest.py                # Shared fixtures
│   ├── test_config_init.py        # Config init tests
│   ├── test_config_validate.py    # Validation tests
│   ├── test_config_mutations.py   # Mutation tests
│   └── test_cli.py                # CLI integration tests
├── docs/                          # Project documentation
│   ├── 00-vision.md               # Vision & invariants
│   ├── 01-data-model.md           # Data model (future phases)
│   ├── 02-persistence.md          # Config & persistence
│   ├── 03-cli.md                  # CLI specification
│   ├── 04-arrangement.md          # Arrangements (future)
│   ├── 05-export-revert.md        # Export/revert (future)
│   └── 06-ops-safety.md           # Safety principles
├── dev_docs/                      # Developer documentation
│   └── Dev_Guide.md               # This file!
├── config.example.yaml            # Example configuration
├── pyproject.toml                 # Project configuration
└── README.md                      # Project README
```

### Key Modules

**exit_codes.py** (15 lines)
- Defines exit code constants
- `SUCCESS`, `ERROR_GENERAL`, `ERROR_INVALID_ARGS`, `ERROR_CONFIG_VALIDATION`, etc.

**config.py** (338 lines)
- `ValidationResult` - Structured validation result dataclass
- `get_default_config_template()` - Default config template
- `ensure_config_exists()` - Create config if missing
- `load_config()` / `save_config()` - YAML I/O
- `normalize_config()` - Path expansion and normalization
- `validate_config()` - Config validation with warnings/errors
- `parse_config_value()` - Smart value parsing (bool/int/float/etc)
- `set_nested_key()` - Dot notation key setting
- `add_library_root()` / `remove_library_root()` - Root management
- `set_default_library_root()` - Set default root

**cli.py** (304 lines)
- Typer CLI application
- 7 commands: `init`, `config show/validate/set/add-root/remove-root/set-default`
- Error handling and exit codes
- Human-readable and JSON output formats

---

## Phase 1 Features

### ✅ Implemented

**Configuration System:**
- YAML-based configuration file
- Path normalization (~ expansion, env vars, absolute paths)
- Idempotent initialization
- Never silently rewrites user config

**Validation:**
- Structured validation results with JSON envelope
- db_path parent validation (warn-only)
- library_roots validation (error if invalid)
- default_library_root validation (warn if mismatch)
- Strict mode (warnings → errors)

**CLI Commands:**
- `sample init` - Initialize config
- `sample config show [--json]` - Display config
- `sample config validate [--strict] [--json]` - Validate config
- `sample config set <key> <value>` - Set config values
- `sample config add-root <path> [--set-default]` - Add library root
- `sample config remove-root <path>` - Remove library root
- `sample config set-default <path>` - Set default root

**Smart Features:**
- Dot notation for nested keys (`defaults.export_mode`)
- Smart value parsing (bool/int/float/null/JSON)
- Cross-platform path handling (pathlib)
- JSON output for all commands (scriptable)

**Testing:**
- 50 tests with 100% pass rate
- Unit tests for pure functions
- Integration tests for CLI commands
- Test isolation (no real filesystem pollution)

### ❌ Not Yet Implemented (Future Phases)

- Database schema (SQLite)
- Library scanning
- Sample indexing/tagging
- Search functionality
- Arrangements
- Export/revert operations
- Filesystem operations (copy/symlink/move)
- Audit logging

---

## Troubleshooting

### CLI Command Not Found

```bash
# Error: command not found: sample
```

**Solution:**
```bash
# Make sure virtual environment is activated
source .venv/bin/activate

# Reinstall package
pip install -e ".[dev]"

# Verify installation
which sample
sample --help
```

### Config Not Found

```bash
# Error: Config not found: /Users/you/.sample_manager/config.yaml
```

**Solution:**
```bash
# Initialize Sample Manager first
sample init

# Verify config was created
ls -la ~/.sample_manager/
cat ~/.sample_manager/config.yaml
```

### Validation Errors

```bash
# Error: library_root does not exist: /path/to/samples
```

**Solution:**
```bash
# Check if the directory exists
ls -d /path/to/samples

# If not, create it or use a different path
mkdir -p /path/to/samples

# Or remove the invalid root
sample config remove-root /path/to/samples

# Add a valid root
sample config add-root ~/Music/Samples
```

### Test Failures

```bash
# Some tests fail with permission errors
```

**Solution:**
```bash
# Tests use temporary directories, shouldn't touch real ~/.sample_manager
# If tests fail, check for:

# 1. Correct Python version (3.10+)
python --version

# 2. All dependencies installed
pip install -e ".[dev]"

# 3. Run tests with verbose output
pytest tests/ -v -s

# 4. Run specific failing test to debug
pytest tests/test_cli.py::test_init_creates_config -v -s
```

### Path Not Normalized

```bash
# Issue: Config shows "~" instead of full path
```

**Solution:**
This is expected in the config file itself. When you use `sample config show`, paths are normalized:

```bash
# Config file (YAML)
db_path: "~/.sample_manager/db.sqlite3"

# Normalized output (sample config show)
db_path: "/Users/you/.sample_manager/db.sqlite3"
```

### Import Errors

```bash
# Error: ModuleNotFoundError: No module named 'sample_manager'
```

**Solution:**
```bash
# Make sure virtual environment is activated
source .venv/bin/activate

# Install package in development mode
pip install -e ".[dev]"

# Verify installation
python -c "import sample_manager; print(sample_manager.__version__)"
```

---

## Common Workflows

### Daily Development

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Make changes to code

# 3. Run tests
pytest tests/ -v

# 4. Test CLI manually
sample config show
```

### Setting Up a New Sample Library

```bash
# 1. Initialize (if not already done)
sample init

# 2. Add your sample directories
sample config add-root ~/Music/Samples
sample config add-root /Volumes/External/Samples
sample config add-root ~/Downloads/Free_Samples

# 3. Set one as default
sample config set-default ~/Music/Samples

# 4. Verify configuration
sample config show
sample config validate
```

### Changing Configuration

```bash
# View current config
sample config show

# Change export mode
sample config set defaults.export_mode symlink

# Disable confirmations
sample config set defaults.confirmations false

# Change collision policy
sample config set defaults.collision_policy fail

# Verify changes
sample config show --json | jq '.defaults'
```

### Scripting with JSON Output

```bash
# Get config as JSON and parse with jq
sample config show --json | jq '.library_roots[]'

# Validate and check status programmatically
result=$(sample config validate --json)
echo $result | jq '.ok'
echo $result | jq '.errors[]'

# Check exit codes
sample config validate --strict
echo $?  # 0 = success, 6 = validation failed
```

---

## Exit Codes Reference

| Code | Name | Description | When Used |
|------|------|-------------|-----------|
| 0 | SUCCESS | Command succeeded | All successful operations |
| 1 | ERROR_GENERAL | Unexpected error | General exceptions |
| 2 | ERROR_INVALID_ARGS | Invalid arguments | Missing config, bad paths |
| 3 | ERROR_SAFETY_REFUSAL | Safety check failed | Missing --confirm (future) |
| 4 | ERROR_CONSTRAINT_VIOLATION | Constraint violated | Export constraint failures (future) |
| 5 | ERROR_PARTIAL_OPERATION | Partial success | Partial revert/export (future) |
| 6 | ERROR_CONFIG_VALIDATION | Config validation failed | `validate --strict` with warnings/errors |

**Usage in scripts:**

```bash
#!/bin/bash

sample config validate --strict
if [ $? -eq 0 ]; then
    echo "Config is valid"
else
    echo "Config validation failed"
    exit 1
fi
```

---

## Resources

### Documentation
- **Vision**: `docs/00-vision.md` - Project vision and invariants
- **Data Model**: `docs/01-data-model.md` - Entity definitions (future)
- **Persistence**: `docs/02-persistence.md` - Config and database design
- **CLI**: `docs/03-cli.md` - CLI specification
- **Arrangements**: `docs/04-arrangement.md` - Arrangement system (future)
- **Export/Revert**: `docs/05-export-revert.md` - Export operations (future)
- **Safety**: `docs/06-ops-safety.md` - Safety principles

### External Resources
- **Typer Documentation**: https://typer.tiangolo.com/
- **PyYAML Documentation**: https://pyyaml.org/wiki/PyYAMLDocumentation
- **pytest Documentation**: https://docs.pytest.org/

---

## Contributing

### Before Making Changes

1. Read the relevant docs in `docs/`
2. Check Phase 1 scope boundaries (this guide)
3. Run existing tests to ensure they pass
4. Write tests for new functionality

### Code Style

- Use type hints where appropriate
- Follow existing naming conventions
- Keep functions pure where possible
- Document complex logic with comments
- Add docstrings to public functions

### Testing Requirements

- All new features must have tests
- Maintain 100% test pass rate
- Use fixtures from `conftest.py`
- Test both success and error cases
- Test CLI commands end-to-end

---

## Quick Reference Card

```bash
# Essential Commands
sample init                                    # Initialize config
sample config show                             # View config
sample config validate                         # Validate config
sample config add-root ~/path --set-default    # Add library root
sample config set key value                    # Set config value

# JSON Output
sample config show --json                      # Config as JSON
sample config validate --json                  # Validation as JSON

# Development
pytest tests/ -v                               # Run all tests
pytest tests/test_cli.py -v                    # Run CLI tests
sample --help                                  # Show help
```

---

**Last Updated**: Phase 1 Implementation Complete
**Version**: 0.1.0
**Status**: Production Ready ✅
