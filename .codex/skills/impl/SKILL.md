---
name: impl
description: >
  Implementation skill for executing code changes with comprehensive inline documentation.
  Use when implementing a task step, feature, or bug fix. Enforces comment-driven development
  where every significant piece of code explains its purpose inline, and uses the JSON GUI
  simulation framework when mocking or validating GUI behavior.
---

# Implementation Skill

Use this skill when writing or modifying code in the `sample_manager` project. This skill
enforces best practices for code clarity, documentation, and maintainability.

## Core Principle: Comment-Driven Code

**Every significant piece of code must have a comment explaining its purpose.**

This is not optional. Comments are not overhead—they are the specification written in natural
language alongside the implementation.

## When to Use

- Implementing a task step from a task report
- Adding a new feature or module
- Fixing a bug with code changes
- Refactoring existing code
- Adding tests for new functionality

## Implementation Rules

### 1. Inline Documentation (MANDATORY)

Every function, class, and non-trivial code block must have documentation:

```python
# GOOD: Function with docstring
def calculate_folder_path(folder_id: int) -> str:
    """Get the full virtual path for a folder by traversing parent chain.
    
    Args:
        folder_id: Folder ID to resolve
        
    Returns:
        Path string like "parent/child" (no leading slash)
        
    Raises:
        ValueError: If folder_id not found
    """
    # Build path by walking up parent chain
    folder = self._repo.get_folder(folder_id)
    if not folder:
        raise ValueError(f"Folder {folder_id} not found")
    
    # Collect folder names from leaf to root
    parts = [folder["name"]]
    current_id = folder["parent_id"]
    
    # Walk up the parent chain
    while current_id is not None:
        parent = self._repo.get_folder(current_id)
        if not parent:
            break
        parts.insert(0, parent["name"])
        current_id = parent["parent_id"]
    
    return "/".join(parts)


# GOOD: Complex logic with inline comments
def build_tree(arrangement_id: int) -> ArrangementTree:
    """Build complete tree structure for an arrangement."""
    # Load all folders in one query for efficiency
    folder_rows = self._repo.list_folders(arrangement_id)
    folders_by_id = {r["id"]: Folder(**r) for r in folder_rows}
    
    # Group folders by parent for tree building
    children_by_parent: dict[int | None, list[TreeNode]] = {}
    
    # Create initial nodes for all folders
    for folder in folders_by_id.values():
        node = TreeNode(
            node_type="folder",
            folder=folder,
            sample=None,
            children=(),  # Will be filled recursively
        )
        children_by_parent.setdefault(folder.parent_id, []).append(node)
    
    # Recursively build subtrees starting from root
    def build_subtree(folder_id: int) -> TreeNode:
        folder = folders_by_id[folder_id]
        child_nodes = []
        
        # Add child folders first
        for child in children_by_parent.get(folder_id, []):
            if child.node_type == "folder" and child.folder:
                child_nodes.append(build_subtree(child.folder.id))
        
        # Add samples in this folder
        sample_rows = self._repo.list_folder_samples(folder_id)
        for s_row in sample_rows:
            # Convert row to immutable DTO
            sample = ArrangementSample(**s_row)
            child_nodes.append(
                TreeNode(node_type="sample", folder=None, sample=sample, children=())
            )
        
        return TreeNode(
            node_type="folder",
            folder=folder,
            sample=None,
            children=tuple(child_nodes),
        )
    
    # Build root-level nodes
    root_folder_nodes = []
    for node in children_by_parent.get(None, []):
        if node.node_type == "folder" and node.folder:
            root_folder_nodes.append(build_subtree(node.folder.id))
    
    return ArrangementTree(
        arrangement_id=arrangement_id,
        root_folders=tuple(root_folder_nodes),
        root_samples=tuple(root_sample_rows),
    )


# BAD: No comments, unclear purpose
def process(data):
    result = []
    for item in data:
        x = item.get("val")
        if x and x > 0:
            result.append(x * 2)
    return result
```

### 2. Module and Class Documentation

Every module and class must have a module docstring and class docstring:

```python
"""Service for managing arrangement virtual folders and sample placement.

Provides a framework-neutral layer over ArrangementRepo for:
- Creating and organizing virtual folders in arrangements
- Adding, moving, and removing samples
- Building tree structures for display
- Snapshot-based undo/restore

All operations are transactional and validate constraints like:
- Folder name uniqueness among siblings
- Cycle prevention in folder hierarchy
- Cross-arrangement boundary enforcement
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import Db
from .repos.arrangement_repo import ArrangementRepo


class ArrangementWorkspaceService:
    """Framework-neutral service for arrangement workspace operations.
    
    Handles virtual folder creation, renaming, moving, removal, and sample
    placement. All operations validate constraints and run in transactions.
    
    Example:
        workspace = ArrangementWorkspaceService(db)
        folder = workspace.create_folder(arr_id, None, "Kicks")
        workspace.add_samples(arr_id, [1, 2, 3], folder.id)
    """
    
    def __init__(self, db: Db) -> None:
        self._db = db
        self._repo = ArrangementRepo(db)
```

### 3. Dataclass and DTO Documentation

Immutable DTOs should document their purpose and fields:

```python
@dataclass(frozen=True)
class Folder:
    """Virtual folder in an arrangement.
    
    Represents a metadata-only folder for organizing samples. Folders form
    a tree structure via parent_id, with unique names among siblings.
    """
    
    id: int                    # Primary key
    arrangement_id: int        # Parent arrangement
    parent_id: int | None      # Parent folder (None = root)
    name: str                  # Display name (original case)
    name_norm: str             # Normalized for case-insensitive uniqueness
    sort_order: int            # Display order among siblings
    created_at: str            # ISO timestamp
    updated_at: str            # ISO timestamp


@dataclass(frozen=True)
class RemovalSnapshot:
    """Snapshot of removed folders and samples for undo/restore.
    
    Contains full state needed to restore a removed folder tree, including
    all descendant folders and their sample placements.
    """
    
    folder_rows: tuple[dict, ...]           # Folder records to restore
    sample_placements: tuple[dict, ...]     # Sample placement records
```

### 4. Complex Algorithm Documentation

For algorithms, add comments explaining the approach:

```python
def remove_folder_tree(self, folder_id: int) -> RemovalSnapshot:
    """Remove a folder and all its descendants.
    
    Uses a two-phase approach:
    1. Collect all folders and sample placements (for undo)
    2. Remove samples then folders in transaction
    
    Args:
        folder_id: Root folder to remove
        
    Returns:
        Snapshot for undo/restore
    """
    with self._db.transaction():
        # Phase 1: Collect all affected data for snapshot
        descendants = self._repo.get_folder_descendants(folder_id)
        folder = self._repo.get_folder(folder_id)
        if not folder:
            raise ValueError(f"Folder {folder_id} not found")
        
        all_folder_ids = [folder_id] + [d["id"] for d in descendants]
        folder_rows = [folder] + descendants
        
        # Collect sample placements before deletion
        sample_placements = []
        for fid in all_folder_ids:
            samples = self._repo.list_folder_samples(fid)
            for s in samples:
                sample_placements.append({
                    "arrangement_id": folder["arrangement_id"],
                    "sample_id": s["id"],
                    "folder_id": s["folder_id"],
                    "sort_order": s["sort_order"],
                })
        
        # Phase 2: Execute deletion
        # Must remove samples first (FK constraint)
        self._repo.remove_samples_in_folder_tree(folder_id)
        
        # Then remove folder (CASCADE removes descendants)
        self._repo.remove_folder(folder_id)
    
    return RemovalSnapshot(
        folder_rows=tuple(folder_rows),
        sample_placements=tuple(sample_placements)
    )
```

### 5. Test Documentation

Tests should document what they're testing and why:

```python
class TestFolderCreation:
    """Tests for creating virtual folders in arrangements."""
    
    def test_create_root_folder(self, workspace, arrangement):
        """Test creating a folder at the root level."""
        folder = workspace.create_folder(arrangement["id"], None, "Kicks")
        
        assert folder.name == "Kicks"
        assert folder.name_norm == "kicks"
        assert folder.parent_id is None
        assert folder.arrangement_id == arrangement["id"]
        assert folder.sort_order > 0
    
    def test_duplicate_sibling_rejected(self, workspace, arrangement):
        """Test that duplicate sibling names are rejected (case-insensitive)."""
        workspace.create_folder(arrangement["id"], None, "Kicks")
        
        # Should fail due to case-insensitive uniqueness
        with pytest.raises(ValueError, match="already exists"):
            workspace.create_folder(arrangement["id"], None, "kicks")
    
    def test_cycle_prevention(self, workspace, arrangement):
        """Test that moving a folder to its own descendant is prevented."""
        parent = workspace.create_folder(arrangement["id"], None, "Parent")
        child = workspace.create_folder(arrangement["id"], parent.id, "Child")
        grandchild = workspace.create_folder(arrangement["id"], child.id, "Grandchild")
        
        # Cannot move parent into its own grandchild
        with pytest.raises(ValueError, match="descendant"):
            workspace.move_folders((parent.id,), grandchild.id)
```

### 6. SQL Query Documentation

SQL queries should have comments explaining their purpose:

```python
def get_folder_descendants(self, folder_id: int) -> list[dict]:
    """Get all descendant folders recursively using CTE.
    
    Uses a recursive common table expression to walk the folder tree
    from the given folder down to all leaves.
    """
    rows = self._db.fetchall(
        """
        -- Recursive CTE to find all descendants
        WITH RECURSIVE descendants(id) AS (
            -- Base case: the folder itself
            SELECT id FROM arrangement_folder WHERE id = ?
            UNION ALL
            -- Recursive case: children of current level
            SELECT af.id FROM arrangement_folder af
            JOIN descendants d ON af.parent_id = d.id
        )
        SELECT af.id, af.arrangement_id, af.parent_id, af.name, af.name_norm,
               af.sort_order, af.created_at, af.updated_at
        FROM arrangement_folder af
        JOIN descendants d ON af.id = d.id
        WHERE af.id != ?  -- Exclude the root folder itself
        """,
        (folder_id, folder_id),
    )
    return [dict(r) for r in rows]
```

### 7. Error Handling Documentation

Explain validation and error conditions:

```python
def create_folder(self, arrangement_id: int, parent_id: int | None, name: str) -> Folder:
    """Create a new virtual folder.
    
    Validates:
    - Name is not empty or whitespace-only
    - Name doesn't contain path separators (/, \)
    - Name is not . or ..
    - Name is unique among siblings (case-insensitive)
    - Parent exists and belongs to same arrangement
    
    Args:
        arrangement_id: Target arrangement
        parent_id: Parent folder ID (None for root)
        name: Display name
        
    Raises:
        ValueError: If name is invalid or would create a duplicate
        
    Returns:
        Created folder
    """
    # Validate name format
    name = name.strip()
    if not name:
        raise ValueError("Folder name cannot be empty")
    if "/" in name or "\\" in name:
        raise ValueError("Folder name cannot contain path separators")
    if name in (".", ".."):
        raise ValueError("Folder name cannot be . or ..")
    
    name_norm = norm_text(name)
    
    # Check for duplicate siblings (case-insensitive)
    if parent_id is None:
        existing = self._db.fetchone(
            "SELECT 1 FROM arrangement_folder "
            "WHERE arrangement_id = ? AND parent_id IS NULL AND name_norm = ?",
            (arrangement_id, name_norm),
        )
    else:
        existing = self._db.fetchone(
            "SELECT 1 FROM arrangement_folder "
            "WHERE arrangement_id = ? AND parent_id = ? AND name_norm = ?",
            (arrangement_id, parent_id, name_norm),
        )
    
    if existing:
        raise ValueError(f"Folder '{name}' already exists at this level")
    
    # Validate parent if specified
    if parent_id is not None:
        parent = self._repo.get_folder(parent_id)
        if not parent:
            raise ValueError(f"Parent folder {parent_id} not found")
        if parent["arrangement_id"] != arrangement_id:
            raise ValueError("Cannot use parent from different arrangement")
    
    # Create the folder
    with self._db.transaction():
        row = self._repo.create_folder(arrangement_id, parent_id, name, name_norm)
    
    return Folder(**row)
```

## Architecture Alignment

Follow existing project patterns:

### Layering
- **Repos** (`repos/`) - Own all SQL, return dicts
- **Services** (`services/`, root modules) - Business logic, validation, transactions
- **GUI** (`gui/`) - Presentation only, no SQL, no business logic
- **DTOs** - Immutable dataclasses for data transfer

### Database
- All SQL in repository methods
- Use parameterized queries (never string interpolation)
- Transactions via `with db.transaction():`
- Repos don't commit (service layer commits)

### Testing
- Test files mirror source structure: `tests/test_foo.py` for `src/sample_manager/foo.py`
- Use fixtures for common setup (`db`, `tmp_path`, etc.)
- Test both success and error cases
- Include edge cases (empty input, duplicates, boundaries)

### GUI Simulation

When implementing GUI behavior or mocking user interaction, use the JSON simulation
framework instead of one-off mocks whenever the behavior can be expressed as user
events, commands, or observable GUI state.

- Runtime API: `src/sample_manager/gui/simulation.py`
- Scenario tests: `tests/gui/test_json_scenarios.py`
- Scenario files: `tests/gui/scenarios/*.json`
- Shell entry points:
  - `sampleman --simulation`
  - `sampleman gui --simulation`
  - `python -m sample_manager --simulation`

Use JSON dispatch objects for GUI movement and interaction:

```json
{"command": "snapshot"}
{"event": "key", "key": "L"}
{"event": "key", "key": "J"}
{"assert": "path", "relative": "drums"}
{"assert": "focus", "row": 1, "name": "snare.wav", "is_dir": false}
```

For new GUI features, prefer adding or extending JSON scenarios when:

- the feature changes keyboard/mouse behavior;
- an agent needs to simulate the app without manually driving Qt;
- the behavior spans multiple widgets or controller state transitions;
- the implementation would otherwise require brittle ad-hoc mocks.

Keep low-level widget/model unit tests as normal Python tests. The JSON framework
is for workflow simulation and user-observable behavior, not replacing focused unit tests.

### Comments Should NOT
- State the obvious: `x = x + 1  # increment x`
- Repeat the code: `# call get_folder`, then `get_folder()`
- Apologize: `# TODO: this is hacky`
- Lie: Comment says one thing, code does another

### Comments SHOULD
- Explain **why**, not just **what**
- Document invariants and assumptions
- Clarify non-obvious algorithms
- Reference external specs or RFCs
- Warn about edge cases or gotchas

## Validation Before Committing

Before marking implementation complete:

1. **Run tests**: `pytest tests/ -xvs`
2. **Check coverage**: Tests for new functions/classes
3. **Verify comments**: Every significant block documented
4. **Check types**: No type errors if using mypy
5. **Run JSON GUI scenarios when GUI behavior changes**:
   `QT_QPA_PLATFORM=offscreen pytest tests/gui/test_json_scenarios.py -v`
6. **Review diff**: All changes intentional and documented

## Example: Complete Implementation

Here's a complete example showing all rules in practice:

```python
"""Arrangement workspace service and DTOs for virtual folder management.

Provides a framework-neutral service for managing arrangement virtual folders,
sample placement, and tree operations. All DTOs are immutable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import Db
from .normalize import norm_text
from .repos.arrangement_repo import ArrangementRepo


@dataclass(frozen=True)
class Folder:
    """Virtual folder in an arrangement."""
    
    id: int
    arrangement_id: int
    parent_id: int | None
    name: str
    name_norm: str
    sort_order: int
    created_at: str
    updated_at: str


class ArrangementWorkspaceService:
    """Framework-neutral service for arrangement workspace operations.
    
    Handles virtual folder creation, renaming, moving, removal, and sample
    placement. All operations validate constraints and run in transactions.
    """
    
    def __init__(self, db: Db) -> None:
        self._db = db
        self._repo = ArrangementRepo(db)
    
    def create_folder(
        self, arrangement_id: int, parent_id: int | None, name: str
    ) -> Folder:
        """Create a new virtual folder.
        
        Validates name format and uniqueness before creating.
        
        Args:
            arrangement_id: Target arrangement
            parent_id: Parent folder ID (None for root)
            name: Display name
            
        Raises:
            ValueError: If name is invalid or duplicate
            
        Returns:
            Created folder
        """
        # Validate name format
        name = name.strip()
        if not name:
            raise ValueError("Folder name cannot be empty")
        if "/" in name or "\\" in name:
            raise ValueError("Folder name cannot contain path separators")
        
        name_norm = norm_text(name)
        
        # Check for duplicate siblings
        # ... (validation code with comments)
        
        # Create the folder transactionally
        with self._db.transaction():
            row = self._repo.create_folder(arrangement_id, parent_id, name, name_norm)
        
        return Folder(**row)
```

## Summary

Follow these rules for every implementation:

1. ✅ **Document every function** with docstrings
2. ✅ **Comment complex logic** inline
3. ✅ **Explain algorithms** and design choices
4. ✅ **Document validation** and error cases
5. ✅ **Test thoroughly** with documented test cases
6. ✅ **Use JSON GUI simulation** for mocked GUI workflows
7. ✅ **Follow architecture** (repos, services, GUI layers)
8. ✅ **Use transactions** for multi-step operations
9. ✅ **Validate before commit** (tests, types, coverage)

Remember: **Comments are not overhead—they are the specification.**
