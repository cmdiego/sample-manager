---
name: report-filename-guardrail
description: Sandbox blocks writing any file whose name contains "report"; task records use task.md instead
metadata:
  type: feedback
---

Writing any file whose **name contains the word "report"** (e.g. `report.md`, `report.template.md`)
is blocked in this environment with: "Subagents should return findings as text, not write report
files." The block is on the filename, not the content.

**Why:** A harness guardrail pattern-matches "report" filenames to stop agents dumping findings to
disk instead of returning them as text. It fires even for legitimate skill assets / task records.

**How to apply:** The `task-report` skill's per-task record is named **`task.md`**, not `report.md`
(the skill and `docs/reports/tasks/README.md` already reflect this). Plans (`<NNN>-<slug>.md`),
`prompt.md`, and the `docs/reports/` directory names are fine — only the literal word "report" in a
*filename being written* is blocked. When creating new task artifacts, never name a written file
`*report*.md`. See [[task-report]] skill.
