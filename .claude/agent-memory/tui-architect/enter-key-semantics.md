---
name: enter-key-semantics
description: Established Enter key semantics: Return → select_or_descend (toggle file / descend dir); l/→ → enter action (open ActionPane modal). Confirmed correct from task 002.
metadata:
  type: project
---

Return (Enter) key is bound to `select_or_descend` action (task 002):
- **File**: toggles its presence in the persistent selection buffer (add if not selected, remove if selected). No modal is opened.
- **Directory**: descends into it (same directory-entry behavior as l/→).

l/→ keys remain bound to `enter` action → `_handle_enter()` → opens ActionPane modal on files (shows add/remove buttons).

**Why:** Digitakt-inspired "soft select" — Return is the primary way to add items to a session. The modal (l/→) is for users who want to inspect before deciding. Keeping them distinct avoids accidental modal openings during fast browsing.

**How to apply:** Do not change Return to open ActionPane. Do not change l/→ to do selection toggle. These are deliberately different. [[textual-key-names]]
