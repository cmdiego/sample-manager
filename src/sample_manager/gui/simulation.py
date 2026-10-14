"""JSON simulation runtime for the Qt GUI.

This module is intentionally independent from pytest. Tests, shell sessions,
and future agent-driven workflows can all dispatch the same JSON-compatible
messages against the real Qt main window.
"""

from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, TextIO

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from .models.browser_model import IsDirRole, SampleIdRole


JsonObject = Mapping[str, Any]


_KEYS: dict[str, Qt.Key] = {
    "A": Qt.Key.Key_A,
    "D": Qt.Key.Key_D,
    "H": Qt.Key.Key_H,
    "J": Qt.Key.Key_J,
    "K": Qt.Key.Key_K,
    "L": Qt.Key.Key_L,
    "Down": Qt.Key.Key_Down,
    "Up": Qt.Key.Key_Up,
    "Left": Qt.Key.Key_Left,
    "Right": Qt.Key.Key_Right,
    "Return": Qt.Key.Key_Return,
    "Enter": Qt.Key.Key_Return,
    "Space": Qt.Key.Key_Space,
    "Backspace": Qt.Key.Key_Backspace,
    "Escape": Qt.Key.Key_Escape,
    "/": Qt.Key.Key_Slash,
    "?": Qt.Key.Key_Question,
}

_MODIFIERS: dict[str, Qt.KeyboardModifier] = {
    "Ctrl": Qt.KeyboardModifier.ControlModifier,
    "Control": Qt.KeyboardModifier.ControlModifier,
    "Alt": Qt.KeyboardModifier.AltModifier,
    "Meta": Qt.KeyboardModifier.MetaModifier,
    "Shift": Qt.KeyboardModifier.ShiftModifier,
}


@dataclass
class TemporarySimulationEnvironment:
    """Disposable app environment for simulation shell sessions.

    The environment owns a temporary directory, a real SQLite database, and a
    small sample library so `--simulation-temp` can run without touching the
    user's real config or `~/.sample_manager` state.
    """

    tempdir: tempfile.TemporaryDirectory
    db: Any
    service: Any
    root: Path

    def close(self) -> None:
        """Release the DB connection and delete the temporary directory."""
        self.db.close()
        self.tempdir.cleanup()


def create_temporary_simulation_environment() -> TemporarySimulationEnvironment:
    """Build an isolated sample-manager environment for JSON simulation."""
    from ..db import Db
    from ..migrations import apply_migrations
    from ..services.library_browser import LibraryBrowserService

    tempdir = tempfile.TemporaryDirectory(prefix="sampleman-sim-")
    base = Path(tempdir.name)
    root = base / "library"
    drums = root / "drums"
    loops = root / "loops"
    drums.mkdir(parents=True)
    loops.mkdir(parents=True)

    # Write valid tiny WAV files so future audio/waveform simulation can use
    # the same fixture without replacing dummy bytes.
    files = (
        _write_sine_wav(drums / "kick.wav", freq=60.0),
        _write_sine_wav(drums / "snare.wav", freq=220.0),
        _write_sine_wav(loops / "funk_loop.wav", freq=110.0),
    )

    db = Db(base / "simulation.sqlite3")
    db.connect()
    apply_migrations(db)
    db.execute(
        "INSERT INTO library_root (path, path_norm) VALUES (?, ?)",
        (str(root), str(root).lower()),
    )
    root_id = db.fetchval("SELECT id FROM library_root LIMIT 1")
    for sample_path in files:
        rel = sample_path.relative_to(root)
        db.execute(
            "INSERT INTO sample "
            "(library_root_id, rel_path, rel_path_norm, filename, ext, size_bytes, mtime_epoch) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                root_id,
                rel.as_posix(),
                rel.as_posix().lower(),
                sample_path.name,
                sample_path.suffix.lstrip(".").lower(),
                sample_path.stat().st_size,
                int(sample_path.stat().st_mtime),
            ),
        )
    db.conn.commit()
    return TemporarySimulationEnvironment(
        tempdir=tempdir,
        db=db,
        service=LibraryBrowserService(db),
        root=root,
    )


@dataclass
class GuiSimulationRuntime:
    """A real GUI window plus JSON command/event/assert dispatch."""

    window: Any
    root: Path | None = None

    def run(self, scenario: JsonObject) -> dict[str, Any]:
        """Run every JSON step in *scenario* and return the final snapshot."""
        steps = scenario.get("steps")
        if not isinstance(steps, list):
            raise AssertionError("scenario must contain a list field named 'steps'")
        name = str(scenario.get("name", "<unnamed>"))
        snapshot: dict[str, Any] = self.snapshot()
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, Mapping):
                raise AssertionError(f"{name} step {index}: step must be an object")
            snapshot = self.dispatch(step, context=f"{name} step {index}")
        return snapshot

    def dispatch(self, message: JsonObject, *, context: str = "dispatch") -> dict[str, Any]:
        """Apply one JSON object and return the latest observable state."""
        kind_count = sum(key in message for key in ("event", "command", "assert"))
        if kind_count != 1:
            raise AssertionError(
                f"{context}: message must contain exactly one of event, command, assert"
            )

        if "event" in message:
            self._dispatch_event(message, context)
        elif "command" in message:
            self._dispatch_command(message, context)
        else:
            self._dispatch_assertion(message, context)
        _process_events()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the simulated app state."""
        return {
            "path": self._relative_path(self.window.controller.current_path),
            "visible_rows": self.visible_rows(),
            "focus": self._focused_item(),
            "filter": {
                "has_focus": self.window.browser.filter_has_focus(),
                "text": self.window.browser.filter_text(),
            },
            "stage_count": self.window.controller.selection_summary().count,
        }

    def visible_rows(self) -> list[str]:
        """Return display names for the currently visible browser rows."""
        proxy = self.window.browser.proxy
        return [
            str(proxy.data(proxy.index(row, 0), Qt.ItemDataRole.DisplayRole))
            for row in range(proxy.rowCount())
        ]

    def _dispatch_event(self, message: JsonObject, context: str) -> None:
        event = message["event"]
        if event != "key":
            raise AssertionError(f"{context}: unsupported event {event!r}")
        key, modifiers = _parse_key_sequence(str(message.get("key", "")), context)
        QTest.keyClick(self.window, key, modifiers)

    def _dispatch_command(self, message: JsonObject, context: str) -> None:
        command = message["command"]
        if command == "snapshot":
            return
        if command == "navigate":
            self.window.controller.navigate_to(
                self._resolve_path(message.get("path", "."), context)
            )
            return
        if command == "focus":
            row = _require_int(message, "row", context)
            proxy = self.window.browser.proxy
            if not 0 <= row < proxy.rowCount():
                raise AssertionError(f"{context}: focus row {row} is out of bounds")
            self.window.browser.view.setCurrentIndex(proxy.index(row, 0))
            return
        raise AssertionError(f"{context}: unsupported command {command!r}")

    def _dispatch_assertion(self, message: JsonObject, context: str) -> None:
        assertion = message["assert"]
        if assertion == "path":
            expected = str(message.get("relative", "."))
            actual = self._relative_path(self.window.controller.current_path)
            _assert_equal(actual, expected, f"{context}: path")
            return
        if assertion == "visible_rows":
            names = message.get("names")
            if not isinstance(names, list):
                raise AssertionError(f"{context}: visible_rows.names must be a list")
            _assert_equal(self.visible_rows(), [str(name) for name in names], context)
            return
        if assertion == "focus":
            focus = self._focused_item()
            for field in ("row", "name", "is_dir", "sample_id"):
                if field in message:
                    _assert_equal(focus.get(field), message[field], f"{context}: focus.{field}")
            return
        if assertion == "filter":
            state = self.snapshot()["filter"]
            for field in ("has_focus", "text"):
                if field in message:
                    _assert_equal(state.get(field), message[field], f"{context}: filter.{field}")
            return
        raise AssertionError(f"{context}: unsupported assertion {assertion!r}")

    def _resolve_path(self, value: Any, context: str) -> Path:
        text = str(value)
        if text in ("", ".", "$root"):
            if self.root is None:
                raise AssertionError(f"{context}: no simulation root is available")
            return self.root
        if text.startswith("$root/"):
            if self.root is None:
                raise AssertionError(f"{context}: no simulation root is available")
            return self.root / text.removeprefix("$root/")
        path = Path(text).expanduser()
        if path.is_absolute():
            return path
        if self.root is None:
            raise AssertionError(f"{context}: relative paths require a simulation root")
        return self.root / path

    def _relative_path(self, path: Path | None) -> str:
        if path is None:
            return ""
        if self.root is None:
            return str(path)
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            return str(path)
        return "." if str(rel) == "." else rel.as_posix()

    def _focused_item(self) -> dict[str, Any]:
        index = self.window.browser.current_index()
        if not index.isValid():
            return {"row": -1, "name": None, "is_dir": None, "sample_id": None}
        sample_id = index.data(SampleIdRole)
        return {
            "row": index.row(),
            "name": index.data(Qt.ItemDataRole.DisplayRole),
            "is_dir": bool(index.data(IsDirRole)),
            "sample_id": int(sample_id) if sample_id is not None else None,
        }


def run_simulation_shell(
    window,
    *,
    root: Path | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    """Run a JSON-lines shell around *window*.

    Each input line must be either a JSON dispatch object, a JSON scenario with
    `steps`, or `exit`/`quit`. Every response is a JSON object written on one
    line for easy machine consumption.
    """
    runtime = GuiSimulationRuntime(window=window, root=root or _window_root(window))
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout

    _write_json(output_stream, {"ok": True, "event": "ready", "snapshot": runtime.snapshot()})
    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() in {"exit", "quit"}:
            _write_json(output_stream, {"ok": True, "event": "exit"})
            return 0
        try:
            payload = json.loads(line)
            if not isinstance(payload, Mapping):
                raise AssertionError("input must be a JSON object")
            snapshot = runtime.run(payload) if "steps" in payload else runtime.dispatch(payload)
        except Exception as exc:  # noqa: BLE001 - shell must report and keep running.
            _write_json(output_stream, {"ok": False, "error": str(exc)})
            continue
        _write_json(output_stream, {"ok": True, "snapshot": snapshot})
    return 0


def _window_root(window) -> Path | None:
    root = window.controller.current_root
    return root.path if root is not None else None


def _write_json(stream: TextIO, payload: Mapping[str, Any]) -> None:
    stream.write(json.dumps(payload, sort_keys=True) + "\n")
    stream.flush()


def _parse_key_sequence(
    sequence: str, context: str
) -> tuple[Qt.Key, Qt.KeyboardModifier]:
    if not sequence:
        raise AssertionError(f"{context}: key must be non-empty")
    parts = sequence.split("+")
    key_name = parts[-1]
    try:
        key = _KEYS[key_name]
    except KeyError as exc:
        raise AssertionError(f"{context}: unsupported key {key_name!r}") from exc
    modifiers = Qt.KeyboardModifier.NoModifier
    for modifier_name in parts[:-1]:
        try:
            modifiers |= _MODIFIERS[modifier_name]
        except KeyError as exc:
            raise AssertionError(
                f"{context}: unsupported modifier {modifier_name!r}"
            ) from exc
    return key, modifiers


def _require_int(message: JsonObject, field: str, context: str) -> int:
    value = message.get(field)
    if not isinstance(value, int):
        raise AssertionError(f"{context}: {field} must be an integer")
    return value


def _assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def _process_events() -> None:
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _write_sine_wav(
    path: Path,
    *,
    freq: float,
    sample_rate: int = 44100,
    seconds: float = 0.05,
    amplitude: float = 0.4,
) -> Path:
    """Write a small mono PCM WAV file for the temporary simulation library."""
    frame_count = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            value = int(
                amplitude
                * 32767
                * math.sin(2 * math.pi * freq * index / sample_rate)
            )
            frames += struct.pack("<h", value)
        wav.writeframes(bytes(frames))
    return path
