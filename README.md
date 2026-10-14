# Sample Manager

Sample Manager is a Python CLI for indexing a sample library, searching and tagging samples, building saved arrangements, and exporting them into hardware-friendly folder structures.

## Requirements

- Python 3.10+
- `typer` and `pyyaml` at runtime
- `PySide6` at runtime for the desktop GUI (installed automatically)
- NumPy, soundfile, and sounddevice for WAV analysis and playback (installed automatically)

## Install

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development:

```bash
source .venv/bin/activate
pip install -e .[dev]
```

After activating the virtualenv, the `sampleman` command is available on your
shell path. If you open a new terminal, activate the environment again:

```bash
cd /path/to/sample_manager
source .venv/bin/activate
```

## First Run

Initialize the user config and example profiles:

```bash
sampleman init
```

This creates `~/.sample_manager/config.yaml` and `~/.sample_manager/profiles/` if they do not already exist.

## Launching the app

Running `sampleman` with no subcommand launches the **Qt desktop GUI** (this is
also what `python -m sample_manager` does):

```bash
source .venv/bin/activate
sampleman        # launches the Qt GUI
sampleman gui    # explicit — same as above
```

Use the **Library** picker above the workspace to switch between indexed
folders. **Add Folder…** chooses and scans a new sample folder; **Rescan** picks
up newly added files and removes entries for files deleted from the active
folder. The window stays responsive during a scan and shows the counts when it
finishes. The selected folder becomes the default for the next launch and for
CLI commands.

For agent-driven or scripted GUI testing, launch the JSON simulation shell:

```bash
sampleman --simulation
sampleman gui --simulation
python -m sample_manager --simulation
```

To run the simulation shell without using your real config, database, or library,
use the disposable sample environment:

```bash
sampleman --simulation-temp
sampleman gui --simulation-temp
python -m sample_manager --simulation-temp
```

This creates a temporary SQLite database and a small temporary sample library for
the session, then deletes them when the shell exits.

The shell reads one JSON object per line from stdin and writes one JSON response
per line to stdout. Example:

```json
{"event": "key", "key": "L"}
{"command": "snapshot"}
{"assert": "path", "relative": "drums"}
```

If you prefer the terminal, the legacy Textual TUI is still available:

```bash
sampleman tui    # launches the legacy Textual terminal UI
```

All the non-interactive subcommands documented below continue to work
regardless of which frontend you use.

Audio is routed to the operating system's default output device. Choose
**Application → Settings → I/O** to select **System Default Output**, any
available output-capable system audio device, or **None**; changes apply
immediately.

Playback shortcuts: **Space** pauses or resumes the current sample, or starts the
focused sample when idle; **Ctrl+Space** also resumes a paused sample. Search the
indexed library with **/**, type any filename or path fragment, then press
**Escape** to clear results or click outside the field to return to browser
shortcuts. While search has focus, **Space** still controls playback and
**Shift+Space** inserts a space into a multi-word query. Drag an indexed Browser
sample into **Stage** to add it. Typing a query does not interrupt the current
sample; press **Enter**, **Down**, or click a result to audition it.

> **Screenshots:** GUI screenshots are pending — they can't be captured in the
> current headless CI environment and will be added once a display-backed
> capture is available.

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

### Selection (Stage in the GUI)
Selection is a persistent working buffer of sample IDs. The GUI calls this **Stage**, following the
Git-style workflow: collect samples in Stage before adding or committing them to an Arrangement.

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
sampleman config show
sampleman config show --json
```

Validate config paths:

```bash
sampleman config validate
sampleman config validate --strict
```

Add or edit config values:

```bash
sampleman config set db_path ~/.sample_manager/sample_manager.sqlite3
sampleman config add-root /path/to/samples
sampleman config set-default /path/to/samples
```

Scan a library root:

```bash
sampleman scan /path/to/samples
sampleman scan /path/to/samples --rescan
sampleman scan /path/to/samples --fast
```

If a library was scanned before `.wave` support was added, use **Rescan** in the
GUI or scan that root again from the CLI to index those files. The GUI searches
indexed samples in the active library root.

Check indexed library status:

```bash
sampleman status
```

Browse and search samples:

```bash
sampleman browse
sampleman browse --json
sampleman search drum
sampleman search --path packs/kicks --tag kick
sampleman search --sort mtime --page 2 --page-size 50
```

Manage tags:

```bash
sampleman tag add 12 kick
sampleman tag remove 12 kick
sampleman tag list 12
sampleman tag bulk --from-search drum --add percussion
sampleman tag alias add kick k
sampleman tag parent add kick drum
```

Work with profiles:

```bash
sampleman profile list
sampleman profile show default-monolithic
sampleman export-profile list
sampleman export-profile show mpc-live
```

Create and manage arrangements:

```bash
sampleman arrangement list
sampleman arrangement create my-kit --profile default-monolithic --from-search kick
sampleman arrangement show my-kit
sampleman arrangement add my-kit --from-selection
sampleman arrangement remove my-kit --ids 12,15
sampleman arrangement preview my-kit --export-profile mpc-live
```

Selection buffer:

```bash
sampleman selection add --ids 12,15
sampleman selection add --from-search kick
sampleman selection list
sampleman selection remove --ids 12
sampleman selection clear
```

Export and revert:

```bash
sampleman export my-kit --to /tmp/export --export-profile mpc-live --confirm
sampleman export my-kit --to /tmp/export --export-profile mpc-live --dry-run
sampleman revert --export-id 1 --confirm
sampleman revert --export-id 1 --dry-run
```

## Files

- Config: `~/.sample_manager/config.yaml`
- SQLite database: `~/.sample_manager/sample_manager.sqlite3`
- Profiles: `~/.sample_manager/profiles/`

## Output

- Human-readable table output is the default.
- Add `--json` where supported for machine-readable output.

## Notes

- `sampleman export` and `sampleman revert` require `--confirm` unless you use `--dry-run`.
- Tags are resolved case-insensitively by name, shorthand, or alias.
- Tag search expands through descendants in the inheritance graph.

## Usage Example

This example shows a complete workflow from a fresh setup to export and revert.

```bash
# 1. Initialize local config and profiles
sampleman init

# 2. Point Sample Manager at a library root
sampleman config add-root /path/to/sample-library
sampleman config set-default /path/to/sample-library

# 3. Scan the library into SQLite
sampleman scan /path/to/sample-library

# 4. Search for samples and inspect the results
sampleman search kick --json

# 5. Add matching samples to the selection buffer
sampleman selection add --from-search kick
sampleman selection list

# 6. Add tags to selected samples if needed
sampleman tag add 12 kick
sampleman tag bulk --from-search kick --add drum

# 7. Create an arrangement from the selection buffer
sampleman arrangement create my-kit --profile default-monolithic --from-selection

# 8. Review the arrangement
sampleman arrangement show my-kit
sampleman arrangement preview my-kit --export-profile mpc-live

# 9. Export the arrangement to a target directory
sampleman export my-kit --to /tmp/sample-export --export-profile mpc-live --confirm

# 10. Revert the export if needed
sampleman revert --export-id 1 --confirm
```
