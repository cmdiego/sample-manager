"""Stage summary zone — selection count, total bytes, export destination.

Presentation-only. It renders a ``SelectionSummary`` DTO supplied by the
controller; it never touches the DB.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...services.library_browser import SelectionSummary


def _human_size(num: int | None) -> str:
    if not num:
        return "0 B"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


class SessionSummaryWidget(QWidget):
    """Shows aggregate stats for the persistent selection buffer."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SessionSummaryWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        heading = QLabel("Stage Summary")
        heading.setObjectName("SessionHeading")
        layout.addWidget(heading)

        self._count = QLabel("Staged: 0")
        self._bytes = QLabel("Total: 0 B")
        self._dest = QLabel("Destination: —")
        self._dest.setWordWrap(True)
        for lbl in (self._count, self._bytes, self._dest):
            lbl.setObjectName("SessionMeta")
            layout.addWidget(lbl)

        layout.addStretch(1)

    def set_summary(self, summary: SelectionSummary) -> None:
        self._count.setText(f"Staged: {summary.count}")
        self._bytes.setText(f"Total: {_human_size(summary.total_bytes)}")
        self._dest.setText(f"Destination: {summary.destination or '—'}")
