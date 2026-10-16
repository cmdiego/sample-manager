"""Repository layer for Sample Manager SQLite persistence.

Each repo class wraps a single table (or closely related set of tables)
and provides typed CRUD operations backed by the Db wrapper.
"""

from .library_root_repo import LibraryRootRepo
from .arrangement_repo import ArrangementRepo
from .sample_repo import SampleRepo
from .selection_repo import SelectionRepo
from .export_repo import ExportRunRepo, HistoryEntryRepo
from .tag_repo import TagRepo
from .tag_alias_repo import TagAliasRepo
from .sample_tag_repo import SampleTagRepo
from .tag_parent_repo import TagParentRepo
from .sample_analysis_repo import SampleAnalysisRepo

__all__ = [
    "LibraryRootRepo",
    "ArrangementRepo",
    "SampleRepo",
    "SelectionRepo",
    "ExportRunRepo",
    "HistoryEntryRepo",
    "TagRepo",
    "TagAliasRepo",
    "SampleTagRepo",
    "TagParentRepo",
    "SampleAnalysisRepo",
]
