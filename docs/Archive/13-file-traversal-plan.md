# File Traversal Plan

## Goal
Build a shell-first navigation experience for Sample Manager that feels natural for Vim users, keeps keyboard traversal consistent across browsing surfaces, and lets users move samples into an active selection buffer as part of the flow.

## Product Scope
- The program should launch into an active shell experience.
- The shell is the primary environment where the user should spend most of their time.
- Existing CLI commands remain available, but the shell should be the intuitive default interaction model.
- File traversal and selection should feel like one continuous workflow, not separate modes.
- Build the shell UI with Python Textual.
- Allow mouse movement and pointer interaction inside the TUI in addition to keyboard traversal.

## Core Movement Mapping
- `h` and left arrow: move left
- `j` and down arrow: move down
- `k` and up arrow: move up
- `l` and right arrow: move right

## Navigation Model
- Up and down move through items in the current directory or list, matching the current pane context.
- Right opens a child directory when the focused item is a folder.
- Right on a file opens a small action pane with file actions such as add-to-selection, inspect, or other file-specific operations.
- The traversal should feel closer to Neotree, IDE file trees, and Elektron-style sample browsing than to a generic list widget.
- Left moves back to the parent directory or previous logical level.

## Scope For v1
- Use the same movement model anywhere the app shows a navigable file or sample list.
- Keep arrow keys as first-class equivalents, not separate behavior.
- Make traversal deterministic and predictable, with one focused item at a time.
- Preserve the current selection and search context while moving.
- Allow the focused file or sample to be added to an active selection buffer from the shell.
- Keep selection state visible and usable while traversing files.
- Support mouse clicks and pointer-driven focus changes inside the TUI.

## Interaction Model
- `j` / down arrow advances to the next visible item.
- `k` / up arrow moves to the previous visible item.
- `h` / left arrow moves back to the parent container or previous logical region.
- `l` / right arrow opens the focused directory or brings up the focused file action pane.
- A selected file should be able to enter the active selection buffer without leaving the shell workflow.
- Traversal actions should operate on the current focus and update selection affordances in the same context.
- Mouse interactions should be able to move focus, select items, and activate the same shell actions as the keyboard.

## Shell Experience
- Launch into a shell that exposes navigation, selection, search, and arrangement workflows.
- Keep the shell keyboard-driven by default.
- Surface the current location, focus, and selection state in a way that supports fast repeated actions.
- Allow commands when needed, but avoid forcing the user out of the shell for routine work.
- Mouse input should be a first-class convenience layer, not a separate mode.

## Selection Buffer Integration
- A focused file can be added to the active selection buffer.
- A focused file can be removed from the active selection buffer.
- Moving focus never changes selection by itself.
- Selection changes happen through explicit actions such as add-to-selection or remove-from-selection.
- The file action pane should expose selection commands so users can work quickly from the focused item.
- Selection state should be persistent enough to support arrangement creation and later editing.
- Traversal should make it easy to build a selection incrementally from the current file view.

## Implementation Steps
1. Define a shared navigation state model for focused item, visible range, parent/child context, and active selection state.
2. Add keybinding normalization so `hjkl` and arrow keys dispatch to the same actions.
3. Design the shell launch path using Textual so the user lands in an interactive, navigation-first environment.
4. Wire traversal and selection actions into the first browsable surface before expanding to other views.
5. Keep traversal, selection, and shell behavior separate from rendering so it is easy to test.
6. Add regression tests for key mapping, focus movement, selection-buffer updates, and boundary behavior.

## Non-Goals For The First Pass
- Multi-pane drag and drop
- Search ranking changes
- Filesystem mutation from traversal alone
- Full TUI feature parity
- Complex shell scripting or plugin automation

## Resolved Decisions
- `h` and left arrow move to the parent directory or previous logical level.
- `j` and `k` move within the current directory/list context.
- `l` and right arrow open child directories.
- On files, right arrow opens a small action pane instead of opening the file directly.
- Traversal is implemented first in the CLI browse surface.
- TUI comes after CLI movement, traversal, and file selection are in place.
- Selection is explicit, not automatic.
- The shell is a navigation-centric entry point that complements, rather than replaces, existing CLI commands.
