"""CLI commands for Sample Manager.

Typer-based CLI implementation per docs/03-cli.md.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import typer

from . import config as config_module
from . import exit_codes
from .db import Db
from .migrations import apply_migrations

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

# Profile subcommand group (Phase 6)
profile_app = typer.Typer(
    name="profile",
    help="Arrangement profile commands"
)
app.add_typer(profile_app, name="profile")

# Export-profile subcommand group (Phase 6)
export_profile_app = typer.Typer(
    name="export-profile",
    help="Export profile commands"
)
app.add_typer(export_profile_app, name="export-profile")

# Arrangement subcommand group (Phase 7)
arrangement_app = typer.Typer(
    name="arrangement",
    help="Arrangement management commands"
)
app.add_typer(arrangement_app, name="arrangement")

# Selection subcommand group
selection_app = typer.Typer(
    name="selection",
    help="Selection buffer commands"
)
app.add_typer(selection_app, name="selection")

# Tag subcommand group (Phase 5)
tag_app = typer.Typer(
    name="tag",
    help="Tag management commands"
)
app.add_typer(tag_app, name="tag")

# Tag alias sub-subcommand group
tag_alias_app = typer.Typer(
    name="alias",
    help="Tag alias management commands"
)
tag_app.add_typer(tag_alias_app, name="alias")

# Tag parent sub-subcommand group
tag_parent_app = typer.Typer(
    name="parent",
    help="Tag parent (DAG) management commands"
)
tag_app.add_typer(tag_parent_app, name="parent")


@app.command()
def init():
    """
    Initialize Sample Manager (create config directory and file).
    
    Idempotent - safe to run multiple times.
    Also creates the profiles directory with example profile files.
    """
    from . import profiles as profiles_module

    try:
        config_path, created = config_module.ensure_config_exists()
        
        if created:
            typer.echo(f"✓ Created config directory and file: {config_path}")
            typer.echo(f"  Edit with: {config_path}")
            typer.echo(f"  Add library roots with: sample config add-root <path>")
        else:
            typer.echo(f"✓ Config already exists: {config_path}")

        # Create profiles directory + example files (idempotent)
        cfg = config_module.load_config(config_path)
        profiles_dir = profiles_module.get_profiles_dir(cfg)
        profiles_module.create_example_profiles(profiles_dir)
        typer.echo(f"✓ Profiles directory ready: {profiles_dir}")
    
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


def _get_db() -> Db:
    """Load config, resolve db_path, open DB, apply migrations.

    Shared helper for commands that need database access.
    Caller is responsible for closing the returned Db instance.

    Raises:
        typer.Exit: If config is missing.
    """
    config_path = config_module.get_config_path()
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True,
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)

    cfg = config_module.load_config()
    normalized = config_module.normalize_config(cfg)
    db_path = normalized.get("db_path")
    if not db_path:
        typer.echo("Error: db_path not set in config.", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)

    db = Db(db_path)
    db.connect()
    apply_migrations(db)
    return db


@app.command()
def scan(
    path: str = typer.Argument(..., help="Library root directory to scan"),
    rescan: bool = typer.Option(
        False, "--rescan", help="Prune samples deleted from disk"
    ),
    fast: bool = typer.Option(
        False, "--fast", help="Skip files with unchanged mtime and size"
    ),
):
    """
    Scan a library root directory for audio samples.

    Walks the directory tree, filters by common audio extensions,
    and persists sample metadata to the database.
    """
    from . import scanner as scanner_module

    db = _get_db()
    try:
        result = scanner_module.scan_library(
            db, path, rescan=rescan, fast=fast
        )
        typer.echo(
            f"Scanned {result.total_on_disk} files "
            f"(inserted: {result.inserted}, updated: {result.updated}, "
            f"skipped: {result.skipped}, pruned: {result.pruned})"
        )
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except NotADirectoryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


@app.command()
def status():
    """
    Show summary of the sample library.

    Displays counts of library roots and samples, with per-root breakdown.
    """
    from .repos.library_root_repo import LibraryRootRepo
    from .repos.sample_repo import SampleRepo

    db = _get_db()
    try:
        root_repo = LibraryRootRepo(db)
        sample_repo = SampleRepo(db)

        roots = root_repo.list_all()
        total_samples = sample_repo.count_all()

        typer.echo(f"Library roots: {len(roots)}")
        typer.echo(f"Total samples: {total_samples}")

        if roots:
            typer.echo("")
            for root in roots:
                count = sample_repo.count_by_root(root["id"])
                typer.echo(f"  {root['path']}  ({count} samples)")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


def _format_table(result) -> str:
    """Format a SearchResult as a human-readable table.

    Columns: id, filename, rel_path, ext, size_bytes, mtime_epoch
    """
    if not result.items:
        return "No samples found."

    headers = ["id", "filename", "rel_path", "ext", "size_bytes", "mtime_epoch"]
    # Compute column widths
    widths = {h: len(h) for h in headers}
    for item in result.items:
        for h in headers:
            val = str(item.get(h, ""))
            widths[h] = max(widths[h], len(val))

    # Build header line
    header_line = "  ".join(str(h).ljust(widths[h]) for h in headers)
    separator = "  ".join("-" * widths[h] for h in headers)

    lines = [header_line, separator]
    for item in result.items:
        row = "  ".join(str(item.get(h, "")).ljust(widths[h]) for h in headers)
        lines.append(row)

    # Pagination footer
    lines.append("")
    lines.append(
        f"Page {result.page} of {result.total_pages} "
        f"({result.total} total results)"
    )
    return "\n".join(lines)


@app.command()
def search(
    query: str = typer.Argument(None, help="Name pattern (shorthand for --name)"),
    name: str = typer.Option(None, "--name", "-n", help="Filter by filename pattern"),
    path: str = typer.Option(None, "--path", "-p", help="Filter by path fragment"),
    tag: list[str] = typer.Option(None, "--tag", "-t", help="Filter by tag (repeatable, AND logic)"),
    sort: str = typer.Option("name", "--sort", "-s", help="Sort by: name, mtime, size"),
    page: int = typer.Option(1, "--page", help="Page number (1-indexed)"),
    page_size: int = typer.Option(50, "--page-size", help="Results per page"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Search samples by name, path, or tags.

    QUERY is an optional positional argument that acts as shorthand for --name.
    Multiple --tag flags use AND logic (sample must match all tags).
    Tag filters expand to include descendant tags.
    """
    from .search import SearchEngine

    # Merge positional query into name if --name not provided
    effective_name = name if name is not None else query

    db = _get_db()
    try:
        engine = SearchEngine(db)
        result = engine.search(
            name=effective_name,
            path=path,
            tags=tag if tag else None,
            sort=sort,
            page=page,
            page_size=page_size,
        )

        if json_output:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            typer.echo(_format_table(result))

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


@app.command()
def browse(
    page: int = typer.Option(1, "--page", help="Page number (1-indexed)"),
    page_size: int = typer.Option(50, "--page-size", help="Results per page"),
    sort: str = typer.Option("name", "--sort", "-s", help="Sort by: name, mtime, size"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Browse all samples with pagination.

    Lists all samples in the library, sorted and paginated.
    """
    from .search import SearchEngine

    db = _get_db()
    try:
        engine = SearchEngine(db)
        result = engine.search(
            sort=sort,
            page=page,
            page_size=page_size,
        )

        if json_output:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            typer.echo(_format_table(result))

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


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


# ============================ Profile commands (Phase 6) ====================


def _get_profiles_dir() -> Path:
    """Load config and resolve the profiles directory.

    Shared helper for profile commands (no DB needed).
    """
    from . import profiles as profiles_module

    config_path = config_module.get_config_path()
    if not config_path.exists():
        typer.echo(
            f"Config not found: {config_path}\n"
            f"Run 'sample init' to create it.",
            err=True,
        )
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)

    cfg = config_module.load_config()
    return profiles_module.get_profiles_dir(cfg)


@profile_app.command("list")
def profile_list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all arrangement profiles."""
    from . import profiles as profiles_module

    try:
        profiles_dir = _get_profiles_dir()
        profiles = profiles_module.load_arrangement_profiles(profiles_dir)

        if json_output:
            payload = [p.to_dict() for p in profiles]
            print(json.dumps(payload, indent=2))
        else:
            if not profiles:
                typer.echo("No arrangement profiles found.")
                typer.echo(
                    f"  Add profiles to: "
                    f"{profiles_dir / profiles_module.ARRANGEMENT_PROFILES_FILENAME}"
                )
            else:
                typer.echo(f"Arrangement profiles ({len(profiles)}):\n")
                for p in profiles:
                    desc = f"  {p.description}" if p.description else ""
                    typer.echo(f"  {p.name}  [{p.layout_mode}]{desc}")

    except profiles_module.ProfileValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@profile_app.command("show")
def profile_show(
    name: str = typer.Argument(..., help="Profile name to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show details of an arrangement profile."""
    from . import profiles as profiles_module

    try:
        profiles_dir = _get_profiles_dir()
        profile = profiles_module.get_arrangement_profile(name, profiles_dir)

        if profile is None:
            typer.echo(f"Arrangement profile not found: {name}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)

        if json_output:
            print(json.dumps(profile.to_dict(), indent=2))
        else:
            typer.echo(f"Name:             {profile.name}")
            typer.echo(f"Description:      {profile.description or '(none)'}")
            typer.echo(f"Layout mode:      {profile.layout_mode}")
            typer.echo(f"Naming template:  {profile.naming_template}")
            typer.echo(f"Collision policy: {profile.collision_policy}")
            if profile.layout_rules:
                typer.echo(f"Layout rules:     {json.dumps(profile.layout_rules)}")
            else:
                typer.echo(f"Layout rules:     (none)")
            if profile.selection_defaults:
                typer.echo(
                    f"Selection defaults: {json.dumps(profile.selection_defaults)}"
                )

    except profiles_module.ProfileValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


# ========================= Export-profile commands (Phase 6) ================


@export_profile_app.command("list")
def export_profile_list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all export profiles."""
    from . import profiles as profiles_module

    try:
        profiles_dir = _get_profiles_dir()
        profiles = profiles_module.load_export_profiles(profiles_dir)

        if json_output:
            payload = [p.to_dict() for p in profiles]
            print(json.dumps(payload, indent=2))
        else:
            if not profiles:
                typer.echo("No export profiles found.")
                typer.echo(
                    f"  Add profiles to: "
                    f"{profiles_dir / profiles_module.EXPORT_PROFILES_FILENAME}"
                )
            else:
                typer.echo(f"Export profiles ({len(profiles)}):\n")
                for p in profiles:
                    typer.echo(
                        f"  {p.name}  "
                        f"[depth={p.max_depth}, "
                        f"filename={p.max_filename_len}, "
                        f"case={p.case_policy}]"
                    )

    except profiles_module.ProfileValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


@export_profile_app.command("show")
def export_profile_show(
    name: str = typer.Argument(..., help="Export profile name to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show details of an export profile."""
    from . import profiles as profiles_module

    try:
        profiles_dir = _get_profiles_dir()
        profile = profiles_module.get_export_profile(name, profiles_dir)

        if profile is None:
            typer.echo(f"Export profile not found: {name}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)

        if json_output:
            print(json.dumps(profile.to_dict(), indent=2))
        else:
            typer.echo(f"Name:             {profile.name}")
            typer.echo(f"Max depth:        {profile.max_depth}")
            typer.echo(f"Max filename len: {profile.max_filename_len}")
            typer.echo(f"Illegal chars:    {profile.illegal_chars}")
            typer.echo(
                f"Allowed charset:  {profile.allowed_charset or '(any)'}"
            )
            typer.echo(f"Replace char:     {profile.replace_char!r}")
            typer.echo(f"Case policy:      {profile.case_policy}")
            typer.echo(f"Path sep policy:  {profile.path_sep_policy}")
            typer.echo(f"On violation:     {profile.on_violation}")

    except profiles_module.ProfileValidationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)


# ============================= Arrangement commands ==========================

from .commands.arrangement_commands import register as register_arrangement_commands

register_arrangement_commands(
    app=app,
    arrangement_app=arrangement_app,
    selection_app=selection_app,
    get_db=_get_db,
    get_profiles_dir=_get_profiles_dir,
    format_table=_format_table,
)


# ============================= Tag commands (Phase 5) =======================


@tag_app.command("add")
def tag_add(
    sample_id: int = typer.Argument(..., help="Sample ID to tag"),
    tag: str = typer.Argument(..., help="Tag name (auto-created if new)"),
):
    """
    Add a tag to a sample.

    Resolves the tag by name, shorthand, or alias. If not found,
    creates a new tag automatically.
    Idempotent: re-adding an existing tag is a no-op.
    """
    from . import tag_service

    db = _get_db()
    try:
        result = tag_service.tag_sample(db, sample_id, tag)
        typer.echo(
            f"Tagged sample {sample_id} with '{result['name_display']}'"
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


@tag_app.command("remove")
def tag_remove(
    sample_id: int = typer.Argument(..., help="Sample ID to untag"),
    tag: str = typer.Argument(..., help="Tag name to remove"),
):
    """
    Remove a tag from a sample.

    The tag must exist (resolved by name, shorthand, or alias).
    """
    from . import tag_service

    db = _get_db()
    try:
        result = tag_service.untag_sample(db, sample_id, tag)
        typer.echo(
            f"Removed tag '{result['name_display']}' from sample {sample_id}"
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


@tag_app.command("list")
def tag_list(
    sample_id: int = typer.Argument(..., help="Sample ID to list tags for"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    List all tags on a sample.
    """
    from . import tag_service

    db = _get_db()
    try:
        tags = tag_service.list_sample_tags(db, sample_id)

        if json_output:
            payload = [
                {
                    "id": t["id"],
                    "name": t["name_display"],
                    "name_norm": t["name_norm"],
                }
                for t in tags
            ]
            print(json.dumps(payload, indent=2))
        else:
            if not tags:
                typer.echo(f"Sample {sample_id} has no tags.")
            else:
                typer.echo(f"Tags for sample {sample_id}:")
                for t in tags:
                    typer.echo(f"  {t['name_display']}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


@tag_app.command("bulk")
def tag_bulk(
    from_search: str = typer.Option(
        ..., "--from-search", help="Name pattern to search samples"
    ),
    add: Optional[list[str]] = typer.Option(
        None, "--add", help="Tag(s) to add (repeatable)"
    ),
    remove: Optional[list[str]] = typer.Option(
        None, "--remove", help="Tag(s) to remove (repeatable)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Bulk add/remove tags based on a search query.

    Uses the search query as a name pattern to find matching samples,
    then applies tag additions and removals.
    """
    from . import tag_service

    if not add and not remove:
        typer.echo("Error: provide at least one --add or --remove tag.", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)

    db = _get_db()
    try:
        result = tag_service.bulk_tag_from_search(
            db,
            from_search,
            add_tags=add or [],
            remove_tags=remove or [],
        )

        if json_output:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            typer.echo(f"Matched {result.samples_matched} samples")
            if result.tags_added:
                typer.echo(f"  Added tags: {', '.join(result.tags_added)}")
            if result.tags_removed:
                typer.echo(f"  Removed tags: {', '.join(result.tags_removed)}")
            typer.echo(
                f"  Operations: {result.attachments_made} attachments, "
                f"{result.detachments_made} detachments"
            )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


# ============================= Tag alias commands ===========================


@tag_alias_app.command("add")
def tag_alias_add(
    tag: str = typer.Argument(..., help="Tag name to add alias for"),
    alias: str = typer.Argument(..., help="Alias string"),
):
    """
    Add an alias for a tag.

    The alias must be globally unique (case-insensitive).
    """
    from . import tag_service

    db = _get_db()
    try:
        row = tag_service.add_tag_alias(db, tag, alias)
        typer.echo(
            f"Added alias '{row['alias_display']}' for tag (id={row['tag_id']})"
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except sqlite3.IntegrityError as e:
        typer.echo(f"Error: alias already exists — {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_CONSTRAINT_VIOLATION)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


@tag_alias_app.command("remove")
def tag_alias_remove(
    alias: str = typer.Argument(..., help="Alias string to remove"),
):
    """
    Remove a tag alias.
    """
    from . import tag_service

    db = _get_db()
    try:
        tag_service.remove_tag_alias(db, alias)
        typer.echo(f"Removed alias '{alias}'")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


# ============================= Tag parent commands ==========================


@tag_parent_app.command("add")
def tag_parent_add(
    child: str = typer.Argument(..., help="Child tag name"),
    parent: str = typer.Argument(..., help="Parent tag name"),
):
    """
    Add a parent edge in the tag DAG (child -> parent).

    Both tags must exist. Cycles are forbidden.
    """
    from . import tag_service

    db = _get_db()
    try:
        tag_service.add_tag_parent(db, child, parent)
        typer.echo(f"Added parent edge: '{child}' -> '{parent}'")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_CONSTRAINT_VIOLATION)
    except sqlite3.IntegrityError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_CONSTRAINT_VIOLATION)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()


@tag_parent_app.command("remove")
def tag_parent_remove(
    child: str = typer.Argument(..., help="Child tag name"),
    parent: str = typer.Argument(..., help="Parent tag name"),
):
    """
    Remove a parent edge from the tag DAG.

    Both tags must exist.
    """
    from . import tag_service

    db = _get_db()
    try:
        tag_service.remove_tag_parent(db, child, parent)
        typer.echo(f"Removed parent edge: '{child}' -> '{parent}'")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(exit_codes.ERROR_GENERAL)
    finally:
        db.close()
