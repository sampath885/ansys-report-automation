"""Phase 3 metadata spike — CAERep / MatML / solve.out without DPF."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO / "tests" / "fixtures" / "ep2737_golden"
CONFIG = REPO / "config" / "project.ep2737.yaml"


def run_metadata(*, write_golden: bool = False, compare: bool = True) -> int:
    from ansys_report.config import load_project_config
    from ansys_report.extract.metadata import extract_project_metadata
    from ansys_report.scanner import scan_project

    cfg = load_project_config(CONFIG)
    inventory = scan_project(
        cfg.project_dir,
        cfg.image_folder,
        cfg.excel_calcs,
        case_root=cfg.case_root,
        excel_bolt_preload=cfg.excel_bolt_preload,
    )
    meta = extract_project_metadata(inventory, cfg.bom_id, cfg.title)
    payload = meta.to_json_dict()

    if write_golden:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        out = GOLDEN_DIR / "3_metadata.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote golden: {out}")

    if compare and not write_golden:
        golden_path = GOLDEN_DIR / "3_metadata.json"
        if not golden_path.exists():
            print(f"Missing golden file: {golden_path} — run with --write-golden")
            return 1
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        errors = _compare(payload, golden)
        if errors:
            for e in errors:
                print(f"FAIL: {e}")
            return 1
        print("Phase 3 metadata golden check: PASS")

    _print_summary(payload)
    return 0


def _compare(actual: dict, golden: dict) -> list[str]:
    errors: list[str] = []
    mod = actual["modelling"]
    gmod = golden["modelling"]
    if mod["node_count"] != gmod["node_count"]:
        errors.append(f"node_count {mod['node_count']} != {gmod['node_count']}")
    if mod["element_count"] != gmod["element_count"]:
        errors.append(f"element_count {mod['element_count']} != {gmod['element_count']}")

    eq = actual["equipment"]["assembly"]
    geq = golden["equipment"]["assembly"]
    if eq and geq:
        if abs(eq["mass_kg"] - geq["mass_kg"]) > 0.01:
            errors.append(f"assembly mass_kg {eq['mass_kg']} != {geq['mass_kg']}")

    loads = actual["modelling"]["loads"]
    gloads = golden["modelling"]["loads"]
    pret = next((l for l in loads if l["load_type"] == "bolt_pretension"), None)
    gpret = next((l for l in gloads if l["load_type"] == "bolt_pretension"), None)
    if pret and gpret:
        if pret["count"] != gpret["count"]:
            errors.append(f"bolt count {pret['count']} != {gpret['count']}")
        if abs(pret["magnitude"] - gpret["magnitude"]) > 0.01:
            errors.append(f"preload {pret['magnitude']} != {gpret['magnitude']}")

    mats = {m["name"]: m for m in actual["modelling"]["materials"]}
    gmats = {m["name"]: m for m in golden["modelling"]["materials"]}
    for name in ("ASTM 182 F 321", "Nylon"):
        if name in mats and name in gmats:
            if mats[name].get("youngs_modulus_gpa") != gmats[name].get("youngs_modulus_gpa"):
                errors.append(f"{name} E mismatch")
            if mats[name].get("density_kg_m3") != gmats[name].get("density_kg_m3"):
                errors.append(f"{name} density mismatch")

    if len(actual["modelling"]["contacts"]) != len(golden["modelling"]["contacts"]):
        errors.append("contact count mismatch")

    return errors


def _print_summary(payload: dict) -> None:
    mod = payload["modelling"]
    eq = payload["equipment"]
    print(f"BOM: {payload['bom_id']}")
    print(f"Mesh: {mod['node_count']} nodes, {mod['element_count']} elements ({mod['mesh_source']})")
    if eq.get("assembly"):
        print(f"Assembly mass: {eq['assembly']['mass_kg']} kg")
    print(f"Bodies: {len(eq['bodies'])}")
    print(f"Materials: {[m['name'] for m in mod['materials']]}")
    print(f"Contacts: {len(mod['contacts'])}")
    pret = next((l for l in mod["loads"] if l["load_type"] == "bolt_pretension"), None)
    if pret:
        print(f"Bolt pretension: {pret['magnitude']} N × {pret['count']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="EP2737 Phase 3 metadata spike")
    parser.add_argument("--write-golden", action="store_true")
    parser.add_argument("--no-compare", action="store_true")
    args = parser.parse_args()
    return run_metadata(write_golden=args.write_golden, compare=not args.no_compare)


if __name__ == "__main__":
    sys.exit(main())
