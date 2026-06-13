"""Phase 4 Excel spike — EP2737 design calculation tables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO / "tests" / "fixtures" / "ep2737_golden"
CONFIG = REPO / "config" / "project.ep2737.yaml"
MAP = REPO / "config" / "ep2737_excel_map.yaml"


def run_excel(*, write_golden: bool = False, compare: bool = True) -> int:
    from ansys_report.config import load_project_config
    from ansys_report.excel.ep2737 import read_ep2737_design_calcs, summarize_for_golden
    from ansys_report.excel.reader import read_design_calcs

    cfg = load_project_config(CONFIG)
    case_root = cfg.case_root or cfg.project_dir

    result = read_design_calcs(
        cfg.excel_path,
        excel_map_path=cfg.excel_map_path or MAP,
        case_root=case_root,
        fos_target=cfg.static.fos_target,
    )
    summary = summarize_for_golden(result)

    if write_golden:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        out = GOLDEN_DIR / "4_excel.json"
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote golden: {out}")

    if compare and not write_golden:
        golden_path = GOLDEN_DIR / "4_excel.json"
        if not golden_path.exists():
            print(f"Missing golden file: {golden_path} — run with --write-golden")
            return 1
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        errors = _compare(summary, golden)
        if errors:
            for e in errors:
                print(f"FAIL: {e}")
            return 1
        print("Phase 4 excel golden check: PASS")

    _print_summary(summary)
    return 0


def _compare(actual: dict, golden: dict) -> list[str]:
    errors: list[str] = []
    for section in ("end_flange", "bolt_load", "effort"):
        for key, expected in golden[section].items():
            got = actual[section].get(key)
            if expected is None:
                continue
            if isinstance(expected, float):
                if got is None or abs(float(got) - expected) > 0.01:
                    errors.append(f"{section}.{key}: {got} != {expected}")
            elif got != expected:
                errors.append(f"{section}.{key}: {got} != {expected}")

    for key, expected in golden["row_counts"].items():
        if actual["row_counts"].get(key) != expected:
            errors.append(f"row_counts.{key}: {actual['row_counts'].get(key)} != {expected}")
    return errors


def _print_summary(summary: dict) -> None:
    ef = summary["end_flange"]
    bl = summary["bolt_load"]
    effort = summary["effort"]
    print(f"Flange FOS: {ef['fos']:.3f} (verdict row: {ef['stress_verdict']})")
    print(f"Required thickness: {ef['required_thickness_mm']:.3f} mm")
    print(f"Bolt count: {bl['bolt_count']}, design P: {bl['design_pressure_mpa']} MPa")
    print(f"Preload: {effort['preload_n']:.4f} N ({effort['bolt_size']})")
    print(f"Rows: {summary['row_counts']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="EP2737 Phase 4 excel spike")
    parser.add_argument("--write-golden", action="store_true")
    parser.add_argument("--no-compare", action="store_true")
    args = parser.parse_args()
    return run_excel(write_golden=args.write_golden, compare=not args.no_compare)


if __name__ == "__main__":
    sys.exit(main())
