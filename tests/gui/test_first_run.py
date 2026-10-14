"""GUI first-run checks that never touch the developer's home directory."""

from __future__ import annotations

from sample_manager import config, profiles
from sample_manager.gui import app as gui_app
from sample_manager.services.library_browser import LibraryBrowserService


def test_gui_setup_creates_starters_and_preserves_existing_files(tmp_path, monkeypatch):
    """Fresh setup is idempotent across both config and profile files."""
    config_path = tmp_path / "home" / "config.yaml"
    profiles_dir = tmp_path / "home" / "profiles"
    template = config.get_default_config_template()
    template["db_path"] = str(tmp_path / "home" / "samples.sqlite3")
    template["profiles_dir"] = str(profiles_dir)
    monkeypatch.setattr(config, "get_config_path", lambda: config_path)
    monkeypatch.setattr(config, "get_default_config_template", lambda: template.copy())

    assert gui_app._ensure_gui_setup() is True
    assert config_path.exists()
    arrangement_file = profiles_dir / profiles.ARRANGEMENT_PROFILES_FILENAME
    export_file = profiles_dir / profiles.EXPORT_PROFILES_FILENAME
    assert arrangement_file.exists() and export_file.exists()

    # A later launch must not erase personal config or edited profiles.
    saved = config.load_config(config_path)
    saved["custom"] = "keep me"
    config.save_config(saved, config_path)
    arrangement_file.write_text("custom arrangement profile")
    assert gui_app._ensure_gui_setup() is False
    assert config.load_config(config_path)["custom"] == "keep me"
    assert arrangement_file.read_text() == "custom arrangement profile"


def test_empty_gui_invites_add_folder(browser_db, qtbot):
    """The first open window has a discoverable next action."""
    window = gui_app.create_main_window(LibraryBrowserService(browser_db))
    qtbot.addWidget(window)

    assert window.controller.current_root is None
    assert window._add_library_action.isEnabled()
    assert not window._rescan_action.isEnabled()
    assert "Add Folder" in window.statusBar().currentMessage()


def test_temporary_simulation_skips_user_setup(monkeypatch):
    """Disposable JSON sessions do not initialize real user paths."""
    def fail_setup():
        """Catch any unintended first-run side effect."""
        raise AssertionError("user setup should not run")

    monkeypatch.setattr(gui_app, "_ensure_gui_setup", fail_setup)
    monkeypatch.setattr(gui_app, "_run_temporary_simulation", lambda _argv: 0)
    assert gui_app.run_gui(["sampleman"], simulation_temp=True) == 0
