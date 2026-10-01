<!--
## Sync Impact Report (REMOVE BEFORE COMMIT)

Version change: N/A (initial creation) → 1.0.0
Modified principles: None (first issuance)
Added sections:
  - Core Principles (5 principles)
  - Technology & Compatibility Standards
  - Development Workflow
  - Governance
Removed sections: None
Follow-up TODOs: None — all placeholders resolved from repo context.
-->

# Sample Manager Constitution

## Core Principles

### I. Non-Destructive First (NON-NEGOTIABLE)

All operations that modify, move, or delete files on disk MUST be non-destructive by default.
Concrete rules:

- Export operations MUST prefer `copy` or `symlink` over `move`; `move` and destructive ops
  MUST require an explicit user flag and a confirmation prompt.
- Every export run MUST produce a persisted manifest (`export_run` + `history_entry` tables)
  before any filesystem mutation begins, enabling full revert.
- Symlink strategy MUST degrade gracefully on platforms where symlinks are restricted
  (e.g., Windows without Developer Mode); fall back to copy, never silently skip.
- The `selection_sample` working buffer is ephemeral and non-destructive; it never modifies
  sample files or metadata on disk.

**Rationale**: Users' sample libraries are irreplaceable creative assets. A bug or misclick
MUST NOT result in data loss. Reversibility is the safety net that makes the tool trustworthy.

### II. Strict Layer Separation

The codebase MUST maintain its four-layer hierarchy: CLI → Services → Repos → DB.
Concrete rules:

- Repos (`repos/`) own all raw SQL. No SQL strings outside a repo class.
- Services (`services/`) own business logic. Services MUST NOT import from `gui/` or `tui/`.
- GUI widgets and TUI screens are presentation-only; they MUST NOT call `Db` directly or
  construct raw SQL.
- The Qt GUI (`gui/`) and legacy Textual TUI (`tui/`) both consume the shared service layer
  (`services/`). Code that could be shared between frontends MUST live in `services/`.
- Background work in the GUI MUST use `QRunnable` workers; no long-running ops on the Qt
  main thread.

**Rationale**: Layer violations create untestable, entangled code. Keeping SQL in repos and
business logic in services allows the test suite to cover behavior without a running UI.

### III. Test-First Development (NON-NEGOTIABLE)

New behaviour MUST have tests written before or alongside the implementation — never after.
Concrete rules:

- Every new repo method, service function, and CLI command MUST have corresponding pytest tests.
- Tests MUST use real in-memory SQLite (the `db` fixture from `tests/conftest.py`), not mocks
  of the database layer. Mocking the DB has previously caused mock/prod divergence.
- GUI tests MUST run offscreen: `QT_QPA_PLATFORM=offscreen pytest tests/gui/ -v`.
- CLI tests MUST isolate user config via the `tmp_home` fixture — never touch
  `~/.sample_manager` in tests.
- A PR MUST NOT be merged if existing tests are broken, and MUST NOT skip hooks to force a
  merge.

**Rationale**: The test suite is the primary safety net for a tool that mutates user data.
Real-DB integration tests catch schema/migration issues that mocked tests miss.

### IV. Schema Changes via Migrations Only

All database schema changes MUST go through the sequential migration system in `migrations.py`.
Concrete rules:

- Migrations are append-only and numbered sequentially. Existing migrations MUST NOT be
  edited after they have been applied to any environment.
- Every migration MUST be exercised by at least one test (via the shared `db` fixture, which
  applies all migrations on construction).
- SQLite PRAGMAs (`WAL` mode, `foreign_keys=ON`) MUST be applied on every connection via
  `db.py`; they MUST NOT be bypassed in tests or scripts.
- The canonical DDL and recursive CTE patterns in
  `docs/appendix-phase2-ddl-and-ctes.md` are authoritative; schema additions MUST be
  consistent with the documented data model.

**Rationale**: Sequential migrations are the single source of truth for schema evolution.
Diverging from the migration path leads to inconsistent production databases.

### V. Simplicity and YAGNI

The codebase MUST NOT accumulate speculative complexity.
Concrete rules:

- Features MUST NOT be implemented before they are explicitly required. Hypothetical future
  requirements do not justify adding abstractions today.
- Three similar lines of code are preferred over a premature helper. Abstract only when a
  concrete pattern has appeared at least three times across unrelated callsites.
- Error handling, fallbacks, and validation MUST NOT be added for scenarios that cannot
  happen given the current code paths and framework guarantees.
- Comments are written only when the *why* is non-obvious (hidden constraint, subtle
  invariant, workaround). Comments that describe *what* the code does MUST NOT be added.
- Audio dependencies (`numpy`, `soundfile`, `sounddevice`) are lazy-imported; they MUST NOT
  be imported at module load time to keep CLI startup fast for users without audio hardware.

**Rationale**: Complexity accretes faster than it is removed. Keeping scope tight makes the
codebase easier to navigate, test, and extend correctly.

## Technology & Compatibility Standards

The project targets these runtime constraints; deviations require an explicit constitution amendment:

- **Runtime**: Python 3.10+ (uses `match` statements and modern type hints).
- **GUI**: PySide6 (Qt6 bindings). No other GUI toolkit is introduced.
- **Terminal UI**: Textual (retained as `sampleman tui` fallback; removed only after
  cross-platform Qt packaging is validated on macOS, Windows, and Linux).
- **Database**: SQLite via the stdlib `sqlite3` module, wrapped by `db.py`. No ORM.
- **CLI framework**: Typer. All subcommands registered through `cli.py:app` or delegated
  via `commands/` modules.
- **Configuration**: YAML via PyYAML. Config stored at `~/.sample_manager/config.yaml`.
  Config MUST NOT be auto-mutated; only explicit `sampleman config *` commands may write it.
- **Paths**: `pathlib.Path` everywhere. String concatenation of paths is forbidden.
- **Exit codes**: Defined in `exit_codes.py`. CLI commands MUST use these codes consistently.

## Development Workflow

- **Entry point**: `sampleman` CLI and `python -m sample_manager` both invoke the Qt GUI
  by default. Subcommands `gui` and `tui` are explicit frontend selectors.
- **Feature lifecycle**: New features follow the Spec Kit workflow
  (`/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`).
- **Branching**: Feature work happens on dedicated branches; PRs target `main`.
- **Quality gates**: All `pytest tests/ -v` and `QT_QPA_PLATFORM=offscreen pytest tests/gui/ -v`
  MUST pass before a PR is merged.
- **Simulation mode**: GUI features MUST be verifiable via the JSON simulation shell
  (`sampleman --simulation` / `sampleman --simulation-temp`) before shipping.
- **Docs**: `docs/` holds original design specs. Functional behaviour described in docs takes
  precedence over ad-hoc implementation choices when there is a conflict.

## Governance

This constitution supersedes all informal agreements, chat instructions, and per-session
guidance. When in conflict, this document wins.

Amendment procedure:
1. Propose the amendment in a PR description, explaining what changes and why.
2. All five principles and both standards sections MUST remain internally consistent after
   the amendment; verify this before merging.
3. Run `/speckit-constitution` to produce an updated `constitution.md` with a Sync Impact
   Report; review the report and remove it before committing.
4. Bump the version according to semantic versioning (MAJOR for governance/principle
   redefinition, MINOR for additions, PATCH for clarifications).
5. Update `LAST_AMENDED_DATE`.

Versioning policy:
- **MAJOR**: Removal or backward-incompatible redefinition of a principle or non-negotiable rule.
- **MINOR**: New principle, section, or materially expanded guidance added.
- **PATCH**: Clarifications, wording improvements, typo fixes.

Compliance: Every PR MUST be reviewed against this constitution. Non-compliance is a blocker.
The Spec Kit command suite (`/speckit-*`) provides the runtime development guidance layer.

**Version**: 1.0.0 | **Ratified**: 2026-09-30 | **Last Amended**: 2026-09-30
