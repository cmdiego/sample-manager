---
name: task-report
description: >
  Create and maintain Task Reports (and Plan + Prompt files) under docs/reports/ whenever a
  new task or TUI issue is picked up for tracking or delegation. Use this when a task is
  assigned a number, when deciding whether work needs a full Plan, or when generating a
  prompt to hand a specialist agent. Enforces the project's plan/prompt file conventions.
---

# Task Report process

Standardizes how work is recorded, planned, and handed to specialist agents in the
`sample_manager` project. Every non-trivial task gets a Task Report; multi-step or
dependency-bearing tasks also get a Plan file (which can generate its own prompt).

## When to use

- A user reports a TUI issue or requests a new task/feature.
- You are about to delegate work to a specialist agent (`tui-architect`,
  `test-pipeline-architect`, general-purpose) and need a durable brief.
- You need to decide whether a task warrants a full Plan or just a Report.

## Directory layout

All artifacts live under `docs/reports/`:

```
docs/reports/
  tui-issues.md                       ← rolling TUI issue index (the canonical issue log)
  tasks/                              ← Task directory (create on demand if missing)
    <NNN>-<task-slug>/                ← one directory per task
      task.md                         ← Task Report (ALWAYS; named task.md, not report.md)
      <NNN>-<task-slug>.md            ← Plan file (ONLY if multi-step or has dependencies)
      prompt.md                       ← prompt derived from the Plan (generated with the Plan)
```

- `<NNN>` is the task number, zero-padded to 3 digits (e.g. `002`).
- `<task-slug>` is a short kebab-case name (e.g. `session-summary-size`).
- When a task originates from a TUI issue, the task number **equals the issue number** so
  the report and the `tui-issues.md` row stay in lock-step. Otherwise use the next unused
  task number in `docs/reports/tasks/`.

## Procedure

1. **Assign the number.** For a TUI issue, reuse its issue-log number. Otherwise take the
   next sequential `<NNN>` under `docs/reports/tasks/`.
2. **Create the task directory** `docs/reports/tasks/<NNN>-<task-slug>/` if it does not exist.
3. **Write the Task Report** at `<dir>/task.md` from `templates/task.template.md`. Always required.
   (The record is named `task.md`, **not** `report.md`: this sandbox blocks writing any file
   whose name contains the word "report".)
4. **Decide if a Plan is needed.** Create a Plan when the task is **multi-step**, is
   **blocked by another task**, or **requires a new feature to be implemented first**.
   Simple single-step fixes skip the Plan (Report only).
5. **If a Plan is needed**, write it at `<dir>/<NNN>-<task-slug>.md` from `templates/plan.template.md`,
   following the project plan convention (see `docs/13-file-traversal-plan.md`). Then
   **generate the prompt** at `<dir>/prompt.md` from `templates/prompt.template.md` — it is derived
   directly from the Plan's Goal/Scope/Deliverables, mirroring how `docs/prompts/prompt_12.md`
   derives from `docs/13-file-traversal-plan.md`.
6. **Update the index.** For TUI issues, add/update the row in `docs/reports/tui-issues.md`.
7. **Delegate** to the right specialist agent, pointing it at the Report (and Plan/prompt).
8. **Keep status current** in the Report and index: `🔍 Investigating` → `🔧 In Progress` →
   `✅ Fixed`/`✅ Done` (or `❌ Blocked`). Fill in Resolution, Validation (`pytest tests/ -v`),
   and Regression Test as the work completes.

## Conventions to preserve

- **Plan files** follow `docs/13-file-traversal-plan.md`: `# Title`, `## Goal`, `## Scope`,
  numbered `## Implementation Steps`, `## Non-Goals`, `## Resolved Decisions`.
- **Prompts** follow `docs/prompts/prompt_12.md`: `Task (<NNN> — <name>): <one-liner>.` then
  `Read these docs first:`, `Scope (ONLY):`, `Deliverables:`, closing with `Testing required.`
- A Plan must contain enough structured detail (Goal, Scope, Deliverables, Testing) that its
  prompt can be generated mechanically. Keep the Plan and prompt in sync.
- Architecture guardrails still apply to any delegated work: CSS only in `styles/app.tcss`,
  DB access only through `TuiDataSource` (`data.py`), pure logic (no Textual imports) in
  `nav_state.py`, `update()` via `remove_children()`+`mount()` (never `refresh()`),
  parameterized SQL only, and no reduction in passing tests.

## Templates

- `templates/task.template.md` — Task Report (always)
- `templates/plan.template.md` — Plan file (multi-step / dependency tasks)
- `templates/prompt.template.md` — Prompt generated from the Plan
