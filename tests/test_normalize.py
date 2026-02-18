"""Tests for sample_manager.normalize — pure normalization functions."""

import pytest
from pathlib import Path

from sample_manager.normalize import norm_text, norm_rel_path, norm_abs_path


# ---------- norm_text ----------

class TestNormText:
    def test_strip_and_lower(self):
        assert norm_text("  Kick Drum ") == "kick drum"

    def test_collapse_internal_whitespace(self):
        assert norm_text("  Kick   Drum  ") == "kick drum"

    def test_tabs_and_newlines_collapsed(self):
        assert norm_text("kick\t\tdrum\n") == "kick drum"

    def test_already_normalized(self):
        assert norm_text("kick") == "kick"

    def test_empty_string(self):
        assert norm_text("") == ""

    def test_only_whitespace(self):
        assert norm_text("   ") == ""

    def test_preserves_hyphens_and_special(self):
        assert norm_text("HI-HAT") == "hi-hat"

    def test_unicode(self):
        assert norm_text("  Böse  Kick  ") == "böse kick"


# ---------- norm_rel_path ----------

class TestNormRelPath:
    def test_simple_relative(self):
        assert norm_rel_path("loops/kick.wav") == "loops/kick.wav"

    def test_backslash_to_forward(self):
        # On all platforms, Path("a\\b") should normalize
        assert norm_rel_path(Path("loops") / "kick.wav") == "loops/kick.wav"

    def test_lowercase(self):
        assert norm_rel_path("Loops/Kick.WAV") == "loops/kick.wav"

    def test_no_trailing_separator(self):
        result = norm_rel_path("loops/sub/")
        assert not result.endswith("/")

    def test_single_file(self):
        assert norm_rel_path("kick.wav") == "kick.wav"

    def test_dotdot_segments(self):
        # Path normalizes .. on construction
        result = norm_rel_path("loops/../drums/kick.wav")
        assert result == "drums/kick.wav"

    def test_absolute_path_rejected(self):
        with pytest.raises(ValueError, match="absolute"):
            norm_rel_path("/absolute/path/file.wav")

    def test_path_object_input(self):
        p = Path("some") / "nested" / "path.wav"
        assert norm_rel_path(p) == "some/nested/path.wav"


# ---------- norm_abs_path ----------

class TestNormAbsPath:
    def test_resolves_to_absolute(self, tmp_path):
        p = tmp_path / "mylib"
        p.mkdir()
        result = norm_abs_path(str(p))
        assert "/" in result  # POSIX separators
        assert result == str(p.resolve()).replace("\\", "/").lower()

    def test_lowercase(self, tmp_path):
        result = norm_abs_path(str(tmp_path))
        assert result == result.lower()

    def test_expands_tilde(self, monkeypatch, tmp_path):
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        result = norm_abs_path("~/mylib")
        # Should contain the fake home path, lowercased
        assert str(fake_home).lower().replace("\\", "/") in result

    def test_forward_slashes(self, tmp_path):
        result = norm_abs_path(str(tmp_path))
        assert "\\" not in result

    def test_string_and_path_input(self, tmp_path):
        s_result = norm_abs_path(str(tmp_path))
        p_result = norm_abs_path(tmp_path)
        assert s_result == p_result
