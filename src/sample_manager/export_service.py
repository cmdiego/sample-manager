"""Export and revert orchestration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .repos.export_repo import ExportRunRepo, HistoryEntryRepo


def apply_plan(
    *,
    export_dir: Path,
    plan: dict,
    mode: str,
    dry_run: bool,
) -> tuple[list[dict], list[str]]:
    """Apply plan operations and return per-op results + errors."""
    # Reject path escapes before any operation, including symlinked parents.
    root = export_dir.resolve()
    for op in plan["operations"]:
        destination = (root / op["dst_rel_path"]).resolve()
        if destination == root or not destination.is_relative_to(root):
            raise ValueError(f"Export path escapes destination: {op['dst_rel_path']}")
    results: list[dict] = []
    errors: list[str] = []

    for op in plan["operations"]:
        src = Path(op["src_abs_path"])
        dst = export_dir / op["dst_rel_path"]
        result = {
            "sample_id": op["sample_id"],
            "src_abs_path": str(src),
            "dst_abs_path": str(dst),
            "status": "planned" if dry_run else "applied",
            "message": "",
        }

        if dry_run:
            results.append(result)
            continue

        if not src.exists():
            result["status"] = "failed"
            result["message"] = "source missing"
            errors.append(f"source missing: {src}")
            results.append(result)
            continue

        if dst.exists():
            result["status"] = "failed"
            result["message"] = "destination exists"
            errors.append(f"destination exists: {dst}")
            results.append(result)
            continue

        try:
            # Directory creation is an operation failure too; retain earlier
            # successes in history so a partial run can still be reverted.
            dst.parent.mkdir(parents=True, exist_ok=True)
            if mode == "copy":
                shutil.copy2(src, dst)
            elif mode == "symlink":
                dst.symlink_to(src)
            elif mode == "move":
                shutil.move(str(src), str(dst))
            else:
                raise ValueError(f"Unsupported mode: {mode}")
        except Exception as e:
            result["status"] = "failed"
            result["message"] = str(e)
            errors.append(f"{dst}: {e}")
        results.append(result)

    return results, errors


def persist_export_history(
    *,
    db,
    arrangement_id: int,
    export_profile_name: str,
    export_dir: Path,
    mode: str,
    plan: dict,
    results: list[dict],
    errors: list[str],
    dry_run: bool,
) -> dict:
    export_repo = ExportRunRepo(db)
    history_repo = HistoryEntryRepo(db)

    if dry_run:
        status = "planned"
    elif errors:
        status = "partial"
    else:
        status = "applied"

    export_row = export_repo.create(
        arrangement_id=arrangement_id,
        export_profile_name=export_profile_name,
        export_dir=str(export_dir),
        mode=mode,
        status=status,
    )

    plan_payload = dict(plan)
    plan_payload["execution"] = results
    history_repo.create(
        export_id=export_row["id"],
        plan_json=plan_payload,
        stats_json={
            "operations": len(results),
            "applied": sum(1 for r in results if r["status"] == "applied"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        },
        errors_json={"errors": errors} if errors else None,
    )
    return export_row


def revert_export(*, db, export_id: int, dry_run: bool) -> tuple[dict, list[str]]:
    export_repo = ExportRunRepo(db)
    history_repo = HistoryEntryRepo(db)

    export_row = export_repo.get_by_id(export_id)
    if export_row is None:
        raise ValueError(f"Export not found: {export_id}")

    history = history_repo.get_latest_for_export(export_id)
    if history is None:
        raise ValueError(f"No history found for export: {export_id}")

    plan = json.loads(history["plan_json"])
    execution = plan.get("execution", [])
    errors: list[str] = []
    reverted = 0

    for op in reversed(execution):
        if op.get("status") not in {"applied", "planned"}:
            continue
        dst = Path(op["dst_abs_path"])
        if dry_run:
            reverted += 1
            continue
        try:
            if dst.is_symlink() or dst.is_file():
                dst.unlink(missing_ok=True)
            reverted += 1
        except Exception as e:
            errors.append(f"{dst}: {e}")

    if dry_run:
        status = export_row["status"]
    elif errors:
        status = "partial"
    else:
        status = "reverted"
    export_repo.set_status(export_id, status)

    return {"export_id": export_id, "reverted": reverted, "status": status}, errors
