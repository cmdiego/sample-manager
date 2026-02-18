"""Tag orchestration service for Phase 5.

Thin coordination layer over TagRepo, TagAliasRepo, SampleTagRepo, and
TagParentRepo. Handles tag resolution (name/shorthand/alias chain),
auto-creation, and bulk operations.

CLI commands delegate here rather than wiring repos directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import Db
from .repos.sample_repo import SampleRepo
from .repos.sample_tag_repo import SampleTagRepo
from .repos.tag_alias_repo import TagAliasRepo
from .repos.tag_parent_repo import TagParentRepo
from .repos.tag_repo import TagRepo
from .search import SearchEngine


def resolve_tag(
    db: Db,
    text: str,
    *,
    include_hidden: bool = False,
) -> dict:
    """Resolve a tag string to a full tag row dict.

    Resolution chain (case-insensitive):
      1. tag.name_norm
      2. tag.shorthand_norm
      3. tag_alias.alias_norm

    Args:
        db: Database connection.
        text: Tag name, shorthand, or alias string.
        include_hidden: If True, include hidden tags in resolution.

    Returns:
        Full tag row as dict.

    Raises:
        ValueError: If the tag string cannot be resolved.
    """
    alias_repo = TagAliasRepo(db)
    tag_repo = TagRepo(db)

    tag_id = alias_repo.resolve(text, include_hidden=include_hidden)
    if tag_id is None:
        raise ValueError(f"Tag not found: {text!r}")

    tag = tag_repo.get_by_id(tag_id)
    assert tag is not None, f"resolve() returned id={tag_id} but get_by_id returned None"
    return tag


def resolve_or_create_tag(db: Db, text: str) -> dict:
    """Resolve an existing tag, or auto-create if not found.

    Tries resolve_tag() first (excluding hidden). On failure, creates
    via TagRepo.get_or_create() using the input text as name_display.

    Args:
        db: Database connection.
        text: Tag name, shorthand, or alias string.

    Returns:
        Full tag row as dict (existing or newly created).
    """
    try:
        return resolve_tag(db, text)
    except ValueError:
        tag_repo = TagRepo(db)
        return tag_repo.get_or_create(text)


def tag_sample(db: Db, sample_id: int, tag_text: str) -> dict:
    """Resolve/create a tag and attach it to a sample.

    Idempotent: re-attaching an existing tag is a no-op.

    Args:
        db: Database connection.
        sample_id: ID of the sample to tag.
        tag_text: Tag name, shorthand, or alias string.

    Returns:
        Full tag row as dict.

    Raises:
        ValueError: If sample_id does not exist.
    """
    sample_repo = SampleRepo(db)
    sample = sample_repo.get_by_id(sample_id)
    if sample is None:
        raise ValueError(f"Sample not found: id={sample_id}")

    tag = resolve_or_create_tag(db, tag_text)

    sample_tag_repo = SampleTagRepo(db)
    sample_tag_repo.attach(sample_id, tag["id"])
    return tag


def untag_sample(db: Db, sample_id: int, tag_text: str) -> dict:
    """Resolve a tag and detach it from a sample.

    Args:
        db: Database connection.
        sample_id: ID of the sample to untag.
        tag_text: Tag name, shorthand, or alias string.

    Returns:
        Full tag row as dict.

    Raises:
        ValueError: If sample_id does not exist or tag cannot be resolved.
    """
    sample_repo = SampleRepo(db)
    sample = sample_repo.get_by_id(sample_id)
    if sample is None:
        raise ValueError(f"Sample not found: id={sample_id}")

    tag = resolve_tag(db, tag_text)

    sample_tag_repo = SampleTagRepo(db)
    sample_tag_repo.detach(sample_id, tag["id"])
    return tag


def list_sample_tags(db: Db, sample_id: int) -> list[dict]:
    """List all tags attached to a sample.

    Args:
        db: Database connection.
        sample_id: ID of the sample.

    Returns:
        List of tag row dicts.

    Raises:
        ValueError: If sample_id does not exist.
    """
    sample_repo = SampleRepo(db)
    sample = sample_repo.get_by_id(sample_id)
    if sample is None:
        raise ValueError(f"Sample not found: id={sample_id}")

    sample_tag_repo = SampleTagRepo(db)
    return sample_tag_repo.list_tags_for_sample(sample_id)


@dataclass
class BulkResult:
    """Summary of a bulk tag operation.

    Attributes:
        samples_matched: Number of samples that were targeted.
        tags_added: Display names of tags that were added.
        tags_removed: Display names of tags that were removed.
        attachments_made: Total attach operations (includes idempotent no-ops).
        detachments_made: Total detach operations (includes idempotent no-ops).
    """

    samples_matched: int = 0
    tags_added: list[str] = field(default_factory=list)
    tags_removed: list[str] = field(default_factory=list)
    attachments_made: int = 0
    detachments_made: int = 0

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "samples_matched": self.samples_matched,
            "tags_added": self.tags_added,
            "tags_removed": self.tags_removed,
            "attachments_made": self.attachments_made,
            "detachments_made": self.detachments_made,
        }


def bulk_tag(
    db: Db,
    sample_ids: list[int],
    *,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
) -> BulkResult:
    """Bulk add/remove tags for multiple samples.

    Idempotent: duplicate attach/detach operations are silently ignored.

    Args:
        db: Database connection.
        sample_ids: List of sample IDs to operate on.
        add_tags: Tag strings to attach (resolved or auto-created).
        remove_tags: Tag strings to detach (must resolve; raises on unknown).

    Returns:
        BulkResult summary.

    Raises:
        ValueError: If any remove_tag cannot be resolved.
    """
    add_tags = add_tags or []
    remove_tags = remove_tags or []

    sample_tag_repo = SampleTagRepo(db)

    # Resolve/create tags to add
    resolved_add: list[dict] = []
    for tag_text in add_tags:
        tag = resolve_or_create_tag(db, tag_text)
        resolved_add.append(tag)

    # Resolve tags to remove (strict — must exist)
    resolved_remove: list[dict] = []
    for tag_text in remove_tags:
        tag = resolve_tag(db, tag_text)
        resolved_remove.append(tag)

    result = BulkResult(
        samples_matched=len(sample_ids),
        tags_added=[t["name_display"] for t in resolved_add],
        tags_removed=[t["name_display"] for t in resolved_remove],
    )

    for sid in sample_ids:
        for tag in resolved_add:
            sample_tag_repo.attach(sid, tag["id"])
            result.attachments_made += 1
        for tag in resolved_remove:
            sample_tag_repo.detach(sid, tag["id"])
            result.detachments_made += 1

    return result


def bulk_tag_from_search(
    db: Db,
    query: str,
    *,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
) -> BulkResult:
    """Run a name-based search and bulk add/remove tags on matching samples.

    The query string is passed as the ``name`` filter to SearchEngine.
    All matching sample IDs are collected (unpaginated — up to 10000 results)
    and passed to bulk_tag().

    Args:
        db: Database connection.
        query: Name pattern for SearchEngine (LIKE %%query%%).
        add_tags: Tag strings to attach.
        remove_tags: Tag strings to detach.

    Returns:
        BulkResult summary.

    Raises:
        ValueError: If any remove_tag cannot be resolved, or no samples match.
    """
    engine = SearchEngine(db)
    result = engine.search(name=query, page_size=10000)
    sample_ids = [item["id"] for item in result.items]

    if not sample_ids:
        return BulkResult(samples_matched=0)

    return bulk_tag(
        db,
        sample_ids,
        add_tags=add_tags,
        remove_tags=remove_tags,
    )


def add_tag_alias(db: Db, tag_text: str, alias_display: str) -> dict:
    """Add an alias to an existing tag.

    Args:
        db: Database connection.
        tag_text: Tag name/shorthand/alias to resolve.
        alias_display: New alias string.

    Returns:
        Full tag_alias row as dict.

    Raises:
        ValueError: If the tag cannot be resolved.
        sqlite3.IntegrityError: If alias_norm conflicts globally.
    """
    tag = resolve_tag(db, tag_text)
    alias_repo = TagAliasRepo(db)
    return alias_repo.add(tag["id"], alias_display)


def remove_tag_alias(db: Db, alias_text: str) -> None:
    """Remove a tag alias by its text.

    Args:
        db: Database connection.
        alias_text: Alias string to remove.
    """
    alias_repo = TagAliasRepo(db)
    alias_repo.remove_by_alias(alias_text)


def add_tag_parent(db: Db, child_text: str, parent_text: str) -> None:
    """Add a parent edge in the tag DAG.

    Args:
        db: Database connection.
        child_text: Child tag name/shorthand/alias.
        parent_text: Parent tag name/shorthand/alias.

    Raises:
        ValueError: If either tag cannot be resolved, or cycle detected.
    """
    child = resolve_tag(db, child_text)
    parent = resolve_tag(db, parent_text)
    parent_repo = TagParentRepo(db)
    parent_repo.add_parent(child["id"], parent["id"])


def remove_tag_parent(db: Db, child_text: str, parent_text: str) -> None:
    """Remove a parent edge from the tag DAG.

    Args:
        db: Database connection.
        child_text: Child tag name/shorthand/alias.
        parent_text: Parent tag name/shorthand/alias.

    Raises:
        ValueError: If either tag cannot be resolved.
    """
    child = resolve_tag(db, child_text)
    parent = resolve_tag(db, parent_text)
    parent_repo = TagParentRepo(db)
    parent_repo.remove(child["id"], parent["id"])
