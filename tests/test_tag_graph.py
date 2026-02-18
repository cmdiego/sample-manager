"""Tests for sample_manager.tag_graph — recursive CTE queries on tag DAG."""

import pytest

from sample_manager.repos.tag_repo import TagRepo
from sample_manager.repos.tag_parent_repo import TagParentRepo
from sample_manager.tag_graph import TagGraphService


@pytest.fixture
def tag_repo(db):
    return TagRepo(db)


@pytest.fixture
def parent_repo(db):
    return TagParentRepo(db)


@pytest.fixture
def graph(db):
    return TagGraphService(db)


def _make_tag(tag_repo, name):
    """Helper: create a tag and return its ID."""
    return tag_repo.create(name)["id"]


class TestDescendantsIncludingSelf:
    def test_single_node_returns_itself(self, graph, tag_repo):
        tid = _make_tag(tag_repo, "Drums")
        result = graph.descendants_including_self(tid)
        assert result == {tid}

    def test_linear_chain(self, graph, tag_repo, parent_repo):
        """A -> B -> C (A is parent of B, B is parent of C).
        Descendants of A should be {A, B, C}.
        """
        a = _make_tag(tag_repo, "Percussion")
        b = _make_tag(tag_repo, "Drums")
        c = _make_tag(tag_repo, "Kick")

        parent_repo.add_parent(child_tag_id=b, parent_tag_id=a)
        parent_repo.add_parent(child_tag_id=c, parent_tag_id=b)

        assert graph.descendants_including_self(a) == {a, b, c}
        assert graph.descendants_including_self(b) == {b, c}
        assert graph.descendants_including_self(c) == {c}

    def test_diamond_dag(self, graph, tag_repo, parent_repo):
        """Diamond: A -> B, A -> C, B -> D, C -> D.
        Descendants of A = {A, B, C, D}.
        """
        a = _make_tag(tag_repo, "Root")
        b = _make_tag(tag_repo, "Left")
        c = _make_tag(tag_repo, "Right")
        d = _make_tag(tag_repo, "Leaf")

        parent_repo.add_parent(child_tag_id=b, parent_tag_id=a)
        parent_repo.add_parent(child_tag_id=c, parent_tag_id=a)
        parent_repo.add_parent(child_tag_id=d, parent_tag_id=b)
        parent_repo.add_parent(child_tag_id=d, parent_tag_id=c)

        assert graph.descendants_including_self(a) == {a, b, c, d}
        assert graph.descendants_including_self(b) == {b, d}
        assert graph.descendants_including_self(c) == {c, d}
        assert graph.descendants_including_self(d) == {d}

    def test_wide_tree(self, graph, tag_repo, parent_repo):
        """Parent with 3 direct children, no grandchildren."""
        root = _make_tag(tag_repo, "Drums")
        c1 = _make_tag(tag_repo, "Kick")
        c2 = _make_tag(tag_repo, "Snare")
        c3 = _make_tag(tag_repo, "Hat")

        parent_repo.add_parent(child_tag_id=c1, parent_tag_id=root)
        parent_repo.add_parent(child_tag_id=c2, parent_tag_id=root)
        parent_repo.add_parent(child_tag_id=c3, parent_tag_id=root)

        assert graph.descendants_including_self(root) == {root, c1, c2, c3}

    def test_nonexistent_tag_returns_singleton(self, graph):
        """Querying a tag ID with no edges returns just that ID."""
        result = graph.descendants_including_self(99999)
        assert result == {99999}


class TestExpandForSearch:
    def test_empty_input_returns_empty(self, graph):
        assert graph.expand_for_search([]) == set()
        assert graph.expand_for_search(set()) == set()

    def test_single_tag_no_children(self, graph, tag_repo):
        tid = _make_tag(tag_repo, "Bass")
        result = graph.expand_for_search([tid])
        assert result == {tid}

    def test_unions_multiple_roots(self, graph, tag_repo, parent_repo):
        """Two independent hierarchies: expanding both roots unions all descendants."""
        # Hierarchy 1: Drums -> Kick
        drums = _make_tag(tag_repo, "Drums")
        kick = _make_tag(tag_repo, "Kick")
        parent_repo.add_parent(child_tag_id=kick, parent_tag_id=drums)

        # Hierarchy 2: Synth -> Pad
        synth = _make_tag(tag_repo, "Synth")
        pad = _make_tag(tag_repo, "Pad")
        parent_repo.add_parent(child_tag_id=pad, parent_tag_id=synth)

        result = graph.expand_for_search([drums, synth])
        assert result == {drums, kick, synth, pad}

    def test_overlapping_hierarchies(self, graph, tag_repo, parent_repo):
        """When two input tags share descendants, result is deduplicated."""
        a = _make_tag(tag_repo, "A")
        b = _make_tag(tag_repo, "B")
        c = _make_tag(tag_repo, "C")

        parent_repo.add_parent(child_tag_id=b, parent_tag_id=a)
        parent_repo.add_parent(child_tag_id=c, parent_tag_id=b)

        # expand_for_search([a, b]) -> {a, b, c} (b and c are descendants of a, c is desc of b)
        result = graph.expand_for_search([a, b])
        assert result == {a, b, c}

    def test_accepts_set_input(self, graph, tag_repo):
        tid = _make_tag(tag_repo, "FX")
        result = graph.expand_for_search({tid})
        assert result == {tid}
