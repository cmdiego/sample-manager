"""Search engine for querying samples by name, path, and tags.

Builds parameterized SQL queries against the sample table, with optional
tag filtering that expands to include descendant tags via TagGraphService.

Per docs/03-cli.md: search supports name pattern, path fragments, and tag filters.
Per docs/01-data-model.md: filtering by a tag expands to include descendant tags.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .db import Db
from .normalize import norm_rel_path, norm_text
from .repos.tag_alias_repo import TagAliasRepo
from .tag_graph import TagGraphService


# Stable output columns per the output contract
_SELECT_COLUMNS = (
    "s.id",
    "s.filename",
    "s.rel_path",
    "s.ext",
    "s.size_bytes",
    "s.mtime_epoch",
)

_SORT_MAP = {
    "name": "s.filename",
    "mtime": "s.mtime_epoch",
    "size": "s.size_bytes",
}


@dataclass
class SearchResult:
    """Result envelope for paginated search queries.

    Attributes:
        items: List of sample dicts with stable column keys.
        total: Total number of matching rows (before pagination).
        page: Current page number (1-indexed).
        page_size: Maximum items per page.
        total_pages: ceil(total / page_size).
    """

    items: list[dict] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
        }


class SearchEngine:
    """SQL-backed search over the sample table.

    Supports filtering by:
      - name pattern (LIKE on filename)
      - path fragment (LIKE on rel_path_norm)
      - tags (resolved via TagAliasRepo, expanded via TagGraphService)

    Multiple --tag filters use AND semantics: a sample must match ALL
    specified tag groups to be included.
    """

    def __init__(self, db: Db) -> None:
        self._db = db
        self._tag_alias_repo = TagAliasRepo(db)
        self._tag_graph = TagGraphService(db)

    def search(
        self,
        *,
        name: str | None = None,
        path: str | None = None,
        tags: list[str] | None = None,
        sort: str = "name",
        page: int = 1,
        page_size: int = 50,
    ) -> SearchResult:
        """Execute a paginated search query.

        Args:
            name: Filename pattern (LIKE '%name%', case-insensitive).
            path: Relative path fragment (LIKE '%path%' on rel_path_norm).
            tags: List of tag strings to filter by (AND semantics).
                  Each tag is resolved via name/shorthand/alias chain,
                  then expanded to include all descendant tags.
            sort: Sort column — one of 'name', 'mtime', 'size'.
            page: Page number (1-indexed, default 1).
            page_size: Results per page (default 50).

        Returns:
            SearchResult with paginated items and metadata.
        """
        # Validate sort
        sort_col = _SORT_MAP.get(sort)
        if sort_col is None:
            raise ValueError(
                f"Invalid sort: {sort!r}. Must be one of: {', '.join(_SORT_MAP)}"
            )

        # Clamp pagination
        page = max(1, page)
        page_size = max(1, min(page_size, 1000))

        # Resolve tag filters.
        # _resolve_tags returns None if any tag is unresolvable (-> empty result),
        # or a list of expanded ID sets on success.
        tag_groups: list[set[int]] | None = None
        if tags:
            resolved = self._resolve_tags(tags)
            if resolved is None:
                # Unresolvable tag — return empty result
                return SearchResult(
                    items=[],
                    total=0,
                    page=page,
                    page_size=page_size,
                    total_pages=0,
                )
            tag_groups = resolved

        # Build query parts
        select_cols = ", ".join(_SELECT_COLUMNS)
        from_clause = "FROM sample s"
        where_clauses: list[str] = []
        join_params: list = []
        where_params: list = []
        having_params: list = []
        group_by = ""
        having = ""

        # Tag joins: for AND semantics with N tag groups, we need the sample
        # to appear in sample_tag for at least one tag from each group.
        # We use a single JOIN + GROUP BY + HAVING COUNT(DISTINCT ...) approach.
        if tag_groups is not None:
            # Flatten all expanded tag IDs for the JOIN filter
            all_tag_ids: set[int] = set()
            for group in tag_groups:
                all_tag_ids |= group

            placeholders = ", ".join("?" * len(all_tag_ids))
            from_clause += (
                f" JOIN sample_tag st ON st.sample_id = s.id"
                f" AND st.tag_id IN ({placeholders})"
            )
            join_params.extend(sorted(all_tag_ids))

            if len(tag_groups) > 1:
                # Test every group independently. Expanded parent/child groups
                # can overlap, and one tag is allowed to satisfy both groups.
                group_checks: list[str] = []
                for group in tag_groups:
                    tag_list = ", ".join("?" * len(group))
                    group_checks.append(
                        f"SUM(CASE WHEN st.tag_id IN ({tag_list}) THEN 1 ELSE 0 END) > 0"
                    )
                    having_params.extend(sorted(group))
                group_by = "GROUP BY s.id"
                having = "HAVING " + " AND ".join(group_checks)
            else:
                # Single tag group — just need the JOIN, no GROUP BY needed
                # but we need DISTINCT to avoid duplicates
                group_by = "GROUP BY s.id"

        # Name filter
        if name is not None:
            where_clauses.append("s.filename LIKE ?")
            where_params.append(f"%{name}%")

        # Path filter
        if path is not None:
            normalized_path = path.lower()
            where_clauses.append("s.rel_path_norm LIKE ?")
            where_params.append(f"%{normalized_path}%")

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Count query (same filters, no pagination)
        # Bind parameters in SQL appearance order: JOIN, WHERE, then HAVING.
        params = tuple(join_params + where_params + having_params)
        count_sql = f"SELECT COUNT(*) FROM (SELECT s.id {from_clause} {where_sql} {group_by} {having})"
        total = self._db.fetchval(count_sql, params) or 0

        # Calculate pagination
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        # Data query with sort + pagination
        offset = (page - 1) * page_size
        order_sql = f"ORDER BY {sort_col}"

        data_sql = (
            f"SELECT {select_cols} {from_clause} {where_sql} "
            f"{group_by} {having} {order_sql} LIMIT ? OFFSET ?"
        )
        data_params = list(params) + [page_size, offset]

        rows = self._db.fetchall(data_sql, tuple(data_params))
        items = [
            {
                "id": row["id"],
                "filename": row["filename"],
                "rel_path": row["rel_path"],
                "ext": row["ext"],
                "size_bytes": row["size_bytes"],
                "mtime_epoch": row["mtime_epoch"],
            }
            for row in rows
        ]

        return SearchResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def _resolve_tags(
        self, tags: list[str]
    ) -> list[set[int]] | None:
        """Resolve tag strings to expanded ID sets.

        Each tag string is resolved via TagAliasRepo.resolve() (name -> shorthand
        -> alias chain), then expanded via TagGraphService.expand_for_search()
        to include all descendant tags.

        Args:
            tags: List of tag name/shorthand/alias strings.

        Returns:
            List of sets, one per input tag, each containing the expanded tag IDs.
            Returns None if any tag cannot be resolved (signals empty result).
        """
        groups: list[set[int]] = []
        for tag_text in tags:
            tag_id = self._tag_alias_repo.resolve(tag_text)
            if tag_id is None:
                return None
            expanded = self._tag_graph.expand_for_search([tag_id])
            groups.append(expanded)
        return groups
