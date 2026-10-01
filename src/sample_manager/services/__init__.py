"""Framework-neutral service layer for the GUI/TUI front-ends.

Modules here must never import a UI framework (no TUI, no Qt). They contain the
pure navigation and library-browsing logic shared by any front-end (the terminal
UI today, Qt in a future phase).
"""
