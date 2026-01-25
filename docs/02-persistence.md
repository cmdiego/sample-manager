## 2) Initialization & config mutation policy (IMPORTANT)

### 2.1 Create config on first run (safe auto-population)
If `~/.sample_manager/config.yaml` does not exist:
- Create the data directory (`~/.sample_manager/`)
- Write a default `config.yaml` template with safe defaults
- Do NOT add discovered library roots automatically
- Print a short message indicating the path created and how to edit it

Recommended explicit command:
- `sample init` — creates config + data dir if missing (idempotent)

Acceptable MVP behavior:
- If user runs any command and config is missing, tool may behave as if `sample init` was run (create defaults), but it must be visible (console note).

### 2.2 Never silently rewrite user config
After the config exists:
- The tool MUST NOT rewrite `config.yaml` automatically during normal operations (scan/export/revert).
- Config changes happen only via explicit user actions (e.g., `sample config set ...`, `sample config add-root ...`).
- Operational state MUST NOT be stored in YAML:
  - last export, selection buffers, history, scan results, etc. belong in SQLite.

### 2.3 What lives where
- YAML config: user preferences and defaults (paths, profile locations, default mode).
- SQLite: authoritative state (library index, tags, arrangements, exports, history).

### 2.4 Validate config paths when config already exists
On program start (or before executing any command), if `config.yaml` exists the program MUST validate configured paths.

Validation rules:
- Always normalize/expand:
  - expand `~` (user home)
  - expand environment variables (e.g., `$HOME`)
  - resolve to absolute paths where applicable
- `db_path`:
  - validate that the parent directory exists; if not, create it (safe) OR warn and continue (implementation choice).
  - do not create the DB file until first DB access.
- `library_roots`:
  - each entry must exist and be a directory.
  - invalid roots are reported.
- `default_library_root`:
  - if set, must exist, be a directory, and should match one entry in `library_roots` (after normalization).
  - if invalid, warn and treat as unset for that run.

Behavior on invalid paths:
- Default: WARN + continue using only valid paths.
- Optional strict mode (future):
  - `defaults.strict_paths: true` causes validation failures to exit non-zero.

Important:
- Validation MUST NOT mutate `config.yaml` automatically (no silent rewrites).
- If the user runs `sample config ...` commands, those commands may update YAML explicitly.

Suggested user-facing output:
- Print a concise warning summary listing invalid paths and how to fix them (edit config or use `sample config add-root ...`).
