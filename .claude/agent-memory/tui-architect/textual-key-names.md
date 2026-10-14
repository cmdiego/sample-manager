---
name: textual-key-names
description: Textual 8.x uses "question_mark" and "slash" as event.key names, not "?" and "/". All KEYMAP entries must use these Textual key names.
metadata:
  type: feedback
---

In Textual 8.x, `event.key` uses the full Textual key name, not the character:
- `?` → `event.key == "question_mark"` (event.character == "?")
- `/` → `event.key == "slash"` (event.character == "/")
- Arrow keys: "left", "right", "up", "down" (correct as-is)
- Enter: "enter" (correct for Return key in terminal)
- Tab: "tab" (correct)
- ctrl+p: intercepted by Textual as command palette; never reaches on_key

**Why:** Discovered during Pilot testing in tasks 002/003. Before the fix, `"?"` and `"/"` in KEYMAP were silently dead at runtime — `resolve_key("question_mark")` returned None and help/filter never activated.

**How to apply:** Always use Textual key names in KEYMAP, not the character symbol. When adding new bindings for punctuation characters, check the Textual key name with a quick `pilot.press(char)` + `on_key` print test before committing.

[[help-screen-pattern]]
