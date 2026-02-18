"""Tests for all repository classes (Phase 2).

Covers: LibraryRootRepo, SampleRepo, TagRepo, TagAliasRepo, SampleTagRepo, TagParentRepo.
Uses the shared `db` fixture from conftest.py (fresh DB with Migration 0001 applied).
"""

import sqlite3

import pytest

from sample_manager.repos.library_root_repo import LibraryRootRepo
from sample_manager.repos.sample_repo import SampleRepo
from sample_manager.repos.tag_repo import TagRepo
from sample_manager.repos.tag_alias_repo import TagAliasRepo
from sample_manager.repos.sample_tag_repo import SampleTagRepo
from sample_manager.repos.tag_parent_repo import TagParentRepo


# ============================= Fixtures =====================================

@pytest.fixture
def root_repo(db):
    return LibraryRootRepo(db)


@pytest.fixture
def sample_repo(db):
    return SampleRepo(db)


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


# ============================= LibraryRootRepo ==============================

class TestLibraryRootRepo:
    def test_get_or_create_new(self, root_repo, tmp_path):
        lib = tmp_path / "samples"
        lib.mkdir()
        row = root_repo.get_or_create(str(lib))
        assert row["id"] is not None
        assert row["path"] == str(lib)
        assert row["path_norm"]  # non-empty normalized path

    def test_get_or_create_returns_existing(self, root_repo, tmp_path):
        lib = tmp_path / "samples"
        lib.mkdir()
        row1 = root_repo.get_or_create(str(lib))
        row2 = root_repo.get_or_create(str(lib))
        assert row1["id"] == row2["id"]

    def test_get_or_create_case_insensitive(self, root_repo, tmp_path):
        """Different casing of same path should resolve to same root (via path_norm)."""
        lib = tmp_path / "Samples"
        lib.mkdir()
        row1 = root_repo.get_or_create(str(lib))
        # On macOS/Windows, different casing resolves to same path.
        # On Linux they'd be different dirs. Since we always lowercase path_norm,
        # this tests the norm behavior.
        row2 = root_repo.get_or_create(str(lib))
        assert row1["id"] == row2["id"]

    def test_path_norm_uniqueness(self, root_repo, tmp_path):
        """Two distinct directories produce different path_norms."""
        lib1 = tmp_path / "lib1"
        lib2 = tmp_path / "lib2"
        lib1.mkdir()
        lib2.mkdir()
        row1 = root_repo.get_or_create(str(lib1))
        row2 = root_repo.get_or_create(str(lib2))
        assert row1["id"] != row2["id"]
        assert row1["path_norm"] != row2["path_norm"]

    def test_get_by_id(self, root_repo, tmp_path):
        lib = tmp_path / "mylib"
        lib.mkdir()
        created = root_repo.get_or_create(str(lib))
        fetched = root_repo.get_by_id(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_by_id_not_found(self, root_repo):
        assert root_repo.get_by_id(99999) is None

    def test_list_all(self, root_repo, tmp_path):
        lib1 = tmp_path / "a"
        lib2 = tmp_path / "b"
        lib1.mkdir()
        lib2.mkdir()
        root_repo.get_or_create(str(lib1))
        root_repo.get_or_create(str(lib2))
        roots = root_repo.list_all()
        assert len(roots) == 2


# ============================= SampleRepo ===================================

class TestSampleRepo:
    def _make_root(self, root_repo, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir(exist_ok=True)
        return root_repo.get_or_create(str(lib))

    def test_upsert_creates(self, sample_repo, root_repo, tmp_path):
        root = self._make_root(root_repo, tmp_path)
        row = sample_repo.upsert(
            library_root_id=root["id"],
            rel_path="loops/kick.wav",
            filename="kick.wav",
            ext=".wav",
            size_bytes=1024,
            mtime_epoch=1700000000,
        )
        assert row["id"] is not None
        assert row["filename"] == "kick.wav"
        assert row["ext"] == ".wav"
        assert row["size_bytes"] == 1024

    def test_upsert_updates_metadata(self, sample_repo, root_repo, tmp_path):
        """Second upsert with same (root, rel_path) updates metadata."""
        root = self._make_root(root_repo, tmp_path)
        row1 = sample_repo.upsert(
            library_root_id=root["id"],
            rel_path="loops/kick.wav",
            filename="kick.wav",
            ext=".wav",
            size_bytes=1024,
            mtime_epoch=1700000000,
        )
        row2 = sample_repo.upsert(
            library_root_id=root["id"],
            rel_path="loops/kick.wav",
            filename="kick.wav",
            ext=".wav",
            size_bytes=2048,
            mtime_epoch=1700001000,
        )
        assert row1["id"] == row2["id"]  # same row
        assert row2["size_bytes"] == 2048
        assert row2["mtime_epoch"] == 1700001000

    def test_upsert_case_insensitive_path(self, sample_repo, root_repo, tmp_path):
        """Different casing of rel_path maps to same rel_path_norm -> same row."""
        root = self._make_root(root_repo, tmp_path)
        row1 = sample_repo.upsert(
            library_root_id=root["id"],
            rel_path="Loops/Kick.WAV",
            filename="Kick.WAV",
            ext=".WAV",
        )
        row2 = sample_repo.upsert(
            library_root_id=root["id"],
            rel_path="loops/kick.wav",
            filename="kick.wav",
            ext=".wav",
        )
        assert row1["id"] == row2["id"]

    def test_different_roots_separate_samples(self, sample_repo, root_repo, tmp_path):
        lib1 = tmp_path / "lib1"
        lib2 = tmp_path / "lib2"
        lib1.mkdir()
        lib2.mkdir()
        r1 = root_repo.get_or_create(str(lib1))
        r2 = root_repo.get_or_create(str(lib2))
        s1 = sample_repo.upsert(r1["id"], "kick.wav", "kick.wav")
        s2 = sample_repo.upsert(r2["id"], "kick.wav", "kick.wav")
        assert s1["id"] != s2["id"]

    def test_get_by_id(self, sample_repo, root_repo, tmp_path):
        root = self._make_root(root_repo, tmp_path)
        created = sample_repo.upsert(root["id"], "x.wav", "x.wav")
        fetched = sample_repo.get_by_id(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_by_id_not_found(self, sample_repo):
        assert sample_repo.get_by_id(99999) is None

    def test_list_by_root(self, sample_repo, root_repo, tmp_path):
        root = self._make_root(root_repo, tmp_path)
        sample_repo.upsert(root["id"], "a.wav", "a.wav")
        sample_repo.upsert(root["id"], "b.wav", "b.wav")
        samples = sample_repo.list_by_root(root["id"])
        assert len(samples) == 2

    def test_optional_fields_nullable(self, sample_repo, root_repo, tmp_path):
        root = self._make_root(root_repo, tmp_path)
        row = sample_repo.upsert(root["id"], "x.wav", "x.wav")
        assert row["ext"] is None
        assert row["size_bytes"] is None
        assert row["mtime_epoch"] is None


# ============================= TagRepo ======================================

class TestTagRepo:
    def test_create(self, tag_repo):
        tag = tag_repo.create("Kick Drum")
        assert tag["id"] is not None
        assert tag["name_display"] == "Kick Drum"
        assert tag["name_norm"] == "kick drum"
        assert tag["is_hidden"] == 0

    def test_get_by_name_case_insensitive(self, tag_repo):
        tag_repo.create("Kick Drum")
        found = tag_repo.get_by_name("KICK DRUM")
        assert found is not None
        assert found["name_norm"] == "kick drum"

    def test_get_by_name_not_found(self, tag_repo):
        assert tag_repo.get_by_name("nonexistent") is None

    def test_name_norm_unique_constraint(self, tag_repo):
        tag_repo.create("Kick")
        with pytest.raises(sqlite3.IntegrityError):
            tag_repo.create("kick")  # same name_norm

    def test_get_or_create_new(self, tag_repo):
        tag = tag_repo.get_or_create("New Tag")
        assert tag["name_norm"] == "new tag"

    def test_get_or_create_existing(self, tag_repo):
        t1 = tag_repo.get_or_create("Bass")
        t2 = tag_repo.get_or_create("BASS")
        assert t1["id"] == t2["id"]

    def test_set_shorthand(self, tag_repo):
        tag = tag_repo.create("Hi-Hat")
        tag_repo.set_shorthand(tag["id"], "hh")
        updated = tag_repo.get_by_id(tag["id"])
        assert updated["shorthand_display"] == "hh"
        assert updated["shorthand_norm"] == "hh"

    def test_shorthand_uniqueness(self, tag_repo):
        t1 = tag_repo.create("Kick")
        t2 = tag_repo.create("Snare")
        tag_repo.set_shorthand(t1["id"], "K")
        with pytest.raises(sqlite3.IntegrityError):
            tag_repo.set_shorthand(t2["id"], "k")  # same shorthand_norm

    def test_clear_shorthand(self, tag_repo):
        tag = tag_repo.create("Hat")
        tag_repo.set_shorthand(tag["id"], "HH")
        tag_repo.clear_shorthand(tag["id"])
        updated = tag_repo.get_by_id(tag["id"])
        assert updated["shorthand_display"] is None
        assert updated["shorthand_norm"] is None

    def test_hide_and_unhide(self, tag_repo):
        tag = tag_repo.create("FX")
        assert tag["is_hidden"] == 0

        tag_repo.hide(tag["id"])
        hidden = tag_repo.get_by_id(tag["id"])
        assert hidden["is_hidden"] == 1

        tag_repo.unhide(tag["id"])
        restored = tag_repo.get_by_id(tag["id"])
        assert restored["is_hidden"] == 0

    def test_list_excludes_hidden_by_default(self, tag_repo):
        tag_repo.create("Visible")
        hidden = tag_repo.create("Hidden")
        tag_repo.hide(hidden["id"])

        visible_list = tag_repo.list()
        assert len(visible_list) == 1
        assert visible_list[0]["name_norm"] == "visible"

    def test_list_includes_hidden_when_requested(self, tag_repo):
        tag_repo.create("Visible")
        hidden = tag_repo.create("Hidden")
        tag_repo.hide(hidden["id"])

        all_list = tag_repo.list(include_hidden=True)
        assert len(all_list) == 2

    def test_create_with_is_category(self, tag_repo):
        tag = tag_repo.create("Drums", is_category=True)
        assert tag["is_category"] == 1


# ============================= TagAliasRepo =================================

class TestTagAliasRepo:
    def test_add_alias(self, alias_repo, tag_repo):
        tag = tag_repo.create("Hi-Hat")
        alias = alias_repo.add(tag["id"], "HH")
        assert alias["alias_norm"] == "hh"
        assert alias["tag_id"] == tag["id"]

    def test_alias_norm_unique_globally(self, alias_repo, tag_repo):
        t1 = tag_repo.create("Tag A")
        t2 = tag_repo.create("Tag B")
        alias_repo.add(t1["id"], "shared")
        with pytest.raises(sqlite3.IntegrityError):
            alias_repo.add(t2["id"], "SHARED")  # same alias_norm

    def test_remove_by_alias(self, alias_repo, tag_repo):
        tag = tag_repo.create("Bass")
        alias_repo.add(tag["id"], "low")
        aliases = alias_repo.list_for_tag(tag["id"])
        assert len(aliases) == 1
        alias_repo.remove_by_alias("LOW")
        aliases = alias_repo.list_for_tag(tag["id"])
        assert len(aliases) == 0

    def test_remove_by_id(self, alias_repo, tag_repo):
        tag = tag_repo.create("Bass")
        alias = alias_repo.add(tag["id"], "low")
        alias_repo.remove_by_id(alias["id"])
        aliases = alias_repo.list_for_tag(tag["id"])
        assert len(aliases) == 0

    def test_list_for_tag(self, alias_repo, tag_repo):
        tag = tag_repo.create("Drums")
        alias_repo.add(tag["id"], "drm")
        alias_repo.add(tag["id"], "perc")
        aliases = alias_repo.list_for_tag(tag["id"])
        assert len(aliases) == 2

    def test_resolve_by_name(self, alias_repo, tag_repo):
        tag = tag_repo.create("Kick Drum")
        resolved = alias_repo.resolve("KICK DRUM")
        assert resolved == tag["id"]

    def test_resolve_by_shorthand(self, alias_repo, tag_repo):
        tag = tag_repo.create("Hi-Hat")
        tag_repo.set_shorthand(tag["id"], "HH")
        resolved = alias_repo.resolve("hh")
        assert resolved == tag["id"]

    def test_resolve_by_alias(self, alias_repo, tag_repo):
        tag = tag_repo.create("Snare")
        alias_repo.add(tag["id"], "snr")
        resolved = alias_repo.resolve("SNR")
        assert resolved == tag["id"]

    def test_resolve_not_found(self, alias_repo):
        assert alias_repo.resolve("nonexistent") is None

    def test_resolve_excludes_hidden_by_default(self, alias_repo, tag_repo):
        tag = tag_repo.create("Secret")
        tag_repo.hide(tag["id"])
        assert alias_repo.resolve("Secret") is None

    def test_resolve_includes_hidden_when_requested(self, alias_repo, tag_repo):
        tag = tag_repo.create("Secret")
        tag_repo.hide(tag["id"])
        resolved = alias_repo.resolve("Secret", include_hidden=True)
        assert resolved == tag["id"]

    def test_resolve_hidden_via_alias(self, alias_repo, tag_repo):
        tag = tag_repo.create("Secret")
        alias_repo.add(tag["id"], "sec")
        tag_repo.hide(tag["id"])
        # Default: hidden tag's alias should not resolve
        assert alias_repo.resolve("sec") is None
        # With include_hidden: should resolve
        assert alias_repo.resolve("sec", include_hidden=True) == tag["id"]

    def test_resolve_hidden_via_shorthand(self, alias_repo, tag_repo):
        tag = tag_repo.create("Secret")
        tag_repo.set_shorthand(tag["id"], "sc")
        tag_repo.hide(tag["id"])
        assert alias_repo.resolve("sc") is None
        assert alias_repo.resolve("sc", include_hidden=True) == tag["id"]


# ============================= SampleTagRepo ================================

class TestSampleTagRepo:
    def _make_sample(self, sample_repo, root_repo, tmp_path, name="kick.wav"):
        lib = tmp_path / "lib"
        lib.mkdir(exist_ok=True)
        root = root_repo.get_or_create(str(lib))
        return sample_repo.upsert(root["id"], name, name)

    def test_attach(self, sample_tag_repo, sample_repo, root_repo, tag_repo, tmp_path):
        sample = self._make_sample(sample_repo, root_repo, tmp_path)
        tag = tag_repo.create("Drums")
        sample_tag_repo.attach(sample["id"], tag["id"])
        tags = sample_tag_repo.list_tags_for_sample(sample["id"])
        assert len(tags) == 1
        assert tags[0]["id"] == tag["id"]

    def test_attach_idempotent(self, sample_tag_repo, sample_repo, root_repo, tag_repo, tmp_path):
        sample = self._make_sample(sample_repo, root_repo, tmp_path)
        tag = tag_repo.create("Drums")
        sample_tag_repo.attach(sample["id"], tag["id"])
        sample_tag_repo.attach(sample["id"], tag["id"])  # no error
        tags = sample_tag_repo.list_tags_for_sample(sample["id"])
        assert len(tags) == 1

    def test_detach(self, sample_tag_repo, sample_repo, root_repo, tag_repo, tmp_path):
        sample = self._make_sample(sample_repo, root_repo, tmp_path)
        tag = tag_repo.create("Drums")
        sample_tag_repo.attach(sample["id"], tag["id"])
        sample_tag_repo.detach(sample["id"], tag["id"])
        tags = sample_tag_repo.list_tags_for_sample(sample["id"])
        assert len(tags) == 0

    def test_detach_nonexistent_is_noop(self, sample_tag_repo, sample_repo, root_repo, tag_repo, tmp_path):
        sample = self._make_sample(sample_repo, root_repo, tmp_path)
        tag = tag_repo.create("Drums")
        # Detach without attach — should not raise
        sample_tag_repo.detach(sample["id"], tag["id"])

    def test_list_tags_for_sample(self, sample_tag_repo, sample_repo, root_repo, tag_repo, tmp_path):
        sample = self._make_sample(sample_repo, root_repo, tmp_path)
        t1 = tag_repo.create("Drums")
        t2 = tag_repo.create("Kick")
        sample_tag_repo.attach(sample["id"], t1["id"])
        sample_tag_repo.attach(sample["id"], t2["id"])
        tags = sample_tag_repo.list_tags_for_sample(sample["id"])
        assert len(tags) == 2
        tag_names = {t["name_norm"] for t in tags}
        assert tag_names == {"drums", "kick"}

    def test_list_samples_for_tag(self, sample_tag_repo, sample_repo, root_repo, tag_repo, tmp_path):
        s1 = self._make_sample(sample_repo, root_repo, tmp_path, "kick.wav")
        s2 = self._make_sample(sample_repo, root_repo, tmp_path, "snare.wav")
        tag = tag_repo.create("Drums")
        sample_tag_repo.attach(s1["id"], tag["id"])
        sample_tag_repo.attach(s2["id"], tag["id"])
        samples = sample_tag_repo.list_samples_for_tag(tag["id"])
        assert len(samples) == 2


# ============================= TagParentRepo ================================

class TestTagParentRepo:
    def test_add_parent(self, parent_repo, tag_repo):
        parent = tag_repo.create("Drums")
        child = tag_repo.create("Kick")
        parent_repo.add_parent(child["id"], parent["id"])
        parents = parent_repo.list_parents(child["id"])
        assert len(parents) == 1
        assert parents[0]["id"] == parent["id"]

    def test_reject_self_edge(self, parent_repo, tag_repo):
        tag = tag_repo.create("Drums")
        with pytest.raises(ValueError, match="Self-edge"):
            parent_repo.add_parent(tag["id"], tag["id"])

    def test_reject_direct_cycle(self, parent_repo, tag_repo):
        """A -> B, then B -> A should be rejected (B is already descendant of A)."""
        a = tag_repo.create("A")
        b = tag_repo.create("B")
        parent_repo.add_parent(b["id"], a["id"])  # B is child of A
        with pytest.raises(ValueError, match="Cycle"):
            parent_repo.add_parent(a["id"], b["id"])  # A child of B would cycle

    def test_reject_indirect_cycle(self, parent_repo, tag_repo):
        """A -> B -> C, then C -> A should be rejected."""
        a = tag_repo.create("A")
        b = tag_repo.create("B")
        c = tag_repo.create("C")
        parent_repo.add_parent(b["id"], a["id"])  # B child of A
        parent_repo.add_parent(c["id"], b["id"])  # C child of B
        with pytest.raises(ValueError, match="Cycle"):
            parent_repo.add_parent(a["id"], c["id"])  # A child of C would cycle

    def test_remove_edge(self, parent_repo, tag_repo):
        p = tag_repo.create("Parent")
        c = tag_repo.create("Child")
        parent_repo.add_parent(c["id"], p["id"])
        parent_repo.remove(c["id"], p["id"])
        parents = parent_repo.list_parents(c["id"])
        assert len(parents) == 0

    def test_list_parents(self, parent_repo, tag_repo):
        root = tag_repo.create("Root")
        alt = tag_repo.create("Alt")
        child = tag_repo.create("Child")
        parent_repo.add_parent(child["id"], root["id"])
        parent_repo.add_parent(child["id"], alt["id"])
        parents = parent_repo.list_parents(child["id"])
        assert len(parents) == 2

    def test_list_children(self, parent_repo, tag_repo):
        parent = tag_repo.create("Drums")
        c1 = tag_repo.create("Kick")
        c2 = tag_repo.create("Snare")
        parent_repo.add_parent(c1["id"], parent["id"])
        parent_repo.add_parent(c2["id"], parent["id"])
        children = parent_repo.list_children(parent["id"])
        assert len(children) == 2
        child_names = {c["name_norm"] for c in children}
        assert child_names == {"kick", "snare"}

    def test_dag_allows_diamond(self, parent_repo, tag_repo):
        """Diamond shape is valid (not a cycle): A->B, A->C, B->D, C->D."""
        a = tag_repo.create("A")
        b = tag_repo.create("B")
        c = tag_repo.create("C")
        d = tag_repo.create("D")
        parent_repo.add_parent(b["id"], a["id"])
        parent_repo.add_parent(c["id"], a["id"])
        parent_repo.add_parent(d["id"], b["id"])
        parent_repo.add_parent(d["id"], c["id"])
        # Should not raise — diamond is valid DAG
        parents_of_d = parent_repo.list_parents(d["id"])
        assert len(parents_of_d) == 2

    def test_cycle_check_rollback_leaves_no_edge(self, parent_repo, tag_repo, db):
        """After a rejected cycle, the edge should not exist in DB."""
        a = tag_repo.create("A")
        b = tag_repo.create("B")
        parent_repo.add_parent(b["id"], a["id"])
        with pytest.raises(ValueError):
            parent_repo.add_parent(a["id"], b["id"])
        # Verify no edge was inserted
        row = db.fetchone(
            "SELECT 1 FROM tag_parent WHERE child_tag_id = ? AND parent_tag_id = ?",
            (a["id"], b["id"]),
        )
        assert row is None
