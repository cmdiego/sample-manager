# CLI Surface

## 1) Command philosophy
- CLI is a thin layer over services.
- Most commands support:
  - --library-root (defaults from config)
  - --json for machine output
  - --dry-run (where applicable)

Executable name (placeholder): `sample`

## 2) Core commands (MVP)

### Init / Config
- `sample init`
  - Creates `~/.sample_manager/` and `config.yaml` if missing (idempotent).
  - Does not overwrite an existing config.
- `sample config validate [--strict] [--json]`
  - Validates paths from config:
    - db_path parent directory exists (may create parent dir if safe)
    - each library_roots entry exists and is a directory
    - default_library_root (if set) exists and is a directory
    - default_library_root should match one normalized library_roots entry (warn if not)
  - Default behavior: warnings do not fail the command.
  - `--strict` exits non-zero if any validation error exists.
- `sample config show [--json]`
  - Prints the effective configuration after normalization (expanded ~, env vars).
- `sample config set <key> <value>`
  - Explicitly updates config (may rewrite YAML).
  - Example keys:
    - db_path
    - defaults.export_mode
    - defaults.preview_format
    - defaults.confirmations
    - defaults.strict_paths
- `sample config add-root <path> [--set-default]`
  - Normalizes and adds a library root (must exist and be a directory).
- `sample config remove-root <path>`
  - Removes a library root by normalized match.
- `sample config set-default <path>`
  - Sets default_library_root to an existing configured root.

Notes:
- Config validation SHOULD run automatically before executing other commands.
  - If invalid paths are found:
    - default: warn and proceed with valid paths only
    - strict mode (defaults.strict_paths or --strict): exit non-zero

### Library
- `sample scan <path> [--rescan] [--fast]`
- `sample status`
- `sample browse [--page N --page-size M] [--sort name|mtime|size]`
- `sample search [--name <glob|regex>] [--tag <tag>] [--category <cat>] [--pack <pack>] [--bpm 120-130] [--key Cm]`

### Tags
- `sample tag add <sample-id> <tag>`
- `sample tag remove <sample-id> <tag>`
- `sample tag bulk --from-search "<query>" --add <tag> [--remove <tag>]`

### Profiles
- `sample profile list`
- `sample profile show <profile-name>`
- `sample export-profile list`
- `sample export-profile show <name>`

### Arrangements
- `sample arrangement list`
- `sample arrangement create <name> --profile <profile-name> [--from-search "<query>"] [--from-ids <id,id,...>]`
- `sample arrangement add <name> --from-search "<query>" [--ids <...>]`
- `sample arrangement remove <name> --ids <...> [--from-search "<query>"]`
- `sample arrangement preview <name> [--export-profile <name>] [--format table|json]`

### Export / Revert
- `sample export <arrangement-name> --to <export-dir> --export-profile <name> [--mode copy|symlink|move] [--confirm]`
- `sample export last`
- `sample revert --export-id <id> [--confirm] [--continue-on-error]`
- `sample revert last [--confirm]`

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
