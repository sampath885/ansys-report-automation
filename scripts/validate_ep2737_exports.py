"""Check which EP2737 report figure PNGs exist under exports/."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
MAP = REPO / "config" / "ep2737_image_map.yaml"


def main() -> int:
    if not MAP.exists():
        print(f"Missing {MAP}")
        return 1

    from ansys_report.ep2737_paths import ep2737_case_root

    case = ep2737_case_root()
    exports = case / "exports"
    data = yaml.safe_load(MAP.read_text(encoding="utf-8"))
    slots = data.get("slots") or {}

    present: list[str] = []
    missing: list[str] = []

    for slot, rel in sorted(slots.items()):
        path = exports / Path(str(rel).replace("/", "\\"))
        if path.exists():
            present.append(slot)
        else:
            missing.append(slot)

    print(f"Case exports root: {exports}")
    print(f"Present: {len(present)} / {len(slots)}")
    if missing:
        print("\nMissing PNGs:")
        for slot in missing:
            print(f"  - {slot}: {slots[slot]}")
        return 1

    print("All mapped figure PNGs are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
