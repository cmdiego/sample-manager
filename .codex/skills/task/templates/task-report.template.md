# Task <NNN> — <Task Name>

- **Status**: Draft | In Progress | Blocked | Done
- **Created**: <YYYY-MM-DD>
- **Owner**: Codex
- **Origin**: <user request | issue | follow-up>
- **Scope**: <one sentence>

## 1. [Struct]

Describe the relevant structure before changing code.

- **Primary area**: `<path>`
- **Supporting areas**: `<path>`, `<path>`
- **Current ownership boundaries**:
- **Files expected to change**:
- **Files expected to remain untouched**:

## 2. [Interfaces]

List the integration seams this task will use or modify.

- **User-facing interface**:
- **Internal API/interface**:
- **Persistence/config interface**:
- **Events/signals/commands**:
- **Tests as interface contracts**:

## 3. [Todo]

- [ ] Inspect existing implementation and tests.
- [ ] Define the smallest safe change.
- [ ] Implement the change.
- [ ] Add or update tests.
- [ ] Run validation.
- [ ] Update this report with final implementation notes.

## 4. [Implementation + Revert]

### Implementation Plan

1. <step>
2. <step>
3. <step>

### Revert Plan

1. Revert `<path>` changes related to <specific behavior>.
2. Remove or restore tests in `<path>`.
3. Restore any config/default behavior changed by this task.

## 5. [Invariance]

These behaviors must remain true after implementation:

- <existing behavior or contract>
- <existing behavior or contract>
- <test or validation that protects the invariant>

## 6. [Implementation]

### Changed Files

- `<path>` — <what changed and why>

### Behavior Implemented

<Describe the actual behavior implemented.>

### Validation

- `<command>`: <PASS/FAIL or not run with reason>

### Follow-ups / Risks

- <none | concrete follow-up>
