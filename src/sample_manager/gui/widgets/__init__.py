"""Qt widgets for the Sample Manager GUI.

Widgets are presentation-only. They never issue SQL or hold a ``Db`` — all data
arrives through the controller / ``LibraryBrowserService``.
"""

from .browser import BrowserWidget
from .preview import PreviewWidget
from .selection import SelectionWidget
from .session_summary import SessionSummaryWidget

__all__ = [
    "BrowserWidget",
    "PreviewWidget",
    "SelectionWidget",
    "SessionSummaryWidget",
]
