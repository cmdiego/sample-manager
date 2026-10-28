"""Arrangement workspace built on shared services, with explicit export/revert."""

import asyncio
from rich.text import Text
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static
from ...db import Db
from ... import profiles
from ...repos.export_repo import ExportRunRepo
from ...services.arrangement_workflow import ArrangementWorkflow
from .confirm_screen import ConfirmScreen


class ArrangementsScreen(ModalScreen):
    """Save Stage, inspect a concrete plan and confirm history-backed operations."""

    BINDINGS = [("escape", "cancel", "Return")]
    DEFAULT_CSS = """
    ArrangementsScreen { align: center middle; }
    #arrangements-dialog { width: 100; max-width: 98%; height: 80%;
                           border: round $accent; background: $surface; padding: 0 1; }
    #arrangements-scroll { height: 1fr; }
    #arrangements-dialog Label, #arrangements-result { height: auto; }
    #arrangements-dialog Horizontal { height: 3; }
    #arrangements-dialog Button { min-width: 12; margin-right: 1; }
    #arrangement-plan { height: auto; min-height: 3; }
    """

    def __init__(self, db_path: str, profiles_dir: Path, on_change):
        super().__init__()
        self.db_path, self.profiles_dir = db_path, profiles_dir
        self.on_change = on_change
        self.busy = False
        with Db(db_path) as db:
            self.arrangements = ArrangementWorkflow(db, profiles_dir).list_arrangements()
            self.runs = ExportRunRepo(db).list_recent()
        self.arrangement_profiles = profiles.load_arrangement_profiles(profiles_dir)
        self.export_profiles = profiles.load_export_profiles(profiles_dir)

    def compose(self) -> ComposeResult:
        """Scroll content rather than clipping actions in small terminals."""
        with Vertical(id="arrangements-dialog"):
            with VerticalScroll(id="arrangements-scroll"):
                yield Label("Arrangements · Stage folders are preserved")
                yield Select([(Text(r["name"]), r["name"]) for r in self.arrangements], id="arrangement-choice", prompt="Choose saved arrangement")
                yield Input(placeholder="New arrangement name", id="arrangement-name")
                yield Select([(p.name, p.name) for p in self.arrangement_profiles], id="arrangement-profile", prompt="Arrangement profile")
                with Horizontal():
                    yield Button("Save Stage", id="arrangement-create")
                    yield Button("Add Stage", id="arrangement-add")
                yield Select([], id="arrangement-sample", prompt="Saved sample to remove")
                yield Button("Remove sample…", id="arrangement-remove")
                yield Select([(p.name, p.name) for p in self.export_profiles], id="export-profile", prompt="Export profile")
                yield Input(placeholder="Copy export destination directory", id="export-target")
                with Horizontal():
                    yield Button("Preview", id="arrangement-preview")
                    yield Button("Copy export…", id="arrangement-export")
                yield Static("Choose profiles and Preview to see the folder layout.\nNo profiles? Configure YAML files in " + str(self.profiles_dir), id="arrangement-plan", markup=False)
                yield Label("Recorded copy exports")
                yield Select([(f"#{r['id']} {r['status']} · {r['export_dir']}", r["id"])
                              for r in self.runs if r["mode"] == "copy" and r["status"] in ("applied", "partial")],
                             id="export-history", prompt="Choose an export to revert")
                yield Button("Revert selected…", id="arrangement-revert")
                yield Static("", id="arrangements-result", markup=False)
            yield Button("Return", id="arrangements-close")

    def action_cancel(self):
        """Never abandon a running filesystem job while its result is pending."""
        if not self.busy:
            self.dismiss()

    def _value(self, selector):
        """Reject blank choices before any persistence operation."""
        value = self.query_one(selector, Select).value
        if value is Select.BLANK:
            raise ValueError("Choose " + selector.removeprefix("#").replace("-", " "))
        return value

    def on_select_changed(self, event: Select.Changed):
        """Refresh membership when a saved arrangement is selected."""
        if event.select.id != "arrangement-choice" or event.value is Select.BLANK:
            return
        with Db(self.db_path) as db:
            samples = ArrangementWorkflow(db, self.profiles_dir).samples(str(event.value))
        self.query_one("#arrangement-sample", Select).set_options([
            (Text(f"#{r['id']} {r['rel_path']}"), r["id"]) for r in samples
        ])

    def _show_plan(self, plan):
        """Show real destination paths and all warnings/errors before export."""
        lines = [f"{plan['arrangement_name']} · {plan['stats']['operations']} files"]
        lines += [op["dst_rel_path"] for op in plan["operations"]]
        lines += ["Warning: " + text for text in plan["warnings"]]
        lines += ["Error: " + text for text in plan["errors"]]
        self.query_one("#arrangement-plan", Static).update("\n".join(lines))

    async def on_button_pressed(self, event: Button.Pressed):
        """Keep export I/O off Textual's event loop and capture confirmed inputs."""
        event.stop()
        if self.busy:
            return
        action = event.button.id
        if action == "arrangements-close":
            self.dismiss()
            return
        try:
            with Db(self.db_path) as db:
                workflow = ArrangementWorkflow(db, self.profiles_dir)
                if action == "arrangement-create":
                    row = workflow.create_from_stage(self.query_one("#arrangement-name", Input).value,
                                                     str(self._value("#arrangement-profile")))
                    choice = self.query_one("#arrangement-choice", Select)
                    choice.set_options([(Text(r["name"]), r["name"]) for r in workflow.list_arrangements()])
                    choice.value = row["name"]
                    self.query_one("#arrangements-result", Static).update("Saved Stage and folders")
                elif action == "arrangement-add":
                    count = workflow.add_stage(str(self._value("#arrangement-choice")))
                    self.query_one("#arrangements-result", Static).update(f"Added {count} samples")
                elif action in ("arrangement-preview", "arrangement-export"):
                    plan = workflow.preview(str(self._value("#arrangement-choice")), str(self._value("#export-profile")))
                    self._show_plan(plan)
                    if action == "arrangement-export":
                        raw = self.query_one("#export-target", Input).value.strip()
                        if not raw:
                            raise ValueError("Enter an export destination")
                        target = Path(raw).expanduser().resolve()
                        summary = f"Copy {len(plan['operations'])} files from {plan['arrangement_name']} to:\n{target}\nExisting files will not be overwritten. Source files stay in place."
                        self.app.push_screen(ConfirmScreen(summary, "Confirm copy"),
                                             callback=lambda yes: self._confirmed_export(yes, plan, target))
                elif action == "arrangement-remove":
                    name = str(self._value("#arrangement-choice"))
                    sample_id = int(self._value("#arrangement-sample"))
                    self.app.push_screen(ConfirmScreen(f"Remove sample #{sample_id} from {name}? Source file stays in place.", "Remove sample"),
                                         callback=lambda yes: self._confirmed_remove(yes, name, sample_id))
                elif action == "arrangement-revert":
                    export_id = int(self._value("#export-history"))
                    row = ExportRunRepo(db).get_by_id(export_id)
                    self.app.push_screen(ConfirmScreen(f"Revert copy export #{export_id} in:\n{row['export_dir']}\nRemove files recorded as successfully copied by that run?", "Confirm revert"),
                                         callback=lambda yes: self._confirmed_revert(yes, export_id))
        except Exception as exc:
            self.query_one("#arrangements-result", Static).update(str(exc))

    def _confirmed_remove(self, yes, name, sample_id):
        """Apply the captured membership edit only after confirmation."""
        if yes:
            try:
                with Db(self.db_path) as db:
                    flow = ArrangementWorkflow(db, self.profiles_dir)
                    flow.remove_sample(name, sample_id, confirmed=True)
                    self.query_one("#arrangement-sample", Select).set_options([
                        (Text(f"#{r['id']} {r['rel_path']}"), r["id"]) for r in flow.samples(name)
                    ])
                self.query_one("#arrangement-plan", Static).update("Membership changed; Preview to refresh the export layout.")
            except Exception as exc:
                self.query_one("#arrangements-result", Static).update(str(exc))

    def _confirmed_export(self, yes, plan, target):
        """Dispatch exactly the reviewed plan/target only after acceptance."""
        if yes:
            self.busy = True
            self.run_worker(self._execute("export", plan, target), exit_on_error=False)

    def _confirmed_revert(self, yes, export_id):
        """Pass the selected immutable history ID through confirmation."""
        if yes:
            self.busy = True
            self.run_worker(self._execute("revert", export_id, None), exit_on_error=False)

    async def _execute(self, kind, value, target):
        """Own a worker DB connection and retain partial-failure history in the UI."""
        self.busy = True
        def run():
            """Filesystem services run on their own thread/connection."""
            with Db(self.db_path) as db:
                flow = ArrangementWorkflow(db, self.profiles_dir)
                if kind == "export":
                    return flow.export_copy(value, target, confirmed=True)
                return flow.revert(value, confirmed=True)
        try:
            result, errors = await asyncio.to_thread(run)
            self.query_one("#arrangements-result", Static).update(f"{kind}: {result}\n" + "\n".join(errors))
            with Db(self.db_path) as db:
                runs = ExportRunRepo(db).list_recent()
            self.query_one("#export-history", Select).set_options([
                (f"#{r['id']} {r['status']} · {r['export_dir']}", r["id"])
                for r in runs if r["mode"] == "copy" and r["status"] in ("applied", "partial")
            ])
            self.on_change()
        except Exception as exc:
            self.query_one("#arrangements-result", Static).update(str(exc))
        finally:
            self.busy = False
