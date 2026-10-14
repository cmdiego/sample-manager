---
name: help-screen-pattern
description: HelpScreen modal pattern in Textual 8.x — event.stop() before dismiss() prevents key from bubbling back to app; Static.content replaces .renderable.
metadata:
  type: feedback
---

Two Textual 8.x quirks found during HelpScreen (task 003) implementation:

1. **Event bubbling through dismiss**: When a ModalScreen calls `self.dismiss()` in `on_key`, the key event continues to bubble upward to the App's `on_key` UNLESS `event.stop()` is called first. For the `?` key this caused the help screen to immediately re-open after dismissing. Fix: always `event.stop()` before `self.dismiss()` in modal key handlers.

2. **Static text attribute**: In Textual 8.x, `Static.content` holds the rendered text string (not `.renderable` which existed in older versions). Use `s.content` in tests and any code that reads back Static text.

**Why:** Both discovered via failing Pilot tests in task 003.

**How to apply:**
- Any new ModalScreen that dismisses on a key: add `event.stop()` before `self.dismiss()`.
- Any code/test reading text from a Static widget: use `.content`, not `.renderable`.

[[textual-key-names]]
