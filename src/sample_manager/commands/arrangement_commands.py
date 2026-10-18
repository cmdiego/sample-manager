"""Arrangement, selection, export, and revert CLI commands."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable, Optional

import typer

from .. import exit_codes
from ..arrangement_service import build_plan
from ..arrangement_workspace import ArrangementWorkspaceService
from ..export_service import apply_plan, persist_export_history
from ..export_service import revert_export as revert_export_service
from ..repos.arrangement_repo import ArrangementRepo
from ..repos.selection_repo import SelectionRepo
from ..services.stage_workspace import StageWorkspace
from .. import profiles as profiles_module
from ..db import Db


def _parse_sample_ids_args(raw_values: Optional[list[str]]) -> list[int]:
    if not raw_values:
        return []
    parsed: list[int] = []
    for raw in raw_values:
        for piece in raw.split(","):
            token = piece.strip()
            if not token:
                continue
            try:
                parsed.append(int(token))
            except ValueError as e:
                raise ValueError(f"Invalid sample id: {token!r}") from e
    return parsed


def _resolve_sample_selection(
    db: Db,
    *,
    from_ids: Optional[list[str]] = None,
    from_search: Optional[str] = None,
    from_selection: bool = False,
    require_source: bool = False,
) -> set[int]:
    from ..repos.sample_repo import SampleRepo
    from ..search import SearchEngine

    if require_source and not from_ids and not from_search and not from_selection:
        raise ValueError(
            "provide at least one --ids/--from-ids, --from-search, or --from-selection"
        )

    selected_ids: set[int] = set(_parse_sample_ids_args(from_ids))
    if from_search:
        engine = SearchEngine(db)
        result = engine.search(name=from_search, page=1, page_size=10000)
        selected_ids.update(int(item["id"]) for item in result.items)
    if from_selection:
        repo = SelectionRepo(db)
        selected_ids.update(int(item["id"]) for item in repo.list_samples())

    sample_repo = SampleRepo(db)
    missing = sorted(
        sid for sid in selected_ids if sample_repo.get_by_id(sid) is None
    )
    if missing:
        raise ValueError(
            f"sample ids not found: {', '.join(str(v) for v in missing)}"
        )
    return selected_ids


def _load_export_profile_or_default(name: str | None, profiles_dir: Path):
    if name:
        profile = profiles_module.get_export_profile(name, profiles_dir)
        if profile is None:
            raise ValueError(f"export profile not found: {name}")
        return profile
    export_profiles = profiles_module.load_export_profiles(profiles_dir)
    if not export_profiles:
        raise ValueError("no export profiles configured")
    return export_profiles[0]


def register(
    *,
    app: typer.Typer,
    arrangement_app: typer.Typer,
    selection_app: typer.Typer,
    get_db: Callable[[], Db],
    get_profiles_dir: Callable[[], Path],
    format_table: Callable,
) -> None:
    @arrangement_app.command("list")
    def arrangement_list(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            repo = ArrangementRepo(db)
            arrangements = repo.list_all()
            if json_output:
                print(json.dumps(arrangements, indent=2))
            else:
                if not arrangements:
                    typer.echo("No arrangements found.")
                else:
                    typer.echo(f"Arrangements ({len(arrangements)}):\n")
                    for a in arrangements:
                        typer.echo(
                            f"  {a['name']}  "
                            f"[profile={a['profile_name']}, samples={a['sample_count']}]"
                        )
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @arrangement_app.command("create")
    def arrangement_create(
        name: str = typer.Argument(..., help="Arrangement name"),
        profile: str = typer.Option(..., "--profile", help="Arrangement profile name"),
        from_search: Optional[str] = typer.Option(
            None, "--from-search", help="Name pattern to search samples"
        ),
        from_ids: Optional[list[str]] = typer.Option(
            None, "--from-ids", help="Sample IDs (comma-separated or repeatable)"
        ),
        from_selection: bool = typer.Option(
            False, "--from-selection", help="Include IDs from selection buffer"
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            profiles_dir = get_profiles_dir()
            profile_obj = profiles_module.get_arrangement_profile(profile, profiles_dir)
            if profile_obj is None:
                typer.echo(f"Error: arrangement profile not found: {profile}", err=True)
                raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)

            initial_ids = _resolve_sample_selection(
                db,
                from_ids=from_ids,
                from_search=from_search,
                from_selection=from_selection,
            )
            repo = ArrangementRepo(db)
            created = repo.create(name=name, profile_name=profile_obj.name)
            # Stage's virtual layout becomes the initial arrangement layout.
            inserted = (
                StageWorkspace(db).copy_to_arrangement(created["id"], sorted(initial_ids))
                if from_selection else repo.add_samples(created["id"], sorted(initial_ids))
            )
            db.conn.commit()
            payload = {
                "id": created["id"],
                "name": created["name"],
                "profile_name": created["profile_name"],
                "samples_attached": inserted,
                "samples_requested": len(initial_ids),
            }
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                typer.echo(
                    f"Created arrangement '{created['name']}' "
                    f"[profile={created['profile_name']}, samples={inserted}]"
                )
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except typer.Exit:
            raise
        except sqlite3.IntegrityError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_CONSTRAINT_VIOLATION)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @arrangement_app.command("show")
    def arrangement_show(
        name: str = typer.Argument(..., help="Arrangement name"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            repo = ArrangementRepo(db)
            arrangement = repo.get_by_name(name)
            if arrangement is None:
                typer.echo(f"Error: arrangement not found: {name}", err=True)
                raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
            samples = repo.list_samples(arrangement["id"])
            payload = {
                "id": arrangement["id"],
                "name": arrangement["name"],
                "profile_name": arrangement["profile_name"],
                "sample_count": len(samples),
                "sample_ids": [s["id"] for s in samples],
                "samples": samples,
            }
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                typer.echo(f"Arrangement: {arrangement['name']}")
                typer.echo(f"Profile: {arrangement['profile_name']}")
                typer.echo(f"Samples: {len(samples)}")
                if samples:
                    result = type(
                        "ArrangementShowResult",
                        (),
                        {
                            "items": samples,
                            "total": len(samples),
                            "page": 1,
                            "page_size": len(samples),
                            "total_pages": 1,
                        },
                    )()
                    typer.echo("")
                    typer.echo(format_table(result))
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @arrangement_app.command("add")
    def arrangement_add(
        name: str = typer.Argument(..., help="Arrangement name"),
        ids: Optional[list[str]] = typer.Option(
            None, "--ids", help="Sample IDs (comma-separated or repeatable)"
        ),
        from_search: Optional[str] = typer.Option(
            None, "--from-search", help="Name pattern to search samples"
        ),
        from_selection: bool = typer.Option(
            False, "--from-selection", help="Include IDs from selection buffer"
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            repo = ArrangementRepo(db)
            arrangement = repo.get_by_name(name)
            if arrangement is None:
                typer.echo(f"Error: arrangement not found: {name}", err=True)
                raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
            sample_ids = _resolve_sample_selection(
                db,
                from_ids=ids,
                from_search=from_search,
                from_selection=from_selection,
                require_source=True,
            )
            # Merge Stage paths, preserving placement of samples already saved.
            inserted = (
                StageWorkspace(db).copy_to_arrangement(arrangement["id"], sorted(sample_ids))
                if from_selection else repo.add_samples(arrangement["id"], sorted(sample_ids))
            )
            db.conn.commit()
            total = len(repo.list_sample_ids(arrangement["id"]))
            payload = {"added": inserted, "requested": len(sample_ids), "sample_count": total}
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                typer.echo(
                    f"Arrangement '{arrangement['name']}' updated: "
                    f"added {inserted} (requested {len(sample_ids)}), total {total}"
                )
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @arrangement_app.command("remove")
    def arrangement_remove(
        name: str = typer.Argument(..., help="Arrangement name"),
        ids: Optional[list[str]] = typer.Option(
            None, "--ids", help="Sample IDs (comma-separated or repeatable)"
        ),
        from_search: Optional[str] = typer.Option(
            None, "--from-search", help="Name pattern to search samples"
        ),
        from_selection: bool = typer.Option(
            False, "--from-selection", help="Include IDs from selection buffer"
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            repo = ArrangementRepo(db)
            arrangement = repo.get_by_name(name)
            if arrangement is None:
                typer.echo(f"Error: arrangement not found: {name}", err=True)
                raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
            sample_ids = _resolve_sample_selection(
                db,
                from_ids=ids,
                from_search=from_search,
                from_selection=from_selection,
                require_source=True,
            )
            removed = repo.remove_samples(arrangement["id"], sorted(sample_ids))
            total = len(repo.list_sample_ids(arrangement["id"]))
            payload = {"removed": removed, "requested": len(sample_ids), "sample_count": total}
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                typer.echo(
                    f"Arrangement '{arrangement['name']}' updated: "
                    f"removed {removed} (requested {len(sample_ids)}), total {total}"
                )
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @arrangement_app.command("preview")
    def arrangement_preview(
        name: str = typer.Argument(..., help="Arrangement name"),
        export_profile: str = typer.Option(
            None, "--export-profile", help="Export profile name"
        ),
        format: str = typer.Option("table", "--format", help="table|json"),
    ):
        db = get_db()
        try:
            repo = ArrangementRepo(db)
            arrangement = repo.get_by_name(name)
            if arrangement is None:
                typer.echo(f"Error: arrangement not found: {name}", err=True)
                raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
            profiles_dir = get_profiles_dir()
            arrangement_profile = profiles_module.get_arrangement_profile(
                arrangement["profile_name"], profiles_dir
            )
            if arrangement_profile is None:
                raise ValueError(
                    f"arrangement profile not found: {arrangement['profile_name']}"
                )
            exp_profile = _load_export_profile_or_default(export_profile, profiles_dir)
            samples = repo.list_samples(arrangement["id"])
            plan = build_plan(
                arrangement=arrangement,
                samples=samples,
                arrangement_profile=arrangement_profile,
                export_profile=exp_profile,
                mode_hint="copy",
                folder_paths=ArrangementWorkspaceService(db).get_sample_folder_paths(arrangement["id"]),
            )
            if format == "json":
                print(json.dumps(plan, indent=2))
            else:
                typer.echo(f"Arrangement: {plan['arrangement_name']}")
                typer.echo(f"Profile: {plan['profile_name']}")
                typer.echo(f"Export profile: {plan['export_profile_name']}")
                typer.echo(f"Operations: {plan['stats']['operations']}")
                typer.echo(f"Collisions: {plan['stats']['collisions']}")
                if plan["warnings"]:
                    typer.echo("Warnings:")
                    for w in plan["warnings"]:
                        typer.echo(f"  - {w}")
                if plan["errors"]:
                    typer.echo("Errors:")
                    for e in plan["errors"]:
                        typer.echo(f"  - {e}")
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @selection_app.command("add")
    def selection_add(
        ids: Optional[list[str]] = typer.Option(
            None, "--ids", help="Sample IDs (comma-separated or repeatable)"
        ),
        from_search: Optional[str] = typer.Option(
            None, "--from-search", help="Name pattern to search samples"
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            selected_ids = _resolve_sample_selection(
                db,
                from_ids=ids,
                from_search=from_search,
                require_source=True,
            )
            repo = SelectionRepo(db)
            inserted = repo.add_samples(sorted(selected_ids))
            payload = {
                "selected_count": repo.count(),
                "added": inserted,
                "requested": len(selected_ids),
            }
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                typer.echo(
                    f"Selection updated: added {inserted} "
                    f"(requested {len(selected_ids)}), total {payload['selected_count']}"
                )
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @selection_app.command("remove")
    def selection_remove(
        ids: Optional[list[str]] = typer.Option(
            None, "--ids", help="Sample IDs (comma-separated or repeatable)"
        ),
        from_search: Optional[str] = typer.Option(
            None, "--from-search", help="Name pattern to search samples"
        ),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            selected_ids = _resolve_sample_selection(
                db,
                from_ids=ids,
                from_search=from_search,
                require_source=True,
            )
            repo = SelectionRepo(db)
            removed = repo.remove_samples(sorted(selected_ids))
            payload = {
                "selected_count": repo.count(),
                "removed": removed,
                "requested": len(selected_ids),
            }
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                typer.echo(
                    f"Selection updated: removed {removed} "
                    f"(requested {len(selected_ids)}), total {payload['selected_count']}"
                )
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @selection_app.command("list")
    def selection_list(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            repo = SelectionRepo(db)
            items = repo.list_samples()
            if json_output:
                print(json.dumps({"items": items, "total": len(items)}, indent=2))
            else:
                if not items:
                    typer.echo("Selection is empty.")
                else:
                    result = type(
                        "SelectionResult",
                        (),
                        {
                            "items": items,
                            "total": len(items),
                            "page": 1,
                            "page_size": len(items),
                            "total_pages": 1,
                        },
                    )()
                    typer.echo(format_table(result))
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @selection_app.command("clear")
    def selection_clear(
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        db = get_db()
        try:
            repo = SelectionRepo(db)
            cleared = repo.clear()
            if json_output:
                print(json.dumps({"cleared": cleared, "selected_count": 0}, indent=2))
            else:
                typer.echo(f"Selection cleared ({cleared} removed).")
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @app.command("export")
    def export_arrangement(
        arrangement_name: str = typer.Argument(..., help="Arrangement name"),
        to: str = typer.Option(..., "--to", help="Export target directory"),
        export_profile: str = typer.Option(
            None, "--export-profile", help="Export profile name"
        ),
        mode: str = typer.Option("copy", "--mode", help="copy|symlink|move"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing"),
        confirm: bool = typer.Option(False, "--confirm", help="Confirm filesystem writes"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        if not dry_run and not confirm:
            typer.echo("Error: export requires --confirm (or use --dry-run).", err=True)
            raise typer.Exit(exit_codes.ERROR_SAFETY_REFUSAL)
        db = get_db()
        try:
            if mode not in {"copy", "symlink", "move"}:
                raise ValueError(f"invalid mode: {mode}")
            repo = ArrangementRepo(db)
            arrangement = repo.get_by_name(arrangement_name)
            if arrangement is None:
                raise ValueError(f"arrangement not found: {arrangement_name}")
            profiles_dir = get_profiles_dir()
            arrangement_profile = profiles_module.get_arrangement_profile(
                arrangement["profile_name"], profiles_dir
            )
            if arrangement_profile is None:
                raise ValueError(
                    f"arrangement profile not found: {arrangement['profile_name']}"
                )
            exp_profile = _load_export_profile_or_default(export_profile, profiles_dir)
            samples = repo.list_samples(arrangement["id"])
            plan = build_plan(
                arrangement=arrangement,
                samples=samples,
                arrangement_profile=arrangement_profile,
                export_profile=exp_profile,
                mode_hint=mode,
                folder_paths=ArrangementWorkspaceService(db).get_sample_folder_paths(arrangement["id"]),
            )
            if plan["errors"]:
                raise ValueError("plan has errors: " + "; ".join(plan["errors"]))
            export_dir = Path(to).expanduser().resolve()
            results, errors = apply_plan(
                export_dir=export_dir, plan=plan, mode=mode, dry_run=dry_run
            )
            export_row = persist_export_history(
                db=db,
                arrangement_id=arrangement["id"],
                export_profile_name=exp_profile.name,
                export_dir=export_dir,
                mode=mode,
                plan=plan,
                results=results,
                errors=errors,
                dry_run=dry_run,
            )
            payload = {
                "export_id": export_row["id"],
                "status": export_row["status"],
                "dry_run": dry_run,
                "operations": len(results),
                "failed": len(errors),
            }
            if json_output:
                print(json.dumps(payload, indent=2))
            else:
                typer.echo(
                    f"Export {export_row['id']} {export_row['status']} "
                    f"(ops={len(results)}, failed={len(errors)})"
                )
            if errors and not dry_run:
                raise typer.Exit(exit_codes.ERROR_PARTIAL_OPERATION)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()

    @app.command("revert")
    def revert_export(
        export_id: int = typer.Option(..., "--export-id", help="Export ID to revert"),
        confirm: bool = typer.Option(False, "--confirm", help="Confirm revert writes"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview revert only"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        if not dry_run and not confirm:
            typer.echo("Error: revert requires --confirm (or use --dry-run).", err=True)
            raise typer.Exit(exit_codes.ERROR_SAFETY_REFUSAL)
        db = get_db()
        try:
            result, errors = revert_export_service(
                db=db, export_id=export_id, dry_run=dry_run
            )
            if json_output:
                print(json.dumps({"result": result, "errors": errors}, indent=2))
            else:
                typer.echo(
                    f"Revert export {result['export_id']}: {result['status']} "
                    f"(reverted={result['reverted']}, errors={len(errors)})"
                )
            if errors and not dry_run:
                raise typer.Exit(exit_codes.ERROR_PARTIAL_OPERATION)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_INVALID_ARGS)
        except typer.Exit:
            raise
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(exit_codes.ERROR_GENERAL)
        finally:
            db.close()
