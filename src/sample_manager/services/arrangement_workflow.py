"""Frontend-neutral Stage → arrangement → preview → confirmed copy/export flow."""

from pathlib import Path
from .. import profiles
from ..arrangement_service import build_plan
from ..arrangement_workspace import ArrangementWorkspaceService
from ..export_service import apply_plan, persist_export_history, revert_export
from ..repos.arrangement_repo import ArrangementRepo
from ..repos.export_repo import ExportRunRepo
from ..repos.selection_repo import SelectionRepo
from ..tag_service import tag_sample
from .stage_workspace import StageWorkspace


class ArrangementWorkflow:
    """Reuse existing persistence/planning/history contracts for terminal workflows."""

    def __init__(self, db, profiles_dir: Path):
        self.db = db
        self.profiles_dir = profiles_dir
        self.repo = ArrangementRepo(db)

    def list_arrangements(self):
        """Return saved arrangements for a choice control."""
        return self.repo.list_all()

    def create_from_stage(self, name: str, profile_name: str):
        """Preserve Stage virtual folders when saving its persistent selection."""
        if not name.strip():
            raise ValueError("Enter an arrangement name")
        if profiles.get_arrangement_profile(profile_name, self.profiles_dir) is None:
            raise ValueError("Choose an available arrangement profile")
        ids = [row["id"] for row in SelectionRepo(self.db).list_samples()]
        if not ids:
            raise ValueError("Stage is empty")
        if self.repo.get_by_name(name):
            raise ValueError("An arrangement with that name already exists")
        with self.db.transaction():
            created = self.repo.create(name.strip(), profile_name, commit=False)
            StageWorkspace(self.db).copy_to_arrangement(created["id"], ids)
        return created

    def add_stage(self, name: str):
        """Merge only new staged samples, retaining saved arrangement placements."""
        arrangement = self._arrangement(name)
        ids = [row["id"] for row in SelectionRepo(self.db).list_samples()]
        return StageWorkspace(self.db).copy_to_arrangement(arrangement["id"], ids)

    def samples(self, name: str):
        """Expose saved membership for explicit remove-sample selection."""
        return self.repo.list_samples(self._arrangement(name)["id"])

    def remove_sample(self, name: str, sample_id: int, *, confirmed=False):
        """Detach one captured sample reference without changing the source file."""
        if not confirmed:
            raise ValueError("Confirm removing this sample first")
        arrangement = self._arrangement(name)
        with self.db.transaction():
            return self.repo.remove_samples(arrangement["id"], [sample_id])

    def preview(self, name: str, export_profile: str):
        """Use exactly the same plan builder and folder mapping as the CLI."""
        arrangement = self._arrangement(name)
        profile = profiles.get_arrangement_profile(arrangement["profile_name"], self.profiles_dir)
        target = profiles.get_export_profile(export_profile, self.profiles_dir)
        if profile is None or target is None:
            raise ValueError("Choose available arrangement/export profiles")
        return build_plan(
            arrangement=arrangement, samples=self.repo.list_samples(arrangement["id"]),
            arrangement_profile=profile, export_profile=target,
            folder_paths=ArrangementWorkspaceService(self.db).get_sample_folder_paths(arrangement["id"]),
        )

    def export_copy(self, plan: dict, target: Path, *, confirmed=False):
        """Apply an explicitly previewed copy plan and record partial failures."""
        if not confirmed:
            raise ValueError("Confirm the copy export first")
        if plan["errors"]:
            raise ValueError("Plan has errors: " + "; ".join(plan["errors"]))
        target = target.expanduser().resolve()
        results, errors = apply_plan(export_dir=target, plan=plan, mode="copy", dry_run=False)
        row = persist_export_history(
            db=self.db, arrangement_id=plan["arrangement_id"],
            export_profile_name=plan["export_profile_name"], export_dir=target,
            mode="copy", plan=plan, results=results, errors=errors, dry_run=False,
        )
        return row, errors

    def revert(self, export_id: int, *, confirmed=False):
        """Revert a selected recorded copy run only after explicit confirmation."""
        if not confirmed:
            raise ValueError("Confirm reverting this export first")
        row = ExportRunRepo(self.db).get_by_id(export_id)
        if row is None or row["mode"] != "copy" or row["status"] not in ("applied", "partial"):
            raise ValueError("Choose an applied or partial copy export")
        return revert_export(db=self.db, export_id=export_id, dry_run=False)

    def tag_stage(self, text: str):
        """Bulk attach one tag using the shared alias/tag validation service."""
        if not text.strip():
            raise ValueError("Enter a tag")
        for row in SelectionRepo(self.db).list_samples():
            tag_sample(self.db, row["id"], text.strip())

    def clear_stage(self, *, confirmed=False):
        """Explicitly clear the shared selection and its virtual folders."""
        if not confirmed:
            raise ValueError("Confirm clearing Stage first")
        return SelectionRepo(self.db).clear()

    def _arrangement(self, name):
        """Report a stale selection without mutating another arrangement."""
        row = self.repo.get_by_name(name)
        if row is None:
            raise ValueError("Arrangement no longer exists")
        return row
