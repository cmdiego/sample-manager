"""Tests for sample_manager.search — SearchEngine + search/browse CLI commands.

Covers:
- SearchEngine query building (name, path, tag filters)
- Tag expansion (parent matches descendants)
- AND semantics for multiple tags
- Unknown tag returns empty results
- Pagination behavior
- Sort ordering
- CLI table and JSON output for search and browse commands
"""

import json

import pytest

from sample_manager.repos.library_root_repo import LibraryRootRepo
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.repos.sample_tag_repo import SampleTagRepo
from sample_manager.repos.tag_parent_repo import TagParentRepo
from sample_manager.repos.tag_repo import TagRepo
from sample_manager.search import SearchEngine, SearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def search_db(db):
    """Populate the test DB with fixture data for search tests.

    Library structure:
        root/
            drums/kick_hard.wav
            drums/kick_soft.wav
            drums/snare_crack.wav
            synths/pad_warm.flac
            synths/lead_bright.wav
            bass/sub_bass.mp3

    Tag hierarchy:
        Percussion (parent)
            -> Drums (child of Percussion)
                -> Kick (child of Drums)
        Synth (standalone)
        Bass (standalone)

    Tag assignments:
        kick_hard.wav   -> Kick
        kick_soft.wav   -> Kick
        snare_crack.wav -> Drums
        pad_warm.flac   -> Synth
        lead_bright.wav -> Synth
        sub_bass.mp3    -> Bass

    Returns:
        Dict with db, sample IDs, and tag IDs for assertions.
    """
    root_repo = LibraryRootRepo(db)
    sample_repo = SampleRepo(db)
    tag_repo = TagRepo(db)
    tag_parent_repo = TagParentRepo(db)
    sample_tag_repo = SampleTagRepo(db)

    # Create library root
    root = root_repo.get_or_create("/test/library")

    # Create samples
    samples = {}
    sample_data = [
        ("drums/kick_hard.wav", "kick_hard.wav", ".wav", 1024, 1000),
        ("drums/kick_soft.wav", "kick_soft.wav", ".wav", 2048, 2000),
        ("drums/snare_crack.wav", "snare_crack.wav", ".wav", 3072, 3000),
        ("synths/pad_warm.flac", "pad_warm.flac", ".flac", 4096, 4000),
        ("synths/lead_bright.wav", "lead_bright.wav", ".wav", 5120, 5000),
        ("bass/sub_bass.mp3", "sub_bass.mp3", ".mp3", 6144, 6000),
    ]
    for rel_path, filename, ext, size, mtime in sample_data:
        s = sample_repo.upsert(
            root["id"], rel_path, filename,
            ext=ext, size_bytes=size, mtime_epoch=mtime,
        )
        samples[filename] = s

    # Create tags
    tags = {}
    for name in ("Percussion", "Drums", "Kick", "Synth", "Bass"):
        tags[name] = tag_repo.create(name)

    # Build tag hierarchy: Kick -> Drums -> Percussion
    tag_parent_repo.add_parent(
        child_tag_id=tags["Drums"]["id"],
        parent_tag_id=tags["Percussion"]["id"],
    )
    tag_parent_repo.add_parent(
        child_tag_id=tags["Kick"]["id"],
        parent_tag_id=tags["Drums"]["id"],
    )

    # Assign tags to samples
    sample_tag_repo.attach(samples["kick_hard.wav"]["id"], tags["Kick"]["id"])
    sample_tag_repo.attach(samples["kick_soft.wav"]["id"], tags["Kick"]["id"])
    sample_tag_repo.attach(samples["snare_crack.wav"]["id"], tags["Drums"]["id"])
    sample_tag_repo.attach(samples["pad_warm.flac"]["id"], tags["Synth"]["id"])
    sample_tag_repo.attach(samples["lead_bright.wav"]["id"], tags["Synth"]["id"])
    sample_tag_repo.attach(samples["sub_bass.mp3"]["id"], tags["Bass"]["id"])

    return {
        "db": db,
        "root": root,
        "samples": samples,
        "tags": tags,
    }


@pytest.fixture
def engine(search_db):
    """SearchEngine backed by the populated search_db."""
    return SearchEngine(search_db["db"])


# ---------------------------------------------------------------------------
# SearchResult dataclass tests
# ---------------------------------------------------------------------------


class TestSearchResult:
    def test_to_dict_empty(self):
        r = SearchResult()
        d = r.to_dict()
        assert d == {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 50,
            "total_pages": 0,
        }

    def test_to_dict_with_data(self):
        r = SearchResult(
            items=[{"id": 1, "filename": "kick.wav"}],
            total=10,
            page=2,
            page_size=5,
            total_pages=2,
        )
        d = r.to_dict()
        assert d["total"] == 10
        assert d["page"] == 2
        assert len(d["items"]) == 1


# ---------------------------------------------------------------------------
# SearchEngine — no filters
# ---------------------------------------------------------------------------


class TestSearchNoFilters:
    def test_returns_all_samples(self, engine, search_db):
        result = engine.search()
        assert result.total == 6
        assert len(result.items) == 6

    def test_items_have_stable_columns(self, engine):
        result = engine.search()
        expected_keys = {"id", "filename", "rel_path", "ext", "size_bytes", "mtime_epoch"}
        for item in result.items:
            assert set(item.keys()) == expected_keys

    def test_default_pagination(self, engine):
        result = engine.search()
        assert result.page == 1
        assert result.page_size == 50
        assert result.total_pages == 1


# ---------------------------------------------------------------------------
# SearchEngine — name filter
# ---------------------------------------------------------------------------


class TestSearchByName:
    def test_name_filter_matches(self, engine):
        result = engine.search(name="kick")
        assert result.total == 2
        filenames = {item["filename"] for item in result.items}
        assert filenames == {"kick_hard.wav", "kick_soft.wav"}

    def test_name_filter_case_insensitive(self, engine):
        result = engine.search(name="KICK")
        assert result.total == 2

    def test_name_filter_partial_match(self, engine):
        result = engine.search(name="hard")
        assert result.total == 1
        assert result.items[0]["filename"] == "kick_hard.wav"

    def test_name_filter_no_match(self, engine):
        result = engine.search(name="zzz_nonexistent")
        assert result.total == 0
        assert result.items == []
        assert result.total_pages == 0


# ---------------------------------------------------------------------------
# SearchEngine — path filter
# ---------------------------------------------------------------------------


class TestSearchByPath:
    def test_path_filter_matches_directory(self, engine):
        result = engine.search(path="drums")
        assert result.total == 3
        filenames = {item["filename"] for item in result.items}
        assert filenames == {"kick_hard.wav", "kick_soft.wav", "snare_crack.wav"}

    def test_path_filter_case_insensitive(self, engine):
        result = engine.search(path="SYNTHS")
        assert result.total == 2

    def test_path_filter_no_match(self, engine):
        result = engine.search(path="nonexistent_dir")
        assert result.total == 0


# ---------------------------------------------------------------------------
# SearchEngine — tag filter
# ---------------------------------------------------------------------------


class TestSearchByTag:
    def test_direct_tag_match(self, engine, search_db):
        """Filtering by 'Kick' returns samples directly tagged with Kick."""
        result = engine.search(tags=["Kick"])
        assert result.total == 2
        filenames = {item["filename"] for item in result.items}
        assert filenames == {"kick_hard.wav", "kick_soft.wav"}

    def test_tag_expands_descendants_one_level(self, engine):
        """Filtering by 'Drums' expands to include Kick (child of Drums).

        Drums has: snare_crack.wav (directly)
        Kick has: kick_hard.wav, kick_soft.wav (descendants of Drums)
        Total: 3
        """
        result = engine.search(tags=["Drums"])
        assert result.total == 3
        filenames = {item["filename"] for item in result.items}
        assert filenames == {"kick_hard.wav", "kick_soft.wav", "snare_crack.wav"}

    def test_tag_expands_descendants_two_levels(self, engine):
        """Filtering by 'Percussion' expands through Drums to Kick.

        Percussion -> Drums -> Kick
        Matches: kick_hard.wav, kick_soft.wav (via Kick), snare_crack.wav (via Drums)
        """
        result = engine.search(tags=["Percussion"])
        assert result.total == 3
        filenames = {item["filename"] for item in result.items}
        assert filenames == {"kick_hard.wav", "kick_soft.wav", "snare_crack.wav"}

    def test_tag_standalone_no_descendants(self, engine):
        """Filtering by 'Bass' (no children) returns only directly tagged samples."""
        result = engine.search(tags=["Bass"])
        assert result.total == 1
        assert result.items[0]["filename"] == "sub_bass.mp3"

    def test_unknown_tag_returns_empty(self, engine):
        """An unresolvable tag should return 0 results."""
        result = engine.search(tags=["NoSuchTag"])
        assert result.total == 0
        assert result.items == []

    def test_tag_case_insensitive(self, engine):
        """Tag resolution is case-insensitive."""
        result = engine.search(tags=["kick"])
        assert result.total == 2

    def test_multiple_tags_and_semantics(self, engine, search_db):
        """Multiple tags use AND: sample must match ALL tag groups.

        Tag both kick samples with Bass as well to create an intersection test.
        """
        # Add Bass tag to kick_hard.wav only
        from sample_manager.repos.sample_tag_repo import SampleTagRepo
        sample_tag_repo = SampleTagRepo(search_db["db"])
        sample_tag_repo.attach(
            search_db["samples"]["kick_hard.wav"]["id"],
            search_db["tags"]["Bass"]["id"],
        )

        # Search for Kick AND Bass — only kick_hard.wav has both
        result = engine.search(tags=["Kick", "Bass"])
        assert result.total == 1
        assert result.items[0]["filename"] == "kick_hard.wav"

    def test_multiple_tags_and_no_overlap(self, engine):
        """If no sample has all tags, result is empty."""
        # Synth and Drums have no overlap
        result = engine.search(tags=["Synth", "Drums"])
        assert result.total == 0


# ---------------------------------------------------------------------------
# SearchEngine — combined filters
# ---------------------------------------------------------------------------


class TestSearchCombinedFilters:
    def test_name_and_tag(self, engine):
        """Name + tag filters combine with AND."""
        result = engine.search(name="hard", tags=["Kick"])
        assert result.total == 1
        assert result.items[0]["filename"] == "kick_hard.wav"

    def test_name_and_path(self, engine):
        """Name + path filters combine with AND."""
        result = engine.search(name="kick", path="drums")
        assert result.total == 2

    def test_path_and_tag(self, engine):
        """Path + tag filters combine with AND."""
        result = engine.search(path="synths", tags=["Synth"])
        assert result.total == 2

    def test_all_filters(self, engine):
        """Name + path + tag all combined."""
        result = engine.search(name="pad", path="synths", tags=["Synth"])
        assert result.total == 1
        assert result.items[0]["filename"] == "pad_warm.flac"


# ---------------------------------------------------------------------------
# SearchEngine — pagination
# ---------------------------------------------------------------------------


class TestSearchPagination:
    def test_page_size_limits_results(self, engine):
        result = engine.search(page_size=2)
        assert len(result.items) == 2
        assert result.total == 6
        assert result.page == 1

    def test_page_2(self, engine):
        result = engine.search(page=2, page_size=2, sort="name")
        assert len(result.items) == 2
        assert result.page == 2

    def test_last_page_partial(self, engine):
        """Last page may have fewer items than page_size."""
        result = engine.search(page=3, page_size=2, sort="name")
        assert len(result.items) == 2  # 6 items, page 3 of 3
        assert result.total == 6

    def test_page_beyond_total(self, engine):
        """Requesting a page beyond total_pages returns empty items."""
        result = engine.search(page=100, page_size=2)
        assert len(result.items) == 0
        assert result.total == 6
        assert result.total_pages == 3

    def test_total_pages_calculation(self, engine):
        result = engine.search(page_size=4)
        assert result.total == 6
        assert result.total_pages == 2  # ceil(6/4) = 2

    def test_total_pages_exact_division(self, engine):
        result = engine.search(page_size=3)
        assert result.total_pages == 2  # ceil(6/3) = 2

    def test_total_pages_single_page(self, engine):
        result = engine.search(page_size=10)
        assert result.total_pages == 1

    def test_page_clamped_to_minimum_1(self, engine):
        """Page number below 1 is clamped to 1."""
        result = engine.search(page=0)
        assert result.page == 1

    def test_pagination_with_filters(self, engine):
        """Pagination works correctly when combined with filters."""
        result = engine.search(name="kick", page=1, page_size=1)
        assert len(result.items) == 1
        assert result.total == 2
        assert result.total_pages == 2


# ---------------------------------------------------------------------------
# SearchEngine — sorting
# ---------------------------------------------------------------------------


class TestSearchSorting:
    def test_sort_by_name(self, engine):
        result = engine.search(sort="name")
        filenames = [item["filename"] for item in result.items]
        assert filenames == sorted(filenames)

    def test_sort_by_size(self, engine):
        result = engine.search(sort="size")
        sizes = [item["size_bytes"] for item in result.items]
        assert sizes == sorted(sizes)

    def test_sort_by_mtime(self, engine):
        result = engine.search(sort="mtime")
        mtimes = [item["mtime_epoch"] for item in result.items]
        assert mtimes == sorted(mtimes)

    def test_invalid_sort_raises(self, engine):
        with pytest.raises(ValueError, match="Invalid sort"):
            engine.search(sort="bogus")


# ---------------------------------------------------------------------------
# CLI — search command
# ---------------------------------------------------------------------------


class TestSearchCLI:
    """End-to-end tests for `sample search` via CliRunner."""

    @pytest.fixture(autouse=True)
    def _setup_cli(self, tmp_path, monkeypatch, search_db):
        """Set up config so CLI can find the DB."""
        from sample_manager import config as config_module

        config_dir = tmp_path / "cli_home" / ".sample_manager"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.yaml"

        # Point config to the test DB
        db_path = search_db["db"]._path
        config_path.write_text(
            f"db_path: {db_path}\n"
            f"library_roots: []\n"
            f"default_library_root: null\n"
            f"defaults:\n"
            f"  export_mode: copy\n"
        )

        monkeypatch.setattr(config_module, "get_config_path", lambda: config_path)
        self.search_db = search_db

    def test_search_table_output(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["search", "kick"])
        assert result.exit_code == 0
        assert "kick_hard.wav" in result.output
        assert "kick_soft.wav" in result.output
        # Check column headers
        assert "id" in result.output
        assert "filename" in result.output
        assert "rel_path" in result.output

    def test_search_json_output(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["search", "kick", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # Verify item schema
        for item in data["items"]:
            assert "id" in item
            assert "filename" in item
            assert "rel_path" in item
            assert "ext" in item
            assert "size_bytes" in item
            assert "mtime_epoch" in item

    def test_search_no_results(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["search", "zzz_nothing"])
        assert result.exit_code == 0
        assert "No samples found" in result.output

    def test_search_with_name_flag(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["search", "--name", "snare"])
        assert result.exit_code == 0
        assert "snare_crack.wav" in result.output

    def test_search_with_tag_flag(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["search", "--tag", "Kick"])
        assert result.exit_code == 0
        assert "kick_hard.wav" in result.output
        assert "kick_soft.wav" in result.output
        # Should not include non-kick samples
        assert "snare_crack.wav" not in result.output
        assert "pad_warm.flac" not in result.output

    def test_search_with_path_flag(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["search", "--path", "synths"])
        assert result.exit_code == 0
        assert "pad_warm.flac" in result.output
        assert "lead_bright.wav" in result.output

    def test_search_json_with_tag_expansion(self, cli_runner):
        """Tag 'Percussion' should expand to include Drums and Kick samples."""
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["search", "--tag", "Percussion", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 3
        filenames = {item["filename"] for item in data["items"]}
        assert filenames == {"kick_hard.wav", "kick_soft.wav", "snare_crack.wav"}

    def test_search_pagination_flags(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(
            app, ["search", "--page", "1", "--page-size", "2", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["items"]) == 2
        assert data["total"] == 6
        assert data["total_pages"] == 3


# ---------------------------------------------------------------------------
# CLI — browse command
# ---------------------------------------------------------------------------


class TestBrowseCLI:
    """End-to-end tests for `sample browse` via CliRunner."""

    @pytest.fixture(autouse=True)
    def _setup_cli(self, tmp_path, monkeypatch, search_db):
        """Set up config so CLI can find the DB."""
        from sample_manager import config as config_module

        config_dir = tmp_path / "cli_home" / ".sample_manager"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.yaml"

        db_path = search_db["db"]._path
        config_path.write_text(
            f"db_path: {db_path}\n"
            f"library_roots: []\n"
            f"default_library_root: null\n"
            f"defaults:\n"
            f"  export_mode: copy\n"
        )

        monkeypatch.setattr(config_module, "get_config_path", lambda: config_path)
        self.search_db = search_db

    def test_browse_returns_all_samples(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["browse", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 6

    def test_browse_table_output(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["browse"])
        assert result.exit_code == 0
        # Should show all samples
        assert "kick_hard.wav" in result.output
        assert "sub_bass.mp3" in result.output
        assert "Page 1" in result.output

    def test_browse_pagination(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(
            app, ["browse", "--page", "2", "--page-size", "2", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["items"]) == 2
        assert data["page"] == 2
        assert data["total_pages"] == 3

    def test_browse_sort_by_size(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["browse", "--sort", "size", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        sizes = [item["size_bytes"] for item in data["items"]]
        assert sizes == sorted(sizes)

    def test_browse_sort_by_mtime(self, cli_runner):
        from sample_manager.cli import app

        result = cli_runner.invoke(app, ["browse", "--sort", "mtime", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        mtimes = [item["mtime_epoch"] for item in data["items"]]
        assert mtimes == sorted(mtimes)
