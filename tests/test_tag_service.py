"""Tests for sample_manager.tag_service — tag orchestration service (Phase 5).

Covers:
- resolve_tag: by name, shorthand, alias; hidden exclusion; not-found error
- resolve_or_create_tag: existing vs auto-create
- tag_sample / untag_sample: attach, idempotent, detach, error on missing sample/tag
- list_sample_tags: listing tags on a sample
- bulk_tag: multi-sample add/remove, idempotent, result counts
- bulk_tag_from_search: integration with SearchEngine
- add_tag_alias / remove_tag_alias: alias lifecycle
- add_tag_parent / remove_tag_parent: DAG edge lifecycle + cycle rejection
"""

import sqlite3

import pytest

from sample_manager.repos.library_root_repo import LibraryRootRepo
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.repos.sample_tag_repo import SampleTagRepo
from sample_manager.repos.tag_alias_repo import TagAliasRepo
from sample_manager.repos.tag_parent_repo import TagParentRepo
from sample_manager.repos.tag_repo import TagRepo
from sample_manager.tag_service import (
    BulkResult,
    add_tag_alias,
    add_tag_parent,
    bulk_tag,
    bulk_tag_from_search,
    list_sample_tags,
    remove_tag_alias,
    remove_tag_parent,
    resolve_or_create_tag,
    resolve_tag,
    tag_sample,
    untag_sample,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tag_repo(db):
    return TagRepo(db)


@pytest.fixture
def alias_repo(db):
    return TagAliasRepo(db)


@pytest.fixture
def sample_tag_repo(db):
    return SampleTagRepo(db)


@pytest.fixture
def parent_repo(db):
    return TagParentRepo(db)


@pytest.fixture
def sample_repo(db):
    return SampleRepo(db)


@pytest.fixture
def root_repo(db):
    return LibraryRootRepo(db)


def _make_sample(db, tmp_path, name="kick.wav"):
    """Helper: create a library root + sample, return sample dict."""
    root_repo = LibraryRootRepo(db)
    sample_repo = SampleRepo(db)
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    root = root_repo.get_or_create(str(lib))
    return sample_repo.upsert(root["id"], name, name)


# ---------------------------------------------------------------------------
# TestResolveTag
# ---------------------------------------------------------------------------


class TestResolveTag:
    def test_resolve_by_name(self, db, tag_repo):
        tag = tag_repo.create("Kick Drum")
        result = resolve_tag(db, "kick drum")
        assert result["id"] == tag["id"]
        assert result["name_display"] == "Kick Drum"

    def test_resolve_by_name_case_insensitive(self, db, tag_repo):
        tag = tag_repo.create("Snare")
        result = resolve_tag(db, "SNARE")
        assert result["id"] == tag["id"]

    def test_resolve_by_shorthand(self, db, tag_repo):
        tag = tag_repo.create("Hi-Hat")
        tag_repo.set_shorthand(tag["id"], "HH")
        result = resolve_tag(db, "hh")
        assert result["id"] == tag["id"]

    def test_resolve_by_alias(self, db, tag_repo, alias_repo):
        tag = tag_repo.create("Bass Drum")
        alias_repo.add(tag["id"], "BD")
        result = resolve_tag(db, "bd")
        assert result["id"] == tag["id"]

    def test_resolve_not_found_raises(self, db):
        with pytest.raises(ValueError, match="Tag not found"):
            resolve_tag(db, "nonexistent")

    def test_resolve_excludes_hidden_by_default(self, db, tag_repo):
        tag = tag_repo.create("Secret")
        tag_repo.hide(tag["id"])
        with pytest.raises(ValueError, match="Tag not found"):
            resolve_tag(db, "Secret")

    def test_resolve_includes_hidden_when_requested(self, db, tag_repo):
        tag = tag_repo.create("Secret")
        tag_repo.hide(tag["id"])
        result = resolve_tag(db, "Secret", include_hidden=True)
        assert result["id"] == tag["id"]


# ---------------------------------------------------------------------------
# TestResolveOrCreateTag
# ---------------------------------------------------------------------------


class TestResolveOrCreateTag:
    def test_returns_existing_tag(self, db, tag_repo):
        tag = tag_repo.create("Drums")
        result = resolve_or_create_tag(db, "drums")
        assert result["id"] == tag["id"]

    def test_creates_new_tag_when_not_found(self, db, tag_repo):
        result = resolve_or_create_tag(db, "Brand New Tag")
        assert result["name_display"] == "Brand New Tag"
        assert result["name_norm"] == "brand new tag"
        # Verify it persists
        found = tag_repo.get_by_name("brand new tag")
        assert found is not None
        assert found["id"] == result["id"]

    def test_resolve_via_alias_returns_existing(self, db, tag_repo, alias_repo):
        tag = tag_repo.create("Percussion")
        alias_repo.add(tag["id"], "perc")
        result = resolve_or_create_tag(db, "perc")
        assert result["id"] == tag["id"]


# ---------------------------------------------------------------------------
# TestTagSample
# ---------------------------------------------------------------------------


class TestTagSample:
    def test_tag_sample_creates_and_attaches(self, db, tmp_path):
        sample = _make_sample(db, tmp_path)
        tag = tag_sample(db, sample["id"], "Drums")
        assert tag["name_norm"] == "drums"
        # Verify attachment
        st_repo = SampleTagRepo(db)
        tags = st_repo.list_tags_for_sample(sample["id"])
        assert len(tags) == 1
        assert tags[0]["id"] == tag["id"]

    def test_tag_sample_idempotent(self, db, tmp_path):
        sample = _make_sample(db, tmp_path)
        tag1 = tag_sample(db, sample["id"], "Drums")
        tag2 = tag_sample(db, sample["id"], "Drums")
        assert tag1["id"] == tag2["id"]
        st_repo = SampleTagRepo(db)
        tags = st_repo.list_tags_for_sample(sample["id"])
        assert len(tags) == 1

    def test_tag_sample_resolves_alias(self, db, tmp_path, tag_repo, alias_repo):
        sample = _make_sample(db, tmp_path)
        tag = tag_repo.create("Percussion")
        alias_repo.add(tag["id"], "perc")
        result = tag_sample(db, sample["id"], "perc")
        assert result["id"] == tag["id"]

    def test_tag_sample_auto_creates_tag(self, db, tmp_path, tag_repo):
        sample = _make_sample(db, tmp_path)
        result = tag_sample(db, sample["id"], "NewAutoTag")
        assert result["name_display"] == "NewAutoTag"
        # Verify tag exists in DB
        found = tag_repo.get_by_name("newautotag")
        assert found is not None

    def test_tag_sample_invalid_sample_raises(self, db):
        with pytest.raises(ValueError, match="Sample not found"):
            tag_sample(db, 99999, "Drums")


# ---------------------------------------------------------------------------
# TestUntagSample
# ---------------------------------------------------------------------------


class TestUntagSample:
    def test_untag_sample(self, db, tmp_path, tag_repo):
        sample = _make_sample(db, tmp_path)
        tag = tag_repo.create("Drums")
        SampleTagRepo(db).attach(sample["id"], tag["id"])
        result = untag_sample(db, sample["id"], "Drums")
        assert result["id"] == tag["id"]
        # Verify detached
        tags = SampleTagRepo(db).list_tags_for_sample(sample["id"])
        assert len(tags) == 0

    def test_untag_unknown_tag_raises(self, db, tmp_path):
        sample = _make_sample(db, tmp_path)
        with pytest.raises(ValueError, match="Tag not found"):
            untag_sample(db, sample["id"], "nonexistent")

    def test_untag_invalid_sample_raises(self, db, tag_repo):
        tag_repo.create("Drums")
        with pytest.raises(ValueError, match="Sample not found"):
            untag_sample(db, 99999, "Drums")


# ---------------------------------------------------------------------------
# TestListSampleTags
# ---------------------------------------------------------------------------


class TestListSampleTags:
    def test_list_empty(self, db, tmp_path):
        sample = _make_sample(db, tmp_path)
        tags = list_sample_tags(db, sample["id"])
        assert tags == []

    def test_list_with_tags(self, db, tmp_path, tag_repo):
        sample = _make_sample(db, tmp_path)
        t1 = tag_repo.create("Drums")
        t2 = tag_repo.create("Kick")
        st_repo = SampleTagRepo(db)
        st_repo.attach(sample["id"], t1["id"])
        st_repo.attach(sample["id"], t2["id"])
        tags = list_sample_tags(db, sample["id"])
        assert len(tags) == 2
        names = {t["name_norm"] for t in tags}
        assert names == {"drums", "kick"}

    def test_list_invalid_sample_raises(self, db):
        with pytest.raises(ValueError, match="Sample not found"):
            list_sample_tags(db, 99999)


# ---------------------------------------------------------------------------
# TestBulkTag
# ---------------------------------------------------------------------------


class TestBulkTag:
    def test_bulk_add_single_tag(self, db, tmp_path):
        s1 = _make_sample(db, tmp_path, "kick.wav")
        s2 = _make_sample(db, tmp_path, "snare.wav")
        result = bulk_tag(db, [s1["id"], s2["id"]], add_tags=["Drums"])
        assert result.samples_matched == 2
        assert result.tags_added == ["Drums"]
        assert result.attachments_made == 2
        # Verify both samples tagged
        st_repo = SampleTagRepo(db)
        assert len(st_repo.list_tags_for_sample(s1["id"])) == 1
        assert len(st_repo.list_tags_for_sample(s2["id"])) == 1

    def test_bulk_add_and_remove(self, db, tmp_path, tag_repo):
        sample = _make_sample(db, tmp_path)
        old_tag = tag_repo.create("OldTag")
        SampleTagRepo(db).attach(sample["id"], old_tag["id"])
        result = bulk_tag(
            db, [sample["id"]], add_tags=["NewTag"], remove_tags=["OldTag"]
        )
        assert result.tags_added == ["NewTag"]
        assert result.tags_removed == ["OldTag"]
        tags = SampleTagRepo(db).list_tags_for_sample(sample["id"])
        names = {t["name_norm"] for t in tags}
        assert "newtag" in names
        assert "oldtag" not in names

    def test_bulk_idempotent(self, db, tmp_path):
        sample = _make_sample(db, tmp_path)
        bulk_tag(db, [sample["id"]], add_tags=["Drums"])
        result2 = bulk_tag(db, [sample["id"]], add_tags=["Drums"])
        # Still reports the operation, but no duplicate rows
        assert result2.attachments_made == 1
        tags = SampleTagRepo(db).list_tags_for_sample(sample["id"])
        assert len(tags) == 1

    def test_bulk_remove_unknown_tag_raises(self, db, tmp_path):
        sample = _make_sample(db, tmp_path)
        with pytest.raises(ValueError, match="Tag not found"):
            bulk_tag(db, [sample["id"]], remove_tags=["nonexistent"])

    def test_bulk_empty_sample_list(self, db):
        result = bulk_tag(db, [], add_tags=["Drums"])
        assert result.samples_matched == 0
        assert result.attachments_made == 0

    def test_bulk_result_to_dict(self):
        result = BulkResult(
            samples_matched=3,
            tags_added=["A", "B"],
            tags_removed=["C"],
            attachments_made=6,
            detachments_made=3,
        )
        d = result.to_dict()
        assert d["samples_matched"] == 3
        assert d["tags_added"] == ["A", "B"]
        assert d["detachments_made"] == 3


# ---------------------------------------------------------------------------
# TestBulkTagFromSearch
# ---------------------------------------------------------------------------


class TestBulkTagFromSearch:
    @pytest.fixture
    def search_data(self, db, tmp_path):
        """Create samples that the search engine can find."""
        root_repo = LibraryRootRepo(db)
        sample_repo = SampleRepo(db)
        lib = tmp_path / "searchlib"
        lib.mkdir()
        root = root_repo.get_or_create(str(lib))
        s1 = sample_repo.upsert(root["id"], "kick_hard.wav", "kick_hard.wav")
        s2 = sample_repo.upsert(root["id"], "kick_soft.wav", "kick_soft.wav")
        s3 = sample_repo.upsert(root["id"], "snare.wav", "snare.wav")
        return {"s1": s1, "s2": s2, "s3": s3}

    def test_bulk_from_search_adds_to_matching(self, db, search_data):
        result = bulk_tag_from_search(db, "kick", add_tags=["KickTag"])
        assert result.samples_matched == 2
        assert result.attachments_made == 2
        # snare should NOT be tagged
        tags_snare = SampleTagRepo(db).list_tags_for_sample(
            search_data["s3"]["id"]
        )
        assert len(tags_snare) == 0

    def test_bulk_from_search_no_matches(self, db, search_data):
        result = bulk_tag_from_search(db, "zzzznotfound", add_tags=["Tag"])
        assert result.samples_matched == 0

    def test_bulk_from_search_remove(self, db, search_data, tag_repo):
        # Pre-tag kick samples
        tag = tag_repo.create("ToRemove")
        st_repo = SampleTagRepo(db)
        st_repo.attach(search_data["s1"]["id"], tag["id"])
        st_repo.attach(search_data["s2"]["id"], tag["id"])
        result = bulk_tag_from_search(db, "kick", remove_tags=["ToRemove"])
        assert result.samples_matched == 2
        assert result.detachments_made == 2
        # Verify removed
        assert len(st_repo.list_tags_for_sample(search_data["s1"]["id"])) == 0


# ---------------------------------------------------------------------------
# TestAddRemoveAlias (service layer)
# ---------------------------------------------------------------------------


class TestTagAliasService:
    def test_add_alias(self, db, tag_repo):
        tag = tag_repo.create("Hi-Hat")
        row = add_tag_alias(db, "Hi-Hat", "HH")
        assert row["alias_norm"] == "hh"
        assert row["tag_id"] == tag["id"]

    def test_add_alias_unknown_tag_raises(self, db):
        with pytest.raises(ValueError, match="Tag not found"):
            add_tag_alias(db, "nonexistent", "alias")

    def test_add_alias_duplicate_raises(self, db, tag_repo):
        tag = tag_repo.create("Bass")
        add_tag_alias(db, "Bass", "low")
        with pytest.raises(sqlite3.IntegrityError):
            add_tag_alias(db, "Bass", "LOW")  # same alias_norm

    def test_remove_alias(self, db, tag_repo, alias_repo):
        tag = tag_repo.create("Snare")
        alias_repo.add(tag["id"], "snr")
        remove_tag_alias(db, "snr")
        # Verify gone
        assert alias_repo.list_for_tag(tag["id"]) == []


# ---------------------------------------------------------------------------
# TestAddRemoveParent (service layer)
# ---------------------------------------------------------------------------


class TestTagParentService:
    def test_add_parent(self, db, tag_repo):
        child = tag_repo.create("Kick")
        parent = tag_repo.create("Drums")
        add_tag_parent(db, "Kick", "Drums")
        pr = TagParentRepo(db)
        parents = pr.list_parents(child["id"])
        assert len(parents) == 1
        assert parents[0]["id"] == parent["id"]

    def test_add_parent_unknown_child_raises(self, db, tag_repo):
        tag_repo.create("Drums")
        with pytest.raises(ValueError, match="Tag not found"):
            add_tag_parent(db, "nonexistent", "Drums")

    def test_add_parent_unknown_parent_raises(self, db, tag_repo):
        tag_repo.create("Kick")
        with pytest.raises(ValueError, match="Tag not found"):
            add_tag_parent(db, "Kick", "nonexistent")

    def test_add_parent_cycle_rejected(self, db, tag_repo):
        tag_repo.create("A")
        tag_repo.create("B")
        add_tag_parent(db, "B", "A")
        with pytest.raises(ValueError, match="Cycle"):
            add_tag_parent(db, "A", "B")

    def test_remove_parent(self, db, tag_repo):
        tag_repo.create("Kick")
        tag_repo.create("Drums")
        add_tag_parent(db, "Kick", "Drums")
        remove_tag_parent(db, "Kick", "Drums")
        pr = TagParentRepo(db)
        kick = tag_repo.get_by_name("Kick")
        assert len(pr.list_parents(kick["id"])) == 0

    def test_remove_parent_unknown_tag_raises(self, db, tag_repo):
        tag_repo.create("Kick")
        with pytest.raises(ValueError, match="Tag not found"):
            remove_tag_parent(db, "Kick", "nonexistent")
