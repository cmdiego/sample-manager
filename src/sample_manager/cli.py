"""CLI commands for Sample Manager.

Typer-based CLI implementation per docs/03-cli.md.
"""

import json
import sys

import typer

from . import config as config_module
from . import exit_codes

# Main app
app = typer.Typer(
    name="sample",
    help="Sample Manager - Music sample library management CLI",
    no_args_is_help=True
)

# Config subcommand group
config_app = typer.Typer(
    name="config",
    help="Configuration management commands"
)
app.add_typer(config_app, name="config")


@app.command()
def init():
    """
    Initialize Sample Manager (create config directory and file).
    
    Idempotent - safe to run multiple times.
    """
    try:
        config_path, created = config_module.ensure_config_exists()
        
        if created:
            typer.echo(f"✓ Created config directory and file: {config_path}")
            typer.echo(f"  Edit with: {config_path}")
            typer.echo(f"  Add library roots with: sample config add-root <path>")
        else:
            typer.echo(f"✓ Config already exists: {config_path}")
    
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@config_app.command("show")
def config_show(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """Display the effective configuration (with normalized paths)."""
    config_path = config_module.get_config_path()
    
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    
    try:
        config = config_module.load_config()
        normalized = config_module.normalize_config(config)
        
        if json_output:
            print(json.dumps(normalized, indent=2))
        else:
            # Human-readable output
            typer.echo(f"Config file: {config_path}\n")
            typer.echo(f"db_path: {normalized.get('db_path', 'NOT SET')}")
            typer.echo(f"library_roots: {len(normalized.get('library_roots', []))} configured")
            for root in normalized.get('library_roots', []):
                typer.echo(f"  - {root}")
            typer.echo(f"default_library_root: {normalized.get('default_library_root', 'NOT SET')}")
            typer.echo(f"\nDefaults:")
            for key, value in normalized.get('defaults', {}).items():
                typer.echo(f"  {key}: {value}")
    
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@config_app.command("validate")
def config_validate(
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero on warnings"
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON"
    )
):
    """
    Validate configuration paths and settings.
    
    Returns exit code 0 on success, 6 on validation failure (strict mode).
    """
    config_path = config_module.get_config_path()
    
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    
    try:
        config = config_module.load_config()
        result = config_module.validate_config(config, strict=strict)
        
        if json_output:
            print(json.dumps(result.to_json(), indent=2))
        else:
            # Human-readable output
            typer.echo(f"Validating: {config_path}\n")
            
            if result.errors:
                typer.echo("ERRORS:", err=True)
                for error in result.errors:
                    typer.echo(f"  ✗ {error}", err=True)
                typer.echo(err=True)
            
            if result.warnings:
                stream = sys.stderr if strict else sys.stdout
                typer.echo("WARNINGS:", file=stream, err=strict)
                for warning in result.warnings:
                    typer.echo(f"  ! {warning}", file=stream, err=strict)
                typer.echo(file=stream, err=strict)
            
            if result.ok:
                typer.echo("✓ Configuration valid")
            else:
                if strict:
                    typer.echo("✗ Validation failed (strict mode)", err=True)
                else:
                    typer.echo("⚠ Validation completed with warnings")
        
        raise typer.Exit(result.exit_code)
    
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (use dot notation for nested)"),
    value: str = typer.Argument(..., help="Value to set")
):
    """
    Set a configuration value.
    
    Examples:
    
      sample config set db_path ~/.sample_manager/db.sqlite3
      
      sample config set defaults.export_mode symlink
      
      sample config set defaults.confirmations false
    """
    config_path = config_module.get_config_path()
    
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    
    try:
        config = config_module.load_config()
        parsed_value = config_module.parse_config_value(value)
        config_module.set_nested_key(config, key, parsed_value)
        config_module.save_config(config)
        
        typer.echo(f"✓ Set {key} = {parsed_value}")
        typer.echo(f"  Type: {type(parsed_value).__name__}")
    
    except KeyError as e:
        typer.echo(f"Error: Invalid config key: {key}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@config_app.command("add-root")
def config_add_root(
    path: str = typer.Argument(..., help="Library root directory path"),
    set_default: bool = typer.Option(
        False,
        "--set-default",
        help="Also set as default library root"
    )
):
    """
    Add a library root directory.
    
    Path must exist and be a directory.
    """
    config_path = config_module.get_config_path()
    
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    
    try:
        config = config_module.load_config()
        updated_config, message = config_module.add_library_root(
            config, path, set_as_default=set_default
        )
        config_module.save_config(updated_config)
        
        typer.echo(f"✓ {message}")
    
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@config_app.command("remove-root")
def config_remove_root(
    path: str = typer.Argument(..., help="Library root directory path to remove")
):
    """Remove a library root directory from configuration."""
    config_path = config_module.get_config_path()
    
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    
    try:
        config = config_module.load_config()
        updated_config, message = config_module.remove_library_root(config, path)
        config_module.save_config(updated_config)
        
        typer.echo(f"✓ {message}")
    
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@config_app.command("set-default")
def config_set_default(
    path: str = typer.Argument(..., help="Library root to set as default")
):
    """
    Set the default library root.
    
    Path must already be configured in library_roots.
    """
    config_path = config_module.get_config_path()
    
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    
    try:
        config = config_module.load_config()
        updated_config, message = config_module.set_default_library_root(config, path)
        config_module.save_config(updated_config)
        
        typer.echo(f"✓ {message}")
    
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
