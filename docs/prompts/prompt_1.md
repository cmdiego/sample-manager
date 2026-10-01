Task (Phase 1): Implement Sample Manager scaffolding + config system + CLI commands.

You are Claude Sonnet 4.5 running in OpenCode. You are implementing a new Python project named “Sample Manager” (CLI-first). The canonical specification is in the repo docs; treat docs as the source of truth and do NOT invent requirements.

Read these files first:
- docs/02-persistence.md (config init + validation policy)
- docs/03-cli.md (Init/Config CLI commands + exit codes)
- docs/06-ops-safety.md (safety/confirmations principles where relevant)

PHASE 1 GOAL (only this phase):
Implement the repo scaffolding + config system + init/validate CLI surface. Do NOT implement DB schema, scanning, search, arrangements, export, or revert yet.

Repository constraints / expectations:
- Use “src layout”: source code must live under src/sample_manager/
- Use Typer for CLI
- Use YAML for config (human-edited)
- Config file location per docs: ~/.sample_manager/config.yaml (cross-platform aware design, but macOS is fine for now)
- Program must NOT silently rewrite an existing config.yaml during normal operations
- When config exists, program MUST validate configured paths (docs/02 §2.4)

Required CLI commands (from docs/03):
1) sampleman init
   - Creates ~/.sample_manager/ and config.yaml if missing (idempotent)
   - Must not overwrite existing config
2) sampleman config validate [--strict] [--json]
   - Validates paths:
     - db_path parent directory exists (may create parent dir if safe)
     - each library_roots entry exists and is a directory
     - default_library_root (if set) exists and is a directory
     - default_library_root should match a normalized library_roots entry (warn if not)
   - Default behavior: warn and continue; does not fail
   - --strict: fail if any validation errors exist
   - Exit code for strict validation failure must be 6 (per docs/03)
3) sampleman config show [--json]
   - Prints the effective normalized config (expanded ~, env vars, absolute paths)
4) (If present in docs/03 already) also implement:
   - sampleman config set <key> <value>
   - sampleman config add-root <path> [--set-default]
   - sampleman config remove-root <path>
   - sampleman config set-default <path>
   If these are not in docs/03, skip them.

Config template (from docs/02) must be used when creating config:
- db_path: "~/.sample_manager/sample_manager.sqlite3"
- library_roots: []
- default_library_root: null
- defaults: export_mode, collision_policy, on_violation, preview_format, confirmations
(Optional) defaults.strict_paths can exist if you need it, but do not break docs.

Implementation guidance (keep minimal):
- Create these modules:
  - src/sample_manager/exit_codes.py (define constants including ERR_CONFIG_VALIDATION=6)
  - src/sample_manager/config.py (ConfigLoader + validation report)
  - src/sample_manager/cli.py (Typer app)
  - src/sample_manager/__main__.py (python -m sample_manager works)
- Return validation as a structured object:
  - warnings: list[str]
  - errors: list[str]
  - normalized_config: dict (for --json show)
- For --json output, print stable JSON to stdout.

Testing (required):
- Add pytest tests under tests/:
  - Missing config → sampleman init creates config file with expected keys
  - Config validate:
    - with invalid library_root emits warnings/errors as expected
    - strict mode returns exit code 6
  - Config show outputs normalized paths (at least expanduser on db_path)
Use tmp dirs and monkeypatch HOME so tests do not touch the real ~/.sample_manager.

Deliverables:
- All code in src/sample_manager/
- Tests in tests/
- Ensure `pip install -e ".[dev]"` works and `sampleman --help` runs (configure pyproject.toml if needed).
- Keep changes tight to Phase 1 scope.

Output format:
- Summarize files created/modified.
- Provide any commands to run tests and verify CLI.
