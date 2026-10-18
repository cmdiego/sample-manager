"""Arrangement planning utilities."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from .profiles import ArrangementProfile, ExportProfile

_MULTISLASH = re.compile(r"/+")


def _render_template(template: str, sample: dict, index: int) -> str:
    rel_path = sample["rel_path"]
    pack = Path(rel_path).parts[0] if Path(rel_path).parts else ""
    name_stem = Path(sample["filename"]).stem
    ext = sample["ext"] or ""
    category = Path(rel_path).parts[0] if Path(rel_path).parts else ""

    tokens = {
        "category": category,
        "pack": pack,
        "pack_short": pack[:12],
        "type": ext.lstrip("."),
        "key": "",
        "bpm": "",
        "index": f"{index:03d}",
        "name": name_stem,
    }
    rendered = template.format_map(tokens)
    rendered = _MULTISLASH.sub("/", rendered.strip().strip("/"))
    if not Path(rendered).suffix and ext:
        rendered = f"{rendered}{ext}"
    return rendered


def build_plan(
    *,
    arrangement: dict,
    samples: list[dict],
    arrangement_profile: ArrangementProfile,
    export_profile: ExportProfile,
    mode_hint: str = "copy",
    folder_paths: dict[int, str] | None = None,
) -> dict:
    """Build deterministic export plan for an arrangement.

    Args:
        arrangement: Arrangement dict
        samples: List of sample dicts (must include 'folder_id' if using virtual folders)
        arrangement_profile: Arrangement profile with naming template
        export_profile: Export constraints and policies
        mode_hint: Operation mode hint (copy/symlink/move)
        folder_paths: Optional mapping of sample_id -> virtual folder path

    Returns:
        Plan dict with operations, warnings, errors, stats
    """
    ordered = sorted(samples, key=lambda s: (s["id"], s["rel_path"]))
    ops = []
    collisions: dict[str, list[dict]] = {}

    for i, s in enumerate(ordered, start=1):
        dst_rel_path = _render_template(arrangement_profile.naming_template, s, i)

        # Prepend virtual folder path if present
        if folder_paths and s["id"] in folder_paths:
            folder_path = folder_paths[s["id"]]
            if folder_path:
                # Normalize and combine paths
                dst_rel_path = str(PurePosixPath(folder_path) / dst_rel_path)
                dst_rel_path = _MULTISLASH.sub("/", dst_rel_path.strip().strip("/"))

        ops.append(
            {
                "sample_id": int(s["id"]),
                "src_abs_path": str(Path(s["library_root_path"]) / s["rel_path"]),
                "dst_rel_path": dst_rel_path,
                "mode_hint": mode_hint,
            }
        )
        collisions.setdefault(dst_rel_path, []).append(ops[-1])

    warnings: list[str] = []
    errors: list[str] = []

    if arrangement_profile.collision_policy == "suffix":
        renamed_ops = []
        for dst in sorted(collisions.keys()):
            bucket = sorted(collisions[dst], key=lambda x: (x["sample_id"], x["src_abs_path"]))
            if len(bucket) == 1:
                renamed_ops.append(bucket[0])
                continue
            for j, op in enumerate(bucket, start=1):
                base = Path(op["dst_rel_path"])
                suffix = f"_{j:03d}"
                op = op.copy()
                op["dst_rel_path"] = str(base.with_name(f"{base.stem}{suffix}{base.suffix}"))
                renamed_ops.append(op)
            warnings.append(f"collision resolved by suffix for {dst}")
        ops = renamed_ops
    elif arrangement_profile.collision_policy == "dedupe_hash":
        renamed_ops = []
        for dst in sorted(collisions.keys()):
            bucket = sorted(collisions[dst], key=lambda x: (x["sample_id"], x["src_abs_path"]))
            if len(bucket) == 1:
                renamed_ops.append(bucket[0])
                continue
            for op in bucket:
                base = Path(op["dst_rel_path"])
                token = hashlib.sha1(op["src_abs_path"].encode("utf-8")).hexdigest()[:8]
                op = op.copy()
                op["dst_rel_path"] = str(base.with_name(f"{base.stem}_{token}{base.suffix}"))
                renamed_ops.append(op)
            warnings.append(f"collision resolved by hash for {dst}")
        ops = renamed_ops
    else:
        for dst, bucket in sorted(collisions.items()):
            if len(bucket) > 1:
                errors.append(f"collision on destination path: {dst}")

    ops = sorted(ops, key=lambda x: (x["dst_rel_path"], x["src_abs_path"]))

    max_depth = export_profile.max_depth
    for op in ops:
        depth = len(Path(op["dst_rel_path"]).parts)
        if depth > max_depth:
            msg = f"path depth {depth} exceeds max_depth={max_depth}: {op['dst_rel_path']}"
            if export_profile.on_violation == "fail":
                errors.append(msg)
            else:
                warnings.append(msg)

    stats = {
        "samples": len(samples),
        "operations": len(ops),
        "collisions": sum(1 for v in collisions.values() if len(v) > 1),
    }

    return {
        "arrangement_id": arrangement["id"],
        "arrangement_name": arrangement["name"],
        "profile_name": arrangement_profile.name,
        "export_profile_name": export_profile.name,
        "operations": ops,
        "warnings": warnings,
        "errors": errors,
        "stats": stats,
    }
