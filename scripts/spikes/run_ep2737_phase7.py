"""Phase 7 spikes — harmonic Y/Z, all shock directions, full build."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ansys_report.ep2737_paths import ep2737_dp0, ep2737_rst_relpath

REPO = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO / "tests" / "fixtures" / "ep2737_golden"
WB = ep2737_dp0()
YIELD_MPA = 170.0
TOL_DISP = 0.05
TOL_STRESS = 0.5


def _rst(folder: str) -> Path:
    return WB / folder / "MECH" / "file.rst"


def spike_harmonic(folder: str, spike_id: str) -> dict:
    from ansys_report.extract.dpf_harmonic import extract_harmonic_peak

    path = _rst(folder)
    result = extract_harmonic_peak(path)
    return {
        "spike": spike_id,
        "rst": ep2737_rst_relpath(path),
        **result.model_dump(),
    }


def spike_shock_all() -> dict:
    from ansys_report.extract.dpf_static import extract_static
    from ansys_report.sections.shock import SHOCK_DIRECTIONS

    directions = []
    for result_key, system_key, folder, label in SHOCK_DIRECTIONS:
        path = _rst(folder)
        static = extract_static(path, YIELD_MPA, load_step=1)
        directions.append(
            {
                "key": result_key,
                "system_key": system_key,
                "direction": label,
                "workbench_folder": folder,
                **static.model_dump(),
            }
        )
    return {"phase": "7_shock", "yield_mpa": YIELD_MPA, "directions": directions}


def _compare_harmonic(actual: dict, golden: dict) -> list[str]:
    errors = []
    a, g = actual.get("peak_displacement_mm"), golden.get("peak_displacement_mm")
    if a is None or g is None:
        errors.append("peak_displacement_mm missing")
    elif abs(a - g) > TOL_DISP:
        errors.append(f"peak_displacement_mm {a} != {g}")
    return errors


def _compare_shock(actual: dict, golden: dict) -> list[str]:
    errors = []
    for a, g in zip(actual["directions"], golden["directions"], strict=True):
        if abs(a["max_stress_mpa"] - g["max_stress_mpa"]) > TOL_STRESS:
            errors.append(f"{a['direction']} stress mismatch")
    return errors


def run_phase7(*, write_golden: bool = False, compare: bool = True) -> int:
    spikes = {
        "2e_harmonic_y.json": spike_harmonic("SYS-3", "2e_harmonic_y"),
        "2f_harmonic_z.json": spike_harmonic("SYS-4", "2f_harmonic_z"),
        "7_shock_all.json": spike_shock_all(),
    }

    exit_code = 0
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    for name, data in spikes.items():
        out = GOLDEN_DIR / name
        if write_golden:
            out.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"Wrote {out}")

        if compare and not write_golden:
            if not out.exists():
                print(f"FAIL: missing golden {name}")
                exit_code = 1
                continue
            golden = json.loads(out.read_text(encoding="utf-8"))
            if "harmonic" in name:
                errs = _compare_harmonic(data, golden)
            else:
                errs = _compare_shock(data, golden)
            if errs:
                exit_code = 1
                for e in errs:
                    print(f"FAIL {name}: {e}")
            else:
                print(f"OK: {name}")

    if not write_golden and compare and exit_code == 0:
        print("Phase 7 golden check: PASS")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="EP2737 Phase 7 DPF spikes")
    parser.add_argument("--write-golden", action="store_true")
    parser.add_argument("--no-compare", action="store_true")
    args = parser.parse_args()
    return run_phase7(write_golden=args.write_golden, compare=not args.no_compare)


if __name__ == "__main__":
    sys.exit(main())
