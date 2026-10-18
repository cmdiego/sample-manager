"""Read-only presentation of technical properties and embedded file tags."""

from pathlib import Path
import re

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ...audio.metadata import ContainerMetadata


def metadata_rows(metadata: ContainerMetadata) -> tuple[tuple[str, str], ...]:
    """List native tags first, then available technical properties."""
    rows = list(metadata.tags)
    if not metadata.tags:
        rows.append(("Embedded tags", "None found"))
    for label, value in (
        ("Format", metadata.format),
        ("Duration", f"{metadata.duration_seconds:.3f} s" if metadata.duration_seconds is not None else None),
        ("Sample rate", f"{metadata.sample_rate:,} Hz" if metadata.sample_rate else None),
        ("Channels", str(metadata.channels) if metadata.channels else None),
        ("Bit depth", f"{metadata.bit_depth} bit" if metadata.bit_depth else None),
        ("Bitrate", f"{metadata.bitrate / 1000:g} kbps" if metadata.bitrate else None),
    ):
        if value:
            rows.append((label, value))
    return tuple(rows)


def musical_summary(
    metadata: ContainerMetadata | None, library_tags: tuple[str, ...],
) -> str:
    """Prioritize musical context without inferring missing tempo/key values."""
    fields = {}
    for label, value in metadata.tags if metadata is not None else ():
        # ID3 TXXX and MP4 freeform names retain their namespace/description.
        # Recognize their descriptive key as well as standard native fields.
        name = label
        if "(" in name and name.endswith(")"):
            name = name.partition("(")[2][:-1].rsplit(":", 1)[-1]
        normalized = "".join(char for char in name.casefold() if char.isalnum())
        fields.setdefault(normalized, value)

    def value(*names: str) -> str:
        """Return the first populated alias, keeping unknown values explicit."""
        return next((fields[name] for name in names if fields.get(name)), "—")

    tempo = value("bpm", "tempo", "beatsperminute")
    if re.fullmatch(r"\d+(?:[.,]\d+)?", tempo):
        tempo += " BPM"
    key = value("key", "initialkey", "musicalkey", "tonality")
    tags = " · ".join(library_tags) if library_tags else "None · t Edit"
    # Keep these three rows first, even in a 24-line terminal. Long artist or
    # title fields cannot displace the requested tempo/key, genre, and tags.
    rows = [
        f"Tempo: {tempo} · Key: {key}",
        f"Genre: {value('genre')}",
        f"Tags: {tags}",
    ]
    for label, aliases in (
        ("File tags", ("tags", "keywords", "keyword")),
        ("Artist", ("artist", "albumartist")),
        ("Title", ("title",)),
        ("Album", ("album",)),
    ):
        text = value(*aliases)
        if text != "—":
            rows.append(f"{label}: {text}")
    return "\n".join(rows)


class MetadataPanel(VerticalScroll):
    """Compact musical summary retaining complete native metadata for i."""

    def __init__(self, **kwargs) -> None:
        """Retain the result across refreshes of the same focused sample."""
        super().__init__(**kwargs)
        self.path: Path | None = None
        self.rows: tuple[tuple[str, str], ...] = ()
        self.library_tags: tuple[str, ...] = ()
        self._metadata: ContainerMetadata | None = None
        self.message = "Choose a sample to inspect"
        self._text = Static(self.message, markup=False, classes="embedded-values")

    def compose(self) -> ComposeResult:
        """Prioritize the musical summary and advertise the complete metadata view."""
        yield Static("Sample details · i Metadata", classes="embedded-title", markup=False)
        yield self._text

    def set_target(self, path: Path | None) -> None:
        """Clear old metadata immediately when focus moves to another sample."""
        if path != self.path:
            self.path = path
            self.rows = ()
            self.library_tags = ()
            self._metadata = None
            self.message = "Reading metadata…" if path else "Choose a sample to inspect"
            self._render_summary()
            if self.is_mounted:
                self.scroll_home(animate=False)

    def set_result(self, path: Path, metadata: ContainerMetadata | None, error: str = "") -> None:
        """Apply only the current target's result, treating errors as nonfatal."""
        if path != self.path:
            return
        self._metadata = metadata
        self.rows = metadata_rows(metadata) if metadata is not None else ()
        self.message = error
        self._render_summary()

    def set_library_tags(self, tags: list[str]) -> None:
        """Reflect assigned tag edits immediately without rereading the file."""
        self.library_tags = tuple(str(tag) for tag in tags)
        self._render_summary()

    def _render_summary(self) -> None:
        """Render literal values; retained full rows remain available to the modal."""
        text = musical_summary(self._metadata, self.library_tags) if self.path else self.message
        self._text.update(text)
