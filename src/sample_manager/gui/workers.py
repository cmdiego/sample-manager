"""Background workers for offloading blocking audio work off the Qt event loop.

Waveform decoding can take tens of milliseconds and must never run on the GUI
thread. ``WaveformWorker`` wraps a :class:`WaveformService` call in a
``QRunnable`` and reports the result — or the failure — back through a
``WorkerSignals`` bridge (queued to the GUI thread) so widgets are only ever
mutated from the main thread.

Every worker carries a monotonically increasing ``generation`` id. The widget
that posted it uses that id to discard results that a newer request has
superseded (e.g. the user moved focus again before the decode finished).

``WaveformService`` is imported only under ``TYPE_CHECKING`` so that importing
this module never pulls in numpy / the audio backends.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..audio.waveform import WaveformService


class WorkerSignals(QObject):
    """Signal bridge for a :class:`WaveformWorker`.

    ``QRunnable`` cannot itself declare signals, so each worker owns one of
    these. Emissions cross from the pool thread to the GUI thread as queued
    connections, so slots run on the main thread.
    """

    waveform_ready = Signal(int, object)  # generation, WaveformData
    error = Signal(int, str)  # generation, message


class WaveformWorker(QRunnable):
    """Decode + envelope a file's waveform on a thread-pool thread.

    On success emits ``waveform_ready(generation, WaveformData)``; on any failure
    emits ``error(generation, message)``. Never touches a widget directly.
    """

    def __init__(
        self,
        generation: int,
        path: Path,
        bins: int,
        service: "WaveformService",
    ) -> None:
        super().__init__()
        self._generation = generation
        self._path = Path(path)
        self._bins = max(1, int(bins))
        self._service = service
        self.signals = WorkerSignals()

    @property
    def generation(self) -> int:
        return self._generation

    @Slot()
    def run(self) -> None:  # noqa: D401 - QRunnable entry point
        try:
            data = self._service.get_waveform(self._path, self._bins)
        except Exception as exc:  # noqa: BLE001 - normalize decode failures
            message = str(exc) or exc.__class__.__name__
            self.signals.error.emit(self._generation, message)
        else:
            self.signals.waveform_ready.emit(self._generation, data)


class Worker(QRunnable):
    """Generic ``fn(*args, **kwargs)`` runner kept for ad-hoc background work.

    Emits ``result`` with the return value on success, ``error`` with the raised
    exception on failure, and always ``finished`` at the end.
    """

    class Signals(QObject):
        finished = Signal()
        result = Signal(object)
        error = Signal(object)

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = Worker.Signals()

    @Slot()
    def run(self) -> None:  # noqa: D401 - QRunnable entry point
        try:
            value = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # pragma: no cover - defensive scaffold
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(value)
        finally:
            self.signals.finished.emit()
