# docs/03-cli.md
# CLI Surface

## 1) Command philosophy
- CLI is a thin layer over services.
- Most commands support:
  - --library-root (defaults from config)
  - --json for machine output
  - --dry-run (where applicable)

Executable name: `sampleman` (see `pyproject.toml [project.scripts]`).

Running `sampleman` with **no subcommand** launches the **Qt desktop GUI**
(browser). All commands below are the non-interactive CLI surface.

### Frontends
- `sampleman gui`
  - Launches the Qt desktop GUI explicitly (identical to running `sampleman`
    with no subcommand, and to `python -m sample_manager`).
- `sampleman tui`
  - Launches the legacy Textual terminal UI. Retained as a fallback until the
    cross-platform Qt packaging is validated.

## 2) Core commands (MVP)

### Init / Config
- `sampleman init`
  - Creates `~/.sample_manager/` and `config.yaml` if missing (idempotent).
  - Does not overwrite existing config.yaml.
- `sampleman config validate [--strict] [--json]`
  - Validates configured paths.
  - Default: warn and continue (exit code 0).
  - Strict: fail with exit code 6 if errors exist.
- `sampleman config show [--json]`
  - Shows effective config with normalized paths.

### Library
- `sampleman scan <path> [--rescan] [--fast]`
- `sampleman status`
- `sampleman browse [--page N --page-size M] [--sort name|mtime|size]`
- `sampleman search ...`
  - By name pattern, path, tags, etc. (phased in later)

### Tags (UPDATED semantics)
- `sampleman tag add <sample-id> <tag>`
- `sampleman tag remove <sample-id> <tag>`
- `sampleman tag bulk --from-search "<query>" --add <tag> [--remove <tag>]`

Tag resolution rules (Phase 2 DB update):
- Tag lookup is case-insensitive and may resolve via (in this order if needed):
  1) tag.name_norm
  2) tag.shorthand_norm
  3) tag_alias.alias_norm
- Tag soft delete:
  - tag.is_hidden=1 means tag is hidden from default list/resolve unless include_hidden=true.
- Tag inheritance:
  - tag_parent edges define a DAG (child -> parent).
  - Searching/filtering by a tag expands to include descendant tags (parent matches descendants only).
  - Cycles are forbidden (cycle check before inserting an edge).

### Profiles
- `sampleman profile list`
- `sampleman profile show <name>`
- `sampleman export-profile list`
- `sampleman export-profile show <name>`

### Arrangements
- `sampleman arrangement list`
- `sampleman arrangement create <name> --profile <profile-name> [--from-search "<query>"] [--from-ids <id,id,...>]`
- `sampleman arrangement add <name> --from-search "<query>" [--ids <...>]`
- `sampleman arrangement remove <name> --ids <...> [--from-search "<query>"]`
- `sampleman arrangement preview <name> [--export-profile <name>] [--format table|json]`

### Export / Revert
- `sampleman export <arrangement-name> --to <export-dir> --export-profile <name> [--mode copy|symlink|move] [--confirm]`
- `sampleman revert --export-id <id> [--confirm] [--continue-on-error]`
- `sampleman revert last [--confirm]` (optional if supported)

## 3) Exit codes (suggested)
- 0 success
- 1 unexpected error
- 2 invalid arguments / config missing
- 3 safety refusal (needs --confirm)
- 4 constraint violation (on_violation=fail)
- 5 partial revert / partial export
- 6 config validation failed (strict mode)

## 4) Output contracts
- Table output is default for humans.
- JSON output is stable for scripts:
  - commands include `--json` to print structured payloads.