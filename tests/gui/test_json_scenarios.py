"""Run JSON GUI simulation scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from sample_manager.gui.app import create_main_window
from sample_manager.gui.simulation import GuiSimulationRuntime


SCENARIO_DIR = Path(__file__).with_name("scenarios")
SCENARIOS = sorted(SCENARIO_DIR.glob("*.json"))


@pytest.mark.parametrize("scenario_path", SCENARIOS, ids=lambda path: path.stem)
def test_json_gui_scenario(populated_service, qtbot, scenario_path: Path):
    service, root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.activateWindow()
    QApplication.setActiveWindow(window)

    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    runtime = GuiSimulationRuntime(window=window, root=root)
    runtime.run(scenario)
