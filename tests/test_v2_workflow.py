"""Disposable end-to-end service and Textual checks for the v2 integration."""

import asyncio
import json
from pathlib import Path
import pytest
from textual.widgets import Input, Select, Button, Static, OptionList

from sample_manager.config import save_config
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.scanner import scan_library
from sample_manager.services.arrangement_workflow import ArrangementWorkflow
from sample_manager.services.stage_workspace import StageWorkspace
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.settings import TuiPreferences
from sample_manager.tui.widgets.arrangements_screen import ArrangementsScreen
from sample_manager.tui.widgets.confirm_screen import ConfirmScreen


@pytest.fixture
def workspace(tmp_path):
    """Generate redistributable samples, real SQLite and minimal profile YAML."""
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    root = tmp_path / "samples"
    (root / "pack").mkdir(parents=True)
    for name in ("kick", "snare"):
        sf.write(root / "pack" / (name + ".wav"), np.full((4800, 1), 0.25), 48000)
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "arrangement_profiles.yaml").write_text(
        '- name: flat\n  layout_mode: monolithic\n  naming_template: "{name}"\n  collision_policy: suffix\n')
    (profile_dir / "export_profiles.yaml").write_text(
        '- name: portable\n  max_depth: 8\n  max_filename_len: 64\n  illegal_chars: "<>:?*"\n')
    db_path = tmp_path / "index.sqlite3"
    with Db(db_path) as db:
        apply_migrations(db)
        scan_library(db, root)
    config = tmp_path / "config.yaml"
    save_config({"db_path": str(db_path), "profiles_dir": str(profile_dir),
                 "library_roots": [str(root)], "default_library_root": str(root)}, config)
    return db_path, root, profile_dir, config


def test_stage_arrangement_copy_partial_failure_revert_and_source_invariance(workspace, tmp_path):
    """Existing service rules carry Stage folders through preview/export/history."""
    db_path, root, profiles, _ = workspace
    before = {p: p.read_bytes() for p in root.rglob("*.wav")}
    with Db(db_path) as db:
        stage = StageWorkspace(db)
        folder = stage.create_folder("Drums/Kicks")
        ids = [r["id"] for r in db.fetchall("SELECT id FROM sample")]
        for sid in ids:
            stage.stage_sample(sid, folder)
        flow = ArrangementWorkflow(db, profiles)
        flow.create_from_stage("Kit", "flat")
        plan = flow.preview("Kit", "portable")
        assert all(op["dst_rel_path"].startswith("Drums/Kicks/") for op in plan["operations"])
        target = tmp_path / "export"
        with pytest.raises(ValueError, match="Confirm"):
            flow.export_copy(plan, target)
        assert not target.exists()
        row, errors = flow.export_copy(plan, target, confirmed=True)
        assert row["status"] == "applied" and not errors
        partial, errors = flow.export_copy(plan, target, confirmed=True)
        assert partial["status"] == "partial" and len(errors) == 2
        with pytest.raises(ValueError, match="Confirm"):
            flow.revert(row["id"])
        result, errors = flow.revert(row["id"], confirmed=True)
        assert result["status"] == "reverted" and not errors
        assert not list(target.rglob("*.wav"))
    assert before == {p: p.read_bytes() for p in before}


def test_export_path_escape_is_rejected_before_any_write(workspace, tmp_path):
    """User-editable naming profiles cannot escape the confirmed destination."""
    db_path, root, profiles, _ = workspace
    with Db(db_path) as db:
        flow = ArrangementWorkflow(db, profiles)
        plan = {"operations": [{"src_abs_path": str(next(root.rglob("*.wav"))),
                                "dst_rel_path": "../escape.wav", "sample_id": 1}], "errors": []}
        with pytest.raises(ValueError, match="escapes"):
            flow.export_copy(plan, tmp_path / "export", confirmed=True)
        assert not (tmp_path / "escape.wav").exists()


def test_views_columns_theme_arrangement_and_cancelled_export(workspace, tmp_path):
    """Drive mounted views and real forms, retaining Stage and cancelling writes."""
    db_path, root, profiles, config = workspace

    async def exercise():
        app = SampleManagerApp(config_path=config, preferences=TuiPreferences(False, "disabled"))
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause()
            await pilot.press("l", "enter")  # enter pack, stage kick
            assert len(app._data.get_selection_ids()) == 1
            await pilot.press("alt+2", "k", "i")
            assert app._filter_query == "ki"
            await pilot.press("alt+3")
            assert app._view == "stage" and app.query_one("#stage-actions").display
            await pilot.press("alt+2")
            assert app._filter_query == "ki"
            app._switch_view("browse")
            app.action_focus_columns()
            await pilot.press("alt+right")
            assert app.focused.id == "tag-column"
            await pilot.press("escape")
            app._apply_preferences(TuiPreferences(False, "disabled", theme="light"), persist=True)
            assert app.theme == "sample-manager-light"
            await pilot.press("alt+4")
            assert isinstance(app.screen, ArrangementsScreen)
            screen = app.screen
            screen.query_one("#arrangement-profile", Select).value = "flat"
            screen.query_one("#arrangement-name", Input).value = "Pilot Kit"
            screen.query_one("#arrangement-create", Button).press()
            await pilot.pause()
            assert screen.query_one("#arrangement-choice", Select).value == "Pilot Kit"
            screen.query_one("#export-profile", Select).value = "portable"
            screen.query_one("#export-target", Input).value = str(tmp_path / "cancelled-export")
            screen.query_one("#arrangement-export", Button).press()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not (tmp_path / "cancelled-export").exists()
            assert "kick.wav" in screen.query_one("#arrangement-plan", Static).content
            await pilot.press("escape")
            assert app.query_one("#transport-bar").region.width == 140
    asyncio.run(exercise())


def test_python_engine_diagnostics_on_generated_corpus(cli_runner, workspace):
    """The CLI measures first non-silent buffer timing with a real headless mixer."""
    from sample_manager.cli import app
    _, root, _, _ = workspace
    result = cli_runner.invoke(app, ["engine", "bench", str(root), "--backend", "null", "--passes", "1"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["results"]) == 2
    assert payload["summary"]["p95_ms"] > 0
    assert "not acoustic" in payload["measurement"]


def test_backfill_executor_jobs_are_serialized_after_async_cancellation(workspace, monkeypatch):
    """Cancelling an asyncio await cannot allow its live decoder thread to overlap."""
    import threading
    from sample_manager.services.sample_analysis import BackfillResult
    entered, release = threading.Event(), threading.Event()
    calls = []
    def slow_backfill(db, *, library_root_id, cancel, pause_seconds):
        """Hold the first executor job after its async waiter was cancelled."""
        calls.append(library_root_id)
        if library_root_id == 1:
            entered.set()
            assert release.wait(5)
        return BackfillResult(0, 0, 0, cancelled=cancel.is_set())
    monkeypatch.setattr("sample_manager.tui.app.backfill_analysis", slow_backfill)
    async def exercise():
        app = SampleManagerApp(preferences=TuiPreferences(False, "disabled"))
        first_cancel, second_cancel = threading.Event(), threading.Event()
        first = asyncio.create_task(app._backfill_analysis(str(workspace[0]), 1, first_cancel))
        assert await asyncio.to_thread(entered.wait, 5)
        first.cancel()
        await first
        assert first_cancel.is_set()
        second = asyncio.create_task(app._backfill_analysis(str(workspace[0]), 2, second_cancel))
        await asyncio.sleep(0.02)
        assert calls == [1]
        release.set()
        await second
        assert calls == [1, 2]
        app._audio_player.close()
        app._waveform_service.close()
    try:
        asyncio.run(exercise())
    finally:
        release.set()


def test_partial_directory_failure_is_recorded_and_revertible(workspace, tmp_path, monkeypatch):
    """Even mkdir failures after earlier successes must retain an export history."""
    db_path, root, profiles, _ = workspace
    with Db(db_path) as db:
        stage = StageWorkspace(db)
        for row in db.fetchall("SELECT id FROM sample"):
            stage.stage_sample(row["id"])
        flow = ArrangementWorkflow(db, profiles)
        flow.create_from_stage("Partial", "flat")
        plan = flow.preview("Partial", "portable")
        real_mkdir = Path.mkdir
        target = tmp_path / "partial"
        calls = []
        def fail_second(path, *args, **kwargs):
            """Model a destination becoming unwritable halfway through a run."""
            if path == target:
                calls.append(path)
                if len(calls) == 2:
                    raise OSError("destination disconnected")
            return real_mkdir(path, *args, **kwargs)
        monkeypatch.setattr(Path, "mkdir", fail_second)
        row, errors = flow.export_copy(plan, target, confirmed=True)
        assert row["status"] == "partial" and len(errors) == 1
        result, errors = flow.revert(row["id"], confirmed=True)
        assert result["status"] == "reverted" and not errors
        assert not list(target.rglob("*.wav"))


def test_folder_tag_facets_intersect_and_include_descendants(workspace):
    """Browse columns narrow within the selected pack, retaining shared tag rules."""
    from sample_manager.tag_service import tag_sample, add_tag_parent
    from sample_manager.tui.data import TuiDataSource
    db_path, root, _, _ = workspace
    with Db(db_path) as db:
        data = TuiDataSource(db)
        rows = db.fetchall("SELECT id, filename FROM sample")
        kick = next(r["id"] for r in rows if r["filename"] == "kick.wav")
        tag_sample(db, kick, "kick")
        snare = next(r["id"] for r in rows if r["filename"] == "snare.wav")
        tag_sample(db, snare, "drums")
        add_tag_parent(db, "kick", "drums")
        facets, _ = data.browse_facets(root, root / "pack")
        assert next(row["samples"] for row in facets if row["name_display"] == "drums") == 2
        assert {item.sample_id for item in data.tagged_samples(root, "drums", root / "pack")} == {kick, snare}
        assert data.tagged_samples(root, "drums", root / "other") == ()


def test_table_summaries_do_not_materialize_waveform_blobs(workspace):
    """Large-library table metadata stays small and excludes peak pyramid payloads."""
    from sample_manager.services.sample_analysis import backfill_analysis
    from sample_manager.tui.data import TuiDataSource
    db_path, root, _, _ = workspace
    with Db(db_path) as db:
        backfill_analysis(db)
        _, summaries = TuiDataSource(db).browse_facets(root, root / "pack")
        assert len(summaries) == 2
        assert all(set(row) == {"sample_id", "duration_seconds", "loudness_lufs"}
                   for row in summaries.values())
        assert all(row["duration_seconds"] == pytest.approx(0.1) for row in summaries.values())
