"""Internal drag payload for moving indexed samples into the persistent Stage."""

from __future__ import annotations

from PySide6.QtCore import QMimeData


SAMPLE_MIME_TYPE = "application/x-sample-manager-sample-id"


def sample_mime(sample_id: int) -> QMimeData:
    """Encode one indexed sample ID for a Browser → Stage copy drag."""
    mime = QMimeData()
    mime.setData(SAMPLE_MIME_TYPE, str(sample_id).encode("ascii"))
    return mime


def sample_id_from_mime(mime: QMimeData) -> int | None:
    """Accept only a positive integer sample ID from our internal MIME type."""
    if not mime.hasFormat(SAMPLE_MIME_TYPE):
        return None
    try:
        sample_id = int(bytes(mime.data(SAMPLE_MIME_TYPE)).decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None
    return sample_id if sample_id > 0 else None
