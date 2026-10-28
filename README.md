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

## Continuous integration

GitHub Actions runs the full CLI, audio, Textual TUI, and offscreen Qt test suite
for pull requests into `main` and pushes to `main`. The matrix covers Python
3.10 and 3.14 on Linux, plus Python 3.14 on macOS and Windows. Tests install the
`dev` and `audio` extras and use generated fixtures; no display or audio device
is required. Each job uploads a JUnit report.

A separate **Package** check builds the source distribution and wheel, checks
their metadata, and verifies the installed wheel's CLI outside the checkout.
Distributions are available as workflow artifacts; CI does not publish releases.
The workflow can also be run manually from the Actions tab.

To run the same regression suite locally after installing the extras:

```bash
python -m pip install ".[dev,audio]"
QT_QPA_PLATFORM=offscreen python -m pytest -ra
```

On PowerShell, set `$env:QT_QPA_PLATFORM = "offscreen"` before running pytest.

## First Run

The GUI creates the user config and example profiles automatically on first
launch. Then choose **Add Folder…** in the Library toolbar to scan your first
sample folder.

In the TUI, press **F4 Add Folder** to enter or paste a sample-folder path.
Submitting a valid folder initializes missing config, profiles, and database
files, scans in the background, and selects the new library. Cancel leaves
configuration untouched.

For CLI setup, initialize those files explicitly:

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

The terminal workspace puts a compact waveform Preview above Browser and Stage.
Stage shows the selected sample count and total size in its header; the bottom
bar follows Browser, Stage, search, and waveform seeking modes. Short terminals
use a smaller preview to keep more sample rows visible.

For the keyboard-driven terminal interface:

```bash
sampleman tui
```

Press **`\`** (the leader key) or **F1** for a compact popup in the lower-right
corner. It shows the possible next keys, updating as you enter a command
sequence while the browser stays visible. Choose a group and then an action
using the displayed letters, arrow keys and **Enter**, or the mouse. For example,
**`\` → l → a** opens Add Folder. Each action shows its regular shortcut;
highlighting an unavailable action explains what is needed. The popup
stays open until you choose an action or close it. **Escape** returns to the
groups, then closes; **`\`** or **F1** closes immediately. Opening and canceling
preserves your search and cursor. Clicking outside also closes it.
Dialog text fields accept `\` normally;
paste a query if you need a literal backslash in search. **?** opens the full
shortcut reference, including waveform controls.

Directory navigation follows Vim in Browser and Stage: **h / Left** goes to
the parent, **j / Down** moves down, **k / Up** moves up, and **l / Right** opens
the focused folder. On a sample, **l / Right** keeps its action menu. Ascending
highlights the folder you just left; reentering a visited folder restores its
last focused item and scrolls it into view. If that item was removed, the cursor
falls back to the nearest remaining row. Newly entered Stage folders focus their
first actual child, allowing repeated **l** to descend through several levels.
**h** stops at the active pane’s root. **Tab** switches panes; **Escape** at Stage
root returns to Browser. The directory inspector opened with **i** also accepts
**hjkl** for tree navigation. In that directory tree, **Enter** toggles an indexed
sample in Stage, **a** adds it, and **d** removes it. **[✓]** marks staged samples;
additions use the currently open Stage folder. Enter on folders still expands
or collapses them. Search and dialog text fields accept these letters
as text; waveform navigation after **w** retains **h/l** for seeking.

Use **Ctrl+h/j/k/l** or **Ctrl+Left/Down/Up/Right** to focus the pane in
that direction. Left/right switch Browser and Stage; up focuses the shared
Preview; down returns to its originating pane. Movement stops at outer edges.
In Preview, **h/l** seek, **j/k** scroll sample details, **Enter** confirms a seek,
and **Escape** returns without seeking. **Tab** still switches Browser/Stage.

In the TUI, press **Tab** to switch between Browser and the selected-files
Stage. **j/k** or the arrow keys move in the active pane; **Return** or **d**
removes the highlighted Stage sample; **Return** opens a Stage folder. Press **r** to cycle indexed library
roots. The TUI opens the configured default root at startup, and Stage remains
available when switching roots. Press **F5** (or choose **Rescan Library** in the
command palette) to pick up added, changed, or removed files. Scanning runs in
the background and refreshes Browser, search results, and Stage when complete.
The current folder and focused sample are preserved when they still exist.

Use **F4 Add Folder** (also in the command palette) to index another library.
Paths may include spaces, `~`, or environment variables. The chosen library is
saved as the startup default after a successful scan; existing Stage items stay
selected when adding or switching libraries.

Stage supports persistent **virtual folders and subfolders**. Press **n** or
**F7** to create a folder; enter `Drums/Kicks` to create a nested path. Relative
paths start inside the open Stage folder; a leading `/` starts at Stage root.
Creating a folder opens it in Stage. Use **Tab** to return to Browser and add
samples with **Enter** or **a**; new selections go into the open Stage folder.
Adding an already-staged sample preserves its existing placement.

In Stage, **Enter**, **l** or **Right** opens a folder; **h** or **Left** returns to its parent,
and **m** moves the focused sample or folder to a destination path (`/` for
root). Missing destination folders are created automatically. **e** renames a
folder. **d** removes a sample from Stage or removes an empty virtual folder;
nonempty folders require moving their contents out first. **Escape** cancels a
folder dialog. The Stage footer shows the current destination path, and its
header totals include samples across all Stage folders and libraries.

Folders and sample placement survive restart and library switching. These
operations organize references and leave source audio files in place. The
shared CLI/GUI selection still contains all staged sample IDs. Creating or
adding an arrangement with `--from-selection` carries over the folder hierarchy;
arrangement preview and export use those folders. `sampleman selection clear`
clears both selections and virtual folders.

Press **F2** for **Settings**, or find Settings in the **Ctrl+P** command
palette. Choose an audio output device or disable playback, and turn automatic
audition on or off. **Save** applies the choices immediately and stores them in
the `tui` section of `config.yaml`; **Cancel** or **Escape** discards edits.
Settings also shows the active library and configuration/database locations.

Press **/** to search indexed samples across the active library, including
nested packs. Search matches filename, relative path, and tags; the activation
slash is not part of the query. Type or paste a query, use **Up/Down** to audition
results, and **Return** to toggle a sample in Stage. **Escape** or **Left** clears
search and restores the directory cursor. Deleting the query keeps search open.
**Space** controls playback; **Shift+Space** inserts a space in the query.
Relative folders distinguish results that share a filename.

Press **i** on a focused directory to inspect its contents in an expandable tree.
The listing includes files of every type and subdirectories. **Enter** or **Right**
expands a folder; **Left** collapses it or moves to its parent; **Escape**, **i**,
or **q** closes the inspector and preserves Browser/Stage state. Nested folders
load in the background when expanded. Symbolic links are listed as leaves.

Preview’s top-right **Sample details** panel prioritizes **Tempo**, **Key**,
**Genre**, and your assigned **Tags**, followed by available file tags, artist,
title, and album. Tempo/key/genre come from the sample’s embedded metadata;
missing values display **—** and are not guessed from the filename. Your tag
edits update the summary immediately. Scroll to additional summary fields when
needed. Press **i** on a sample for its full, scrollable metadata, including
custom fields, technical audio properties, artwork summaries, and separately
labeled library tags. **Escape** closes the view. Native metadata is read-only
and requires the optional `audio` extra (`pip install "sample-manager[audio]"`).

Press **F6** or **t** to manage tags on the focused sample in Browser or Stage,
or choose **Edit tags** from its action pane. Enter a tag name or existing alias
and press **Enter**/**Add**. Choose a listed tag and **Remove selected** to detach
it from this sample. Changes apply immediately; **Close** or **Escape** ends
editing. Preview shows the current tags, and active tag searches refresh after
each edit. Removing an attachment preserves the shared tag and other samples.

All the non-interactive subcommands documented below continue to work
regardless of which frontend you use.

In the GUI, audio is routed to the operating system's default output device. Choose
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

## v2 workspace and optional native audio

Browse, Search and Stage views are available from the top bar, **Alt+1/2/3**,
leader → v, or the command palette. Switching views preserves the search query
and shared Stage folders. **Tab** still switches Browser/Stage and **h/l** still
navigate directories. Wide terminals show folder/tag columns; use **Alt+Left**
to enter them, **Alt+Right/Left** to change column, **Enter** to apply and **Esc**
to return. Columns collapse below 100 characters. Tag choices include descendants.
Stored analysis supplies duration/LUFS summaries when available.

The bottom transport retains the playing sample independently of browsing focus.
It shows a full-width waveform, time and supported engine health fields. The
compact Preview keeps focused metadata and existing waveform seeking controls.
Transport updates during loading/playback and stops polling while idle.

**Stage view** adds Tag all, Arrange and confirmed Clear actions.
**Alt+4**, the Arrangements button or leader → s → r opens saved arrangements.
Choose an arrangement profile and name to save Stage with its virtual folders,
merge Stage into an existing arrangement, or remove a saved sample reference.
Choose an export profile and **Preview** to inspect destination paths. **Copy
export…** and history-based **Revert selected…** require confirmation. The TUI
copies source files and preserves them; existing CLI export modes remain available.
Configure profiles in the YAML files named by `profiles_dir` if the lists are empty.

**F2 Settings** now includes dark/light theme, engine, buffer frames, prefetch
depth and decoded cache size. Audio changes stop playback; visual changes apply
immediately. Existing configs remain readable. Shared `audio` keys take precedence
over legacy `tui` audio keys; saving retains unrelated configuration values:

```yaml
audio:
  engine: python           # python (default), auto, native
  audio_output: system_default
  buffer_frames: 1024      # 128, 256, 512, 1024 or 2048
  prefetch_depth: 3        # 0–10 neighbours per side
  cache_mb: 256            # 16–2048 MiB
tui:
  auto_audition: true
  theme: dark              # dark or light
  theme_tokens:            # optional colour overrides
    accent: "#638fba"
```

The optional Rust engine is built separately; see [engine/README.md](engine/README.md).
Install a local/CI `sample-manager-engine` wheel before selecting native. Once
published, the same package can be installed with `pip install "sample-manager[native]"`.
`auto` reports native failures and falls back to Python; explicit `native` reports
an actionable error. Qt keeps its existing Python player and output-device settings;
native Qt adoption remains deferred until the TUI v2 acceptance milestone.

Diagnostics use disposable engine instances, independently of a running frontend:

```sh
sampleman engine stats --engine python --backend null
sampleman engine bench /path/to/fixtures --engine native --backend null
```

`null` never opens an output device. Use `--backend device` for hardware checks.
Benchmarks report input-to-first-non-silent-buffer timing, not acoustic latency;
a first pass is not guaranteed cold disk. Native remains opt-in pending platform
CI and real-device latency/listening acceptance. Level matching and oversampled
true-peak analysis remain future work.

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

To make `kick` a sub-tag of `drums`, first create both tags by adding them
to samples with **t** in the TUI (or `sampleman tag add SAMPLE_ID TAG`). Then run:

```bash
sampleman tag parent add kick drums
```

The child comes first, then its parent. Parent relationships are currently
managed through the CLI; the TUI tag editor manages sample attachments.
`sampleman search --tag drums` includes descendants such as `kick`. The TUI’s
`/` search currently matches tag text directly.

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
