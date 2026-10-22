"""Native metadata loading, presentation and lifecycle through real TUI events."""

import asyncio
from threading import Event

import pytest
from textual.widgets import Static

from sample_manager.audio import WaveformBin, WaveformData
from sample_manager.audio.backends import BackendUnavailable
from sample_manager.audio.metadata import ContainerMetadata, read_metadata
from sample_manager.tui.widgets.metadata_panel import MetadataPanel
from sample_manager.tui.widgets.metadata_screen import MetadataScreen
from sample_manager.tui.widgets.top_display import TopDisplayWidget
from test_tui_navigation import _NavigationTestApp


def _metadata(path, tags=()):
    """Build a typed reader result without invoking an audio device."""
    return ContainerMetadata(str(path), ".wav", "WAVE", 1.0, 44100, 2, None, 16, tags)


def _app(tmp_path, reader):
    """Mount production layout and metadata worker against disposable files."""
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "kick.wav").write_bytes(b"RIFF0000")
    (first / "snare.wav").write_bytes(b"RIFF1111")
    app = _NavigationTestApp((first, second))
    app.fake_data.add_to_selection = app.fake_data.selected.add
    app._metadata_reader = reader
    return app


async def _settle(app, pilot):
    """Drain metadata workers and pending Textual row mounts."""
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
def test_panel_geometry_full_view_and_selection_reuse(tmp_path, size):
    """Tags fit beside the waveform; the full view retains literal long values."""
    calls = []
    long_comment = "[literal] comment " * 100

    def reader(path):
        """Record I/O so selection refreshes cannot silently reread files."""
        calls.append(path)
        return _metadata(path, (("Title", "[Loop]"), ("Artist", "Artist"), ("Comment", long_comment)))

    async def exercise():
        app = _app(tmp_path, reader)
        async with app.run_test(size=size) as pilot:
            await _settle(app, pilot)
            preview = app.query_one(TopDisplayWidget)
            panel = preview.metadata_panel
            assert panel.region.right <= preview.content_region.right
            waveform = preview._waveform
            assert waveform.region.right <= panel.region.x
            assert panel.region.width >= 30
            waveform.set_data(WaveformData(waveform.path, 1.0, (WaveformBin(-0.5, 0.5),)))
            assert len(waveform.render().plain.splitlines()[0]) == waveform.size.width
            assert dict(panel.rows)["Title"] == "[Loop]"
            assert dict(panel.rows)["Sample rate"] == "44,100 Hz"
            await pilot.press("enter", "enter")
            await _settle(app, pilot)
            assert len(calls) == 1
            assert preview._waveform is waveform
            await pilot.press("i")
            await pilot.pause()
            assert isinstance(app.screen, MetadataScreen)
            dialog = app.screen.query_one("#metadata-dialog")
            assert dialog.region.width <= size[0] and dialog.region.bottom <= size[1]
            values = app.screen.query_one("#metadata-full-values", Static)
            assert long_comment in values.content
            assert "[literal]" in values.visual.plain
            await pilot.press("pagedown")
            await pilot.pause()
            assert dialog.scroll_y > 0
            await pilot.press("q")
            assert app.is_running and len(app.screen_stack) == 1
            await pilot.press("/", "i")
            assert app._filter_query == "i"  # Search still owns printable keys.

    asyncio.run(exercise())


def test_stale_metadata_cannot_replace_new_focus(tmp_path):
    """A slow first file cannot populate the second file or its expanded view."""
    release = Event()
    started = Event()

    def reader(path):
        """Hold the first read while the second finishes immediately."""
        if path.name == "kick.wav":
            started.set()
            if not release.wait(timeout=5):
                raise RuntimeError("Metadata test did not release worker")
        return _metadata(path, (("Title", path.name),))

    async def exercise():
        app = _app(tmp_path, reader)
        try:
            async with app.run_test() as pilot:
                await pilot.pause()
                assert await asyncio.to_thread(started.wait, 2)
                await pilot.press("down", "i")
                release.set()
                await _settle(app, pilot)
                assert isinstance(app.screen, MetadataScreen)
                await pilot.pause(0.15)
                text = app.screen.query_one("#metadata-full-values", Static).content
                assert "snare.wav" in text and "kick.wav" not in text
        finally:
            release.set()

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", [None, ValueError("bad header"), BackendUnavailable("no mutagen")])
def test_no_tags_and_metadata_failures_are_nonfatal(tmp_path, failure):
    """Missing tags, corrupt files and optional readers each have truthful states."""
    def reader(path):
        """Return a tagless file or simulate the relevant backend error."""
        if failure is not None:
            raise failure
        return _metadata(path)

    async def exercise():
        app = _app(tmp_path, reader)
        async with app.run_test() as pilot:
            await _settle(app, pilot)
            panel = app.query_one(MetadataPanel)
            if failure is None:
                assert dict(panel.rows)["Embedded tags"] == "None found"
                assert dict(panel.rows)["Bit depth"] == "16 bit"
            else:
                assert "unavailable" in panel.message.lower()
                assert not panel.rows
            await pilot.press("down", "tab")
            assert app._active_pane == "stage" and app.is_running

    asyncio.run(exercise())


def test_real_id3_fields_reach_the_panel(tmp_path, write_sine_wav):
    """A generated tagged audio file reaches the TUI through the actual reader."""
    pytest.importorskip("mutagen")
    from mutagen.wave import WAVE
    from mutagen.id3 import TIT2

    async def exercise():
        app = _app(tmp_path, read_metadata)
        path = app.test_roots[0] / "kick.wav"
        write_sine_wav(path, seconds=0.1)
        audio = WAVE(path)
        audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text=["Embedded title"]))
        audio.save()
        async with app.run_test() as pilot:
            await _settle(app, pilot)
            assert dict(app.query_one(MetadataPanel).rows)["Title"] == "Embedded title"

    asyncio.run(exercise())


@pytest.mark.parametrize("tags, expected", [
    ((("BPM", "98"), ("Key", "Am"), ("Genre", "Disco")), "Tempo: 98 BPM · Key: Am\nGenre: Disco"),
    ((("Custom (TEMPO)", "98.5"), ("---- (com.apple.iTunes:INITIALKEY)", "8A")), "Tempo: 98.5 BPM · Key: 8A\nGenre: —"),
    ((), "Tempo: — · Key: —\nGenre: —"),
])
def test_summary_recognizes_native_custom_and_missing_musical_fields(tags, expected):
    """Standard/custom aliases work without inventing missing musical values."""
    from pathlib import Path
    from sample_manager.tui.widgets.metadata_panel import musical_summary

    text = musical_summary(_metadata(Path("loop.wav"), tags), ("drums", "loop"))
    assert text.startswith(expected)
    assert text.splitlines()[2] == "Tags: drums · loop"


def test_summary_keeps_core_fields_visible_and_full_metadata_available(tmp_path):
    """Long low-priority metadata never displaces musical context at 80×24."""
    calls = []

    def reader(path):
        """Return title first to ensure source order cannot crowd out core fields."""
        calls.append(path)
        return _metadata(path, (
            ("Title", "Long title " * 100), ("Comment", "Comment " * 100),
            ("BPM", "98"), ("Key", "Am"), ("Genre", "Disco"),
            ("Keywords", "[vinyl]; funk"),
        ))

    async def exercise():
        app = _app(tmp_path, reader)
        original_details = app.fake_data.get_sample_details
        app.fake_data.get_sample_details = lambda sid: dict(original_details(sid), tags=["drums", "loop"])
        async with app.run_test(size=(80, 24)) as pilot:
            await _settle(app, pilot)
            panel = app.query_one(MetadataPanel)
            text = panel.query_one(".embedded-values", Static)
            assert text.content.splitlines()[:3] == [
                "Tempo: 98 BPM · Key: Am", "Genre: Disco", "Tags: drums · loop",
            ]
            assert text.region.y + 3 <= panel.content_region.bottom
            assert "File tags: [vinyl]; funk" in text.content
            assert "Comment" not in text.content
            # Assigned tag changes refresh synchronously, preserving native data.
            waveform = app.query_one(TopDisplayWidget)._waveform
            app.fake_data.get_sample_details = lambda sid: dict(original_details(sid), tags=["new [tag]"])
            app._refresh_ui(audition=False)
            await pilot.pause()
            assert "Tags: new [tag]" in text.visual.plain
            assert "Tempo: 98 BPM" in text.content and len(calls) == 1
            assert app.query_one(TopDisplayWidget)._waveform is waveform
            await pilot.press("i")
            assert isinstance(app.screen, MetadataScreen)
            values = app.screen.query_one("#metadata-full-values", Static)
            assert "Library tags: new [tag]" in values.content
            assert "Keywords: [vinyl]; funk" in values.content
            assert "Comment: " + "Comment " * 100 in values.content
            assert "Sample rate: 44,100 Hz" in values.content

    asyncio.run(exercise())


def test_summary_keeps_library_tags_when_native_metadata_is_unavailable(tmp_path):
    """A native read failure must not hide user-assigned tags or its own error."""
    def reader(_path):
        """Simulate a bad native header while keeping library data available."""
        raise ValueError("bad header")

    async def exercise():
        app = _app(tmp_path, reader)
        original = app.fake_data.get_sample_details
        app.fake_data.get_sample_details = lambda sid: dict(original(sid), tags=["drums"])
        async with app.run_test(size=(80, 24)) as pilot:
            await _settle(app, pilot)
            panel = app.query_one(MetadataPanel)
            text = panel.query_one(".embedded-values", Static).content
            assert "Tempo: — · Key: —" in text and "Tags: drums" in text
            await pilot.press("i")
            values = app.screen.query_one("#metadata-full-values", Static).content
            assert "Library tags: drums" in values and "bad header" in values

    asyncio.run(exercise())
