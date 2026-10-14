"""Contracts for indexed, root-scoped sample search."""

from sample_manager.repos.sample_repo import SampleRepo


def _root(db, path: str) -> int:
    """Insert one library root for a search fixture."""
    db.execute("INSERT INTO library_root (path, path_norm) VALUES (?, ?)", (path, path.lower()))
    return db.fetchval("SELECT last_insert_rowid()")


def _sample(db, root_id: int, rel_path: str) -> int:
    """Insert an indexed sample with its normalized relative path."""
    db.execute(
        "INSERT INTO sample (library_root_id, rel_path, rel_path_norm, filename) "
        "VALUES (?, ?, ?, ?)",
        (root_id, rel_path, rel_path.lower(), rel_path.rsplit("/", 1)[-1]),
    )
    return db.fetchval("SELECT last_insert_rowid()")


def test_search_finds_case_insensitive_substring_in_wave_filename(db):
    """A middle-of-name Drum query finds the exact reported file shape."""
    root_id = _root(db, "/samples")
    sample_id = _sample(db, root_id, "packs/FL_FDS_09_Drum_Loop_Full_98.wave")

    hits = SampleRepo(db).search_by_text(root_id, "DrUm")

    assert [hit["id"] for hit in hits] == [sample_id]


def test_search_matches_all_terms_across_path_name_and_tags(db):
    """Terms may combine a folder fragment, a filename, and a tag alias."""
    root_id = _root(db, "/samples")
    sample_id = _sample(db, root_id, "Funky_Disco/FL_FDS_09_Drum_Loop_Full_98.wave")
    db.execute("INSERT INTO tag (name_display, name_norm) VALUES ('Percussion', 'percussion')")
    tag_id = db.fetchval("SELECT last_insert_rowid()")
    db.execute("INSERT INTO sample_tag (sample_id, tag_id) VALUES (?, ?)", (sample_id, tag_id))
    db.execute(
        "INSERT INTO tag_alias (tag_id, alias_display, alias_norm) VALUES (?, 'Beat', 'beat')",
        (tag_id,),
    )

    hits = SampleRepo(db).search_by_text(root_id, "funky drum beat")

    assert [hit["id"] for hit in hits] == [sample_id]


def test_search_stays_in_root_and_treats_percent_literally(db):
    """A query cannot leak another root or treat '%' as a wildcard."""
    root_a = _root(db, "/a")
    root_b = _root(db, "/b")
    wanted = _sample(db, root_a, "100%_drum.wav")
    _sample(db, root_a, "plain_drum.wav")
    _sample(db, root_b, "100%_drum.wav")

    hits = SampleRepo(db).search_by_text(root_a, "%")

    assert [hit["id"] for hit in hits] == [wanted]
