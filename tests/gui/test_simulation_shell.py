"""Tests for the JSON simulation shell."""

from __future__ import annotations

from io import StringIO
import json

from PySide6.QtWidgets import QApplication

from sample_manager.gui.app import create_main_window
from sample_manager.gui.simulation import (
    create_temporary_simulation_environment,
    run_simulation_shell,
)


def test_simulation_shell_accepts_json_lines(populated_service, qtbot):
    service, root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.activateWindow()
    QApplication.setActiveWindow(window)

    input_stream = StringIO(
        '{"event": "key", "key": "L"}\n'
        '{"event": "key", "key": "J"}\n'
        '{"command": "snapshot"}\n'
        'exit\n'
    )
    output_stream = StringIO()

    exit_code = run_simulation_shell(
        window,
        root=root,
        input_stream=input_stream,
        output_stream=output_stream,
    )

    assert exit_code == 0
    messages = [
        json.loads(line)
        for line in output_stream.getvalue().splitlines()
        if line.strip()
    ]
    assert messages[0]["event"] == "ready"
    assert messages[-1]["event"] == "exit"
    assert messages[-2]["snapshot"]["path"] == "drums"
    assert messages[-2]["snapshot"]["focus"]["name"] == "snare.wav"


def test_simulation_shell_reports_invalid_json_without_exiting(populated_service, qtbot):
    service, root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)

    input_stream = StringIO('{"event": "key", "key": "Nope"}\nexit\n')
    output_stream = StringIO()

    assert run_simulation_shell(
        window,
        root=root,
        input_stream=input_stream,
        output_stream=output_stream,
    ) == 0
    messages = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert messages[1]["ok"] is False
    assert "unsupported key" in messages[1]["error"]
    assert messages[2]["event"] == "exit"


def test_temporary_simulation_environment_runs_without_user_config(qtbot):
    """The temp fixture gives the shell a real root, DB, and sample rows."""
    env = create_temporary_simulation_environment()
    try:
        window = create_main_window(env.service)
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        window.activateWindow()
        QApplication.setActiveWindow(window)

        input_stream = StringIO(
            '{"command": "snapshot"}\n'
            '{"event": "key", "key": "L"}\n'
            '{"command": "snapshot"}\n'
            'quit\n'
        )
        output_stream = StringIO()

        assert run_simulation_shell(
            window,
            root=env.root,
            input_stream=input_stream,
            output_stream=output_stream,
        ) == 0

        messages = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        assert messages[0]["snapshot"]["visible_rows"] == ["drums", "loops"]
        assert messages[2]["snapshot"]["path"] == "drums"
        assert messages[2]["snapshot"]["visible_rows"] == ["kick.wav", "snare.wav"]
    finally:
        env.close()
