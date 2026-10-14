# TUI Architect Memory Index

- [Textual Key Names](textual-key-names.md) — Textual 8.x uses "question_mark"/"slash" not "?"/"/" in event.key; affects KEYMAP
- [HelpScreen Pattern](help-screen-pattern.md) — HelpScreen modal: event.stop() required before dismiss() to prevent bubbling; Static.content not .renderable in Textual 8.x
- [Enter Key Semantics](enter-key-semantics.md) — Return key → select_or_descend (toggle file / descend dir); l/right → enter action (open ActionPane)
