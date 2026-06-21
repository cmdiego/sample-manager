# Sample Manager

Sample Manager is a Python CLI for indexing a sample library, searching and tagging samples, building saved arrangements, and exporting them into hardware-friendly folder structures.

## Requirements

- Python 3.10+
- `typer` and `pyyaml` at runtime

## Install

From the project root:

```bash
pip install -e .
```

For development:

```bash
pip install -e .[dev]
```

## First Run

Initialize the user config and example profiles:

```bash
sample init
```

This creates `~/.sample_manager/config.yaml` and `~/.sample_manager/profiles/` if they do not already exist.

## Concepts

### Library Root
A library root is a folder you scan into the database. The scanner walks that directory recursively and indexes supported audio files.

### Sample
A sample is one audio file plus its indexed metadata. The database identifies a sample by the pair `(library_root_id, rel_path_norm)`.

### Tag
Tags are labels attached to samples. Tag lookup is case-insensitive and can resolve by:

1. tag name
2. tag shorthand
3. tag alias

Tags are soft-deleted, which means hidden tags stay in the database but are excluded from normal lookup and listing.

### Tag Aliases
An alias is an alternate name for a tag. Aliases are globally unique, case-insensitive, and point back to a single tag.

### Tag Parent
Tag parents define inheritance between tags. The relationship is `child -> parent`, and the graph must remain acyclic. Searching for a tag includes its descendants.

### Selection
Selection is a persistent working buffer of sample IDs. It is useful when you want to collect samples once and reuse that set for arrangement editing or other operations.

### Arrangement
An arrangement is a named saved selection of samples plus a chosen arrangement profile. It is the main unit you use when preparing an export.

### Arrangement Profile
An arrangement profile defines how sample names and folders are organized when an arrangement is previewed or exported. It controls layout mode, naming template, and collision policy.

### Export Profile
An export profile defines filesystem constraints for the target device or destination. It controls path depth, filename length, allowed characters, case policy, and what to do when a rule is violated.

### Export
Export takes an arrangement, renders a deterministic plan, and applies it to a target directory using `copy`, `symlink`, or `move`.

### Export Run and History
Every export attempt is recorded in SQLite. History stores the plan and execution results so a revert can use the recorded history instead of guessing.

## Common Commands

Show the effective config:

```bash
sample config show
sample config show --json
```

Validate config paths:

```bash
sample config validate
sample config validate --strict
```

Add or edit config values:

```bash
sample config set db_path ~/.sample_manager/sample_manager.sqlite3
sample config add-root /path/to/samples
sample config set-default /path/to/samples
```

Scan a library root:

```bash
sample scan /path/to/samples
sample scan /path/to/samples --rescan
sample scan /path/to/samples --fast
```

Check indexed library status:

```bash
sample status
```

Browse and search samples:

```bash
sample browse
sample browse --json
sample search drum
sample search --path packs/kicks --tag kick
sample search --sort mtime --page 2 --page-size 50
```

Manage tags:

```bash
sample tag add 12 kick
sample tag remove 12 kick
sample tag list 12
sample tag bulk --from-search drum --add percussion
sample tag alias add kick k
sample tag parent add kick drum
```

Work with profiles:

```bash
sample profile list
sample profile show default-monolithic
sample export-profile list
sample export-profile show mpc-live
```

Create and manage arrangements:

```bash
sample arrangement list
sample arrangement create my-kit --profile default-monolithic --from-search kick
sample arrangement show my-kit
sample arrangement add my-kit --from-selection
sample arrangement remove my-kit --ids 12,15
sample arrangement preview my-kit --export-profile mpc-live
```

Selection buffer:

```bash
sample selection add --ids 12,15
sample selection add --from-search kick
sample selection list
sample selection remove --ids 12
sample selection clear
```

Export and revert:

```bash
sample export my-kit --to /tmp/export --export-profile mpc-live --confirm
sample export my-kit --to /tmp/export --export-profile mpc-live --dry-run
sample revert --export-id 1 --confirm
sample revert --export-id 1 --dry-run
```

## Files

- Config: `~/.sample_manager/config.yaml`
- SQLite database: `~/.sample_manager/sample_manager.sqlite3`
- Profiles: `~/.sample_manager/profiles/`

## Output

- Human-readable table output is the default.
- Add `--json` where supported for machine-readable output.

## Notes

- `sample export` and `sample revert` require `--confirm` unless you use `--dry-run`.
- Tags are resolved case-insensitively by name, shorthand, or alias.
- Tag search expands through descendants in the inheritance graph.

## Usage Example

This example shows a complete workflow from a fresh setup to export and revert.

```bash
# 1. Initialize local config and profiles
sample init

# 2. Point Sample Manager at a library root
sample config add-root /path/to/sample-library
sample config set-default /path/to/sample-library

# 3. Scan the library into SQLite
sample scan /path/to/sample-library

# 4. Search for samples and inspect the results
sample search kick --json

# 5. Add matching samples to the selection buffer
sample selection add --from-search kick
sample selection list

# 6. Add tags to selected samples if needed
sample tag add 12 kick
sample tag bulk --from-search kick --add drum

# 7. Create an arrangement from the selection buffer
sample arrangement create my-kit --profile default-monolithic --from-selection

# 8. Review the arrangement
sample arrangement show my-kit
sample arrangement preview my-kit --export-profile mpc-live

# 9. Export the arrangement to a target directory
sample export my-kit --to /tmp/sample-export --export-profile mpc-live --confirm

# 10. Revert the export if needed
sample revert --export-id 1 --confirm
```
