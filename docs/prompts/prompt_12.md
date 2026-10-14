Task (Phase 12): File traversal + shell-first TUI navigation.

Read these docs first:
- docs/13-file-traversal-plan.md
- docs/03-cli.md
- docs/02-persistence.md
- docs/01-data-model.md

Scope (ONLY):
- Implement file traversal/navigation behavior first in the CLI browse surface
- Add Vim-style movement mapping: `h/j/k/l` plus arrow-key parity
- Make movement context-aware for the current directory/list
- Right arrow on folders opens the child directory
- Right arrow on files opens a small file-action pane
- Add explicit file selection actions for the active selection buffer
- Keep selection separate from focus movement
- Add mouse support in the TUI layer as an additional input path
- Scaffold the Textual shell interface as the next-stage UI entry point
- Do not remove or break existing CLI commands

Deliverables:
- traversal/navigation implementation
- selection-buffer integration
- Textual shell scaffold
- tests

Testing required.
