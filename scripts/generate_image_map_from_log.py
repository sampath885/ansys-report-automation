#!/usr/bin/env python3
"""Generate an image_map.yaml from auto_discover_log.txt or by scanning exports/."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from ansys_report.images.auto_discover import (
    load_image_match_rules,
    parse_manifest_export_log,
    resolve_assets_auto_discover,
    resolve_assets_smart,
    scan_image_folder,
)
from ansys_report.images.log_slot_mapper import parse_autodiscover_export_log
from ansys_report.images.slots import figure_slots_for_config

_LOG_LINE = re.compile(
    r"^OK\s+\[[^\]]+\]\s+->\s+(.+\.png)\s*$",
    re.IGNORECASE,
)


def _rel_from_log_line(exports_root: Path, absolute_png: str) -> str | None:
    path = Path(absolute_png.replace("\\", "/"))
    try:
        rel = path.relative_to(exports_root)
        return rel.as_posix()
    except ValueError:
        parts = path.as_posix().split("/exports/")
        if len(parts) == 2:
            return parts[1]
    return None


def paths_from_log(log_path: Path, exports_root: Path) -> list[str]:
    rels: list[str] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LOG_LINE.match(line.strip())
        if not match:
            continue
        rel = _rel_from_log_line(exports_root, match.group(1))
        if rel:
            rels.append(rel)
    return sorted(set(rels))


def generate_map(
    exports_root: Path,
    *,
    rules_path: Path | None = None,
    section_content: Path | None = None,
    log_path: Path | None = None,
) -> dict[str, str]:
    repo = Path(__file__).resolve().parents[1]
    rules = load_image_match_rules(rules_path or repo / "config" / "image_match_rules.yaml")
    slots = figure_slots_for_config(section_content) or sorted(rules.rules.keys())

    if log_path is not None and log_path.exists():
        log_map = parse_autodiscover_export_log(log_path, exports_root)
        if log_map:
            return log_map

        manifest_map = parse_manifest_export_log(log_path, exports_root)
        if manifest_map:
            return dict(sorted(manifest_map.items()))

    assets = resolve_assets_auto_discover(exports_root, rules, slots=slots, check_quality=False)
    return {
        slot: path.relative_to(exports_root).as_posix()
        for slot, path in sorted(assets.resolved.items())
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports", type=Path, help="Path to exports/ folder")
    parser.add_argument("-o", "--output", type=Path, help="Write image_map YAML here")
    parser.add_argument("--rules", type=Path, help="image_match_rules.yaml path")
    parser.add_argument("--section-content", type=Path, help="section_content.yaml for slot list")
    parser.add_argument(
        "--log",
        type=Path,
        help="Export log with OK [slot] -> path lines (manifest mode)",
    )
    parser.add_argument("--list-files", action="store_true", help="Only list PNG files found")
    args = parser.parse_args()

    exports_root = args.exports.resolve()
    if not exports_root.exists():
        raise SystemExit(f"exports folder not found: {exports_root}")

    if args.list_files:
        for rel in scan_image_folder(exports_root):
            print(rel)
        return 0

    log_path = args.log
    if log_path is None:
        candidate = exports_root / "auto_discover_log.txt"
        if candidate.exists():
            log_path = candidate

    slots = generate_map(
        exports_root,
        rules_path=args.rules,
        section_content=args.section_content,
        log_path=log_path,
    )

    by_path: dict[str, list[str]] = {}
    for slot, rel in slots.items():
        by_path.setdefault(rel, []).append(slot)
    duplicates = {rel: names for rel, names in by_path.items() if len(names) > 1}

    payload = {"version": 1, "slots": slots}
    text = yaml.safe_dump(payload, sort_keys=True, allow_unicode=True)

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {len(slots)} slots to {args.output}")
    else:
        print(text, end="")

    if duplicates:
        print(f"\nWarning: {len(duplicates)} PNG path(s) shared by multiple slots:", file=__import__("sys").stderr)
        for rel, names in sorted(duplicates.items()):
            print(f"  {rel}: {', '.join(sorted(names))}", file=__import__("sys").stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
