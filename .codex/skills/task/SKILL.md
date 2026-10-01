---
name: task
description: >
  Use when starting or implementing a new sample_manager task that needs durable
  documentation. Creates exactly one task report per task, organized around
  Struct, Interfaces, Todo, Implementation + Revert, Invariance, and Implementation,
  and keeps the main task tracker updated.
---

# Task

Use this skill when a new implementation task begins, especially for feature work,
architecture changes, GUI/TUI behavior, audio changes, or refactors.

The output is one task report. Do not create separate plan, prompt, or extra report
files unless the user explicitly asks.

## Location

Store task reports under:

```text
docs/reports/tasks/<NNN>-<task-slug>/task.md
```

- `<NNN>` is the next unused zero-padded task number (check `docs/reports/tasks/` for existing).
- `<task-slug>` is a short kebab-case summary (e.g., `arrangement-workspace-qol`).
- If the task already has a directory, update its existing `task.md`.

Maintain the main task tracker at:

```text
docs/reports/tasks/README.md
```

## Workflow

1. **Assign task number** by inspecting `docs/reports/tasks/` for the next unused number.
2. **Create directory** `docs/reports/tasks/<NNN>-<task-slug>/`.
3. **Create task report** `<dir>/task.md` using `templates/task-report.template.md`.
4. **Fill all six sections** before implementation starts (planning phase).
5. **Update task tracker** at `docs/reports/tasks/README.md` with new row.
6. **During implementation**, keep the report current:
   - Update [Todo] section as tasks complete
   - Add findings to [Implementation] section
   - Document actual files changed
   - Record validation results
7. **On status change**, update both task report and tracker row.
8. **At completion**, finalize:
   - Status → Done
   - Complete [Implementation] section
   - Record final validation
   - Document any follow-ups or risks
   - Update tracker row

## Required Sections

Each report must contain these sections in this order:

1. **[Struct]** — Codebase structure and ownership boundaries
   - Primary areas touched
   - Supporting components
   - Files expected to change vs remain untouched

2. **[Interfaces]** — Public APIs, events, commands, settings, UI entry points
   - User-facing interfaces (CLI commands, GUI widgets)
   - Internal APIs and service boundaries
   - Persistence and configuration interfaces
   - Integration seams with existing code

3. **[Todo]** — Concrete task checklist
   - Specific, actionable items
   - Can be updated during implementation
   - Use `[ ]` for pending, `[x]` for complete

4. **[Implementation + Revert]** — Strategy plus rollback plan
   - **Implementation**: Step-by-step plan
   - **Revert**: Exact steps to undo (specific enough for another engineer)

5. **[Invariance]** — Behaviors and contracts that must not change
   - Existing behaviors to preserve
   - Test coverage protecting invariants
   - Backward compatibility requirements

6. **[Implementation]** — Final implementation notes
   - **Changed Files**: Actual files modified with descriptions
   - **Behavior Implemented**: What was actually done
   - **Validation**: Test commands and results
   - **Follow-ups/Risks**: Known issues or future work

## Rules

- Keep reports factual and implementation-oriented.
- Use file paths and concrete symbols, not vague descriptions.
- Document architectural decisions that constrain future work.
- Include test commands for validation (`pytest tests/...`).
- Revert plan must be specific and actionable.
- Update the report when implementation diverges from initial plan.
- Task tracker row must match report title, status, and created date.
- Status transitions: Draft → In Progress → Done (or Blocked/Cancelled).

## Template

Use:

```text
.codex/skills/task/templates/task-report.template.md
```

## Integration with Existing Tasks

This project has task reports under `docs/reports/tasks/` with numbered directories like:
- `001-textual-tui-browser/`
- `008-arrangement-workspace-qol/`

When creating a new task, follow this existing convention and update the README.md tracker.
