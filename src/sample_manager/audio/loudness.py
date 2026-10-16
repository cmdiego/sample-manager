"""ITU-R BS.1770 loudness (LUFS) without an IIR filter dependency.

BS.1770 measures the mean square of a K-weighted signal (a high shelf plus a
high-pass "RLB" stage) in 400 ms blocks with 75 % overlap, gated at −70 LUFS
absolute and −10 LU relative. A per-sample IIR loop is too slow in Python and
SciPy is not a dependency, so the K-weighting is applied as an FFT
overlap-add convolution with the cascade's impulse response. That response
decays below −200 dB within 0.25 s, so truncating it there is exact for
loudness purposes. The filtered signal is never stored: each overlap-add
block is reduced straight to 100 ms step energies.

Momentary (400 ms) and short-term (3 s) blocks are means of 4 and 30 steps.
Files shorter than one 400 ms block report the ungated K-weighted loudness of
the whole file, which is what one-shot level matching needs.

All channels are weighted 1.0, which is exact for mono and stereo. Surround
channel weights are not applied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from .backends import require

_STEP_SECONDS = 0.1
_MOMENTARY_STEPS = 4
_SHORT_TERM_STEPS = 30
_ABSOLUTE_GATE_LUFS = -70.0
_RELATIVE_GATE_LU = -10.0
_OFFSET = -0.691
_IMPULSE_SECONDS = 0.25
_MIN_FFT = 1 << 16

# Brecht De Man's bilinear derivation of the BS.1770 filters; at 48 kHz it
# reproduces the coefficients printed in the standard.
_SHELF_HZ = 1681.974450955533
_SHELF_GAIN_DB = 3.999843853973347
_SHELF_Q = 0.7071752369554196
_SHELF_BAND_EXPONENT = 0.4996667741545416
_HIGHPASS_HZ = 38.13547087602444
_HIGHPASS_Q = 0.5003270373238773


@dataclass(frozen=True)
class Loudness:
    """Integrated loudness and the loudest short-term (3 s) window, in LUFS.

    Either value is ``None`` when the signal is silent (below the gate).
    """

    integrated_lufs: float | None
    short_term_max_lufs: float | None


def measure_loudness(samples, sample_rate: int) -> Loudness:
    """Measure *samples* (``(frames, channels)`` or mono) at *sample_rate*."""
    np = require("numpy")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    pcm = np.asarray(samples, dtype="float32")
    if pcm.ndim == 1:
        pcm = pcm[:, None]
    frames = int(pcm.shape[0])
    if frames == 0:
        return Loudness(None, None)

    step = max(1, round(sample_rate * _STEP_SECONDS))
    steps = frames // step
    if steps < _MOMENTARY_STEPS:
        total = _filtered_energy_per_step(np, pcm, sample_rate, frames).sum()
        level = _lufs(float(total) / frames)
        return Loudness(level, level)

    step_energy = _filtered_energy_per_step(np, pcm, sample_rate, step)[:steps] / step
    momentary = _windowed_means(np, step_energy, _MOMENTARY_STEPS)
    integrated = _gated_integrated(np, momentary)
    short_term = _windowed_means(np, step_energy, _SHORT_TERM_STEPS)
    return Loudness(integrated, _lufs(float(short_term.max())))


def _filtered_energy_per_step(np, pcm, rate: int, step: int):
    """Sum of squared K-weighted samples (all channels) for each *step* frames.

    Overlap-add: each input block is convolved in the frequency domain; its
    tail carries into the next block, and only finished samples are counted.
    """
    impulse = _impulse_response(rate)
    taps = impulse.shape[0]
    nfft = _MIN_FFT
    while nfft < 4 * taps:
        nfft *= 2
    block = nfft - taps + 1
    kernel = np.fft.rfft(impulse, nfft)[:, None]
    frames, channels = pcm.shape
    sums = np.zeros(frames // step + 1, dtype="float64")
    carry = np.zeros((taps - 1, channels), dtype="float64")
    for start in range(0, frames, block):
        chunk = pcm[start:start + block]
        count = chunk.shape[0]
        filtered = np.fft.irfft(np.fft.rfft(chunk, nfft, axis=0) * kernel, nfft, axis=0)
        filtered[:taps - 1] += carry
        carry = filtered[count:count + taps - 1].copy()
        finished = filtered[:count]
        energy = np.einsum("ij,ij->i", finished, finished)
        positions = (start + np.arange(count)) // step
        sums += np.bincount(positions, weights=energy, minlength=sums.shape[0])[:sums.shape[0]]
    return sums


@lru_cache(maxsize=8)
def _impulse_response(rate: int):
    """K-weighting impulse response, from its frequency response on a fine grid."""
    np = require("numpy")
    taps = max(64, round(rate * _IMPULSE_SECONDS))
    grid = 8 * taps
    omega = 2.0 * math.pi * np.arange(grid // 2 + 1) / grid
    z1 = np.exp(-1j * omega)
    z2 = z1 * z1
    response = np.ones_like(z1)
    for b, a in (_high_shelf(rate), _high_pass(rate)):
        response *= (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)
    # The grid is 8× the kept length, so time aliasing is far below the
    # response's own decay at the truncation point.
    return np.fft.irfft(response, grid)[:taps]


def _high_shelf(rate: int):
    k = math.tan(math.pi * _SHELF_HZ / rate)
    high = 10.0 ** (_SHELF_GAIN_DB / 20.0)
    band = high ** _SHELF_BAND_EXPONENT
    a0 = 1.0 + k / _SHELF_Q + k * k
    b = (
        (high + band * k / _SHELF_Q + k * k) / a0,
        2.0 * (k * k - high) / a0,
        (high - band * k / _SHELF_Q + k * k) / a0,
    )
    a = (1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / _SHELF_Q + k * k) / a0)
    return b, a


def _high_pass(rate: int):
    k = math.tan(math.pi * _HIGHPASS_HZ / rate)
    a0 = 1.0 + k / _HIGHPASS_Q + k * k
    b = (1.0, -2.0, 1.0)
    a = (1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / _HIGHPASS_Q + k * k) / a0)
    return b, a


def _windowed_means(np, values, width: int):
    """Means of every run of *width* consecutive 100 ms steps."""
    if values.shape[0] < width:
        return np.array([values.mean()])
    cumulative = np.concatenate(([0.0], np.cumsum(values, dtype="float64")))
    return (cumulative[width:] - cumulative[:-width]) / width


def _gated_integrated(np, momentary) -> float | None:
    """BS.1770-4 two-stage gating over 400 ms blocks (75 % overlap)."""
    with np.errstate(divide="ignore"):
        levels = _OFFSET + 10.0 * np.log10(momentary)
    kept = momentary[levels > _ABSOLUTE_GATE_LUFS]
    if kept.size == 0:
        return None
    relative_gate = _OFFSET + 10.0 * math.log10(float(kept.mean())) + _RELATIVE_GATE_LU
    final = kept[levels[levels > _ABSOLUTE_GATE_LUFS] > relative_gate]
    return _lufs(float(final.mean())) if final.size else None


def _lufs(energy: float) -> float | None:
    if energy <= 0.0 or not math.isfinite(energy):
        return None
    level = _OFFSET + 10.0 * math.log10(energy)
    return level if level > _ABSOLUTE_GATE_LUFS else None
