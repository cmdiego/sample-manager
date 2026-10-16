"""Mixer rendering, fades, and completion events without a device."""

import pytest

np = pytest.importorskip("numpy")

from sample_manager.audio.mixer import Mixer, Voice


def _ones(frames: int, channels: int = 1):
    return np.ones((frames, channels), dtype="float32")


def _render(mixer: Mixer, frames: int, channels: int = 1):
    out = np.empty((frames, channels), dtype="float32")
    mixer.render(out)
    return out


def test_voice_from_start_plays_at_full_gain_and_completes():
    mixer = Mixer(1000, 1, fade_seconds=0.004)
    pcm = np.array([[0.25], [-0.5], [0.75]], dtype="float32")
    mixer.play(Voice(token=1, pcm=pcm), fade_in=False)

    out = _render(mixer, 4)

    assert out[:, 0].tolist() == [0.25, -0.5, 0.75, 0.0]
    assert list(mixer.events) == [("complete", 1)]
    assert not mixer.active


def test_fade_in_ramps_to_unity():
    mixer = Mixer(1000, 1, fade_seconds=0.004)  # 4-frame fade
    mixer.play(Voice(token=1, pcm=_ones(8)), fade_in=True)

    out = _render(mixer, 6)

    assert out[:, 0].tolist() == pytest.approx([0.25, 0.5, 0.75, 1.0, 1.0, 1.0])


def test_new_voice_crossfades_and_superseded_voice_never_completes():
    mixer = Mixer(1000, 1, fade_seconds=0.004)
    first = Voice(token=1, pcm=_ones(100))
    mixer.play(first, fade_in=False)
    _render(mixer, 10)

    mixer.play(Voice(token=2, pcm=_ones(100) * 0.5), fade_in=False)
    out = _render(mixer, 6)

    # Old voice fades 0.75, 0.5, 0.25, 0 while the new one plays at 0.5.
    assert out[:, 0].tolist() == pytest.approx([1.25, 1.0, 0.75, 0.5, 0.5, 0.5])
    assert first.stopping
    assert ("complete", 1) not in mixer.events


def test_stop_fades_out_and_removes_voice_without_completion():
    mixer = Mixer(1000, 2, fade_seconds=0.002)
    voice = Voice(token=7, pcm=_ones(50, 2))
    mixer.play(voice, fade_in=False)
    _render(mixer, 5, 2)

    mixer.stop(voice)
    out = _render(mixer, 4, 2)

    assert out[:, 0].tolist() == pytest.approx([0.5, 0.0, 0.0, 0.0])
    assert not mixer.active
    assert not mixer.events


def test_render_records_first_audible_time_for_latency_stats():
    mixer = Mixer(1000, 1)
    voice = Voice(token=1, pcm=_ones(10))
    mixer.play(voice, fade_in=False)
    assert voice.first_render_at is None
    _render(mixer, 4)
    assert voice.first_render_at is not None
