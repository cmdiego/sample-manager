# File Traversal Plan

## Goal
Add keyboard-driven file traversal that feels natural for Vim users and stays consistent across future browsing surfaces.

## Core Movement Mapping
- `h` and left arrow: move left
- `j` and down arrow: move down
- `k` and up arrow: move up
- `l` and right arrow: move right

## Scope For v1
- Use the same movement model anywhere the app shows a navigable file or sample list.
- Keep arrow keys as first-class equivalents, not separate behavior.
- Make traversal deterministic and predictable, with one focused item at a time.
- Preserve the current selection and search context while moving.

## Interaction Model
- `j` / down arrow advances to the next visible item.
- `k` / up arrow moves to the previous visible item.
- `h` / left arrow moves back to the parent container or previous logical region.
- `l` / right arrow enters the next logical region or opens the focused item.

## Implementation Steps
1. Define a shared navigation state model for focused item, visible range, and parent/child context.
2. Add keybinding normalization so `hjkl` and arrow keys dispatch to the same actions.
3. Wire traversal into the first browsable surface before expanding to other views.
4. Keep the traversal logic separate from rendering so it is easy to test.
5. Add regression tests for key mapping, focus movement, and boundary behavior.

## Non-Goals For The First Pass
- Mouse-driven navigation polish
- Multi-pane drag and drop
- Search ranking changes
- Filesystem mutation from traversal alone

## Open Questions
- Should `h` always mean "go to parent" or should it depend on the active pane?
- Should `l` open files immediately, or move into the next logical scope only when a container is focused?
- Should traversal be implemented first in the CLI browse surface or held for a future TUI layer?
