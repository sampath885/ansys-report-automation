#!/usr/bin/env python3
"""Print slot→PNG mapping, duplicates, and folder mismatches for an exports folder."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ansys_report.config import load_image_map, load_project_config  # noqa: E402
from ansys_report.images.analysis_registry import expected_folder_markers, path_allowed_for_slot  # noqa: E402
from ansys_report.images.auto_discover import load_image_match_rules, resolve_assets_smart  # noqa: E402
from ansys_report.images.image_validation import validate_resolved_images  # noqa: E402
from ansys_report.images.map_select import detect_export_layout, resolve_image_map_for_exports  # noqa: E402
from ansys_report.images.slots import figure_slots_for_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports", type=Path, help="Path to exports/ folder")
    parser.add_argument("-c", "--config", type=Path, default=Path("config/project.ep2741.yaml"))
    args = parser.parse_args()

    exports = args.exports.resolve()
    cfg = load_project_config(args.config)
    slots = figure_slots_for_config(cfg.section_content_path) or []
    rules = load_image_match_rules(cfg.image_match_rules_path) if cfg.image_match_rules_path else None
    image_map, mode = resolve_image_map_for_exports(cfg, exports, repo_root=REPO)

    print("=== CONFIG ===")
    print("config:", args.config)
    print("detected layout:", detect_export_layout(exports))
    print("configured map:", cfg.image_map_path)
    print("resolve_mode:", mode)
    print("exports:", exports)
    print("png count:", len(list(exports.rglob("*.png"))) if exports.exists() else 0)
    print("auto_discover_log:", (exports / "auto_discover_log.txt").exists())

    if not exports.exists():
        print("\nERROR: exports folder does not exist on this machine.")
        return 2

    if cfg.image_map_path and cfg.image_map_path.exists():
        raw = load_image_map(cfg.image_map_path)
        hit = sum(1 for rel in raw.slots.values() if (exports / rel).exists())
        print(f"configured map hits: {hit}/{len(raw.slots)}")

    assets = resolve_assets_smart(
        exports,
        slots=slots,
        image_map=image_map,
        rules=rules,
        mode=mode,
        check_quality=False,
    )

    print("\n=== SLOT → PATH ===")
    by_path: dict[str, list[str]] = defaultdict(list)
    bad = 0
    for slot in sorted(assets.resolved):
        path = assets.resolved[slot]
        try:
            rel = path.relative_to(exports).as_posix()
        except ValueError:
            rel = path.as_posix()
        ok = path_allowed_for_slot(slot, rel)
        if not ok:
            bad += 1
        mark = "OK" if ok else "BAD FOLDER"
        print(f"{mark:10} {slot:35} -> {rel}")
        by_path[rel.lower()].append(slot)

    print("\n=== DUPLICATE PNGs ===")
    dup = {rel: ss for rel, ss in by_path.items() if len(ss) > 1}
    if not dup:
        print("(none)")
    else:
        for rel, ss in sorted(dup.items()):
            print(f"  {rel}: {', '.join(sorted(ss))}")

    print("\n=== VALIDATION ===")
    errs, warns = validate_resolved_images(assets.resolved, exports)
    for e in errs:
        print("ERROR:", e)
    for w in warns[:15]:
        print("WARN:", w)
    print(f"missing slots: {len(assets.missing_slots)}")

    watch = [
        "cad_section",
        "geometry_model_orientation",
        "mesh_global",
        "static_earth_gravity",
        "static_fixed_support",
        "static_pressure",
        "harmonic_x_location",
    ]
    print("\n=== KEY SLOTS ===")
    for slot in watch:
        path = assets.resolved.get(slot)
        if not path:
            print(f"{slot}: MISSING")
            continue
        rel = path.relative_to(exports).as_posix()
        expect = expected_folder_markers(slot)
        print(f"{slot}: {rel}  (expect ~ {expect[0] if expect else '?'})")

    if dup or errs or bad:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
