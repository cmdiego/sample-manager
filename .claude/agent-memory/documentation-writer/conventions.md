# Documentation conventions & constraints

- "report" filename constraint: the sandbox blocks writing any file whose basename contains
  "report". Name summaries without it, e.g. `docs/reports/YYYY-MM-DD-session-summary.md`. The
  `docs/reports/` *directory* is fine; only the literal basename token is blocked.
- CLI entry point: the installed command is `sampleman` (`pyproject.toml [project.scripts]`),
  NOT `sample`. Running `sampleman` with no subcommand launches the Textual TUI.
- Do NOT rewrite these protected uses of "sample" when renaming the CLI: `sample_manager`
  (package), `sample-manager` (dist name), the `sample` DB table, `sample-id`, "Sample Manager",
  "sample library", "a sample", "sample upsert/indexes/metadata".
- Canonical CLI reference: `docs/03-cli.md` — keep it in sync with the real Typer app in
  `src/sample_manager/cli.py` (subcommands: init, scan, status, search, browse, config, tag,
  profile, export-profile, arrangement, selection, export, revert).
- TUI keybindings live in `src/sample_manager/tui/keybindings.py` (`KEYMAP` +
  `ACTION_DESCRIPTIONS` + `ACTION_CATEGORIES`); the in-app `HelpScreen` is generated from them.
  There is no separate user-facing keybinding table doc.
- Bulk find/replace across docs: macOS BSD `sed` does NOT support `\b`; use `perl -0777 -i -pe`
  for word-boundary replacements.
- Task records: `docs/reports/tasks/<NNN>-<slug>/task.md` (never `report.md`) via the
  `task-report` skill; `docs/reports/tui-issues.md` is the rolling issue index (task # = issue #).
