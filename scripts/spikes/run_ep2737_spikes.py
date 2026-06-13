"""Phase 2 DPF spikes — extract and validate EP2737 result scalars."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CASE = REPO / "EP 2737"
WB = CASE / "Structural Analysis_EP2737" / "EP2737_files" / "dp0"
GOLDEN_DIR = REPO / "tests" / "fixtures" / "ep2737_golden"
YIELD_MPA = 170.0  # ASTM 182 F 321 static allowable order-of-magnitude
TOL_FREQ = 0.01  # Hz
TOL_STRESS = 0.5  # MPa
TOL_DISP = 0.01  # mm


def _rst(folder: str) -> Path:
    return WB / folder / "MECH" / "file.rst"


def spike_modal(num_modes: int = 6) -> dict:
    from ansys_report.extract.dpf_modal import extract_modal

    path = _rst("SYS-1")
    result = extract_modal(path, num_modes)
    return {
        "spike": "2a_modal",
        "rst": str(path.relative_to(REPO)),
        "modes": [m.model_dump() for m in result.modes],
        "manual_fields": result.manual_fields,
    }


def spike_static(load_step: int = 3) -> dict:
    from ansys_report.extract.dpf_static import extract_static

    path = _rst("SYS")
    result = extract_static(path, YIELD_MPA, load_step=load_step)
    return {
        "spike": "2b_static",
        "rst": str(path.relative_to(REPO)),
        "load_step": load_step,
        **result.model_dump(),
    }


def spike_harmonic_x() -> dict:
    from ansys_report.extract.dpf_harmonic import extract_harmonic_peak

    path = _rst("SYS-2")
    result = extract_harmonic_peak(path)
    return {
        "spike": "2c_harmonic_x",
        "rst": str(path.relative_to(REPO)),
        **result.model_dump(),
    }


def spike_shock_plus_x() -> dict:
    from ansys_report.extract.dpf_static import extract_static

    path = _rst("SYS-5")
    result = extract_static(path, YIELD_MPA, load_step=1)
    return {
        "spike": "2d_shock_plus_x",
        "rst": str(path.relative_to(REPO)),
        **result.model_dump(),
    }


def _compare_modal(actual: dict, golden: dict) -> list[str]:
    errors = []
    for a, g in zip(actual["modes"], golden["modes"], strict=False):
        if a.get("freq_hz") is None:
            errors.append(f"mode {a['index']}: missing frequency")
            continue
        if abs(a["freq_hz"] - g["freq_hz"]) > TOL_FREQ:
            errors.append(
                f"mode {a['index']}: {a['freq_hz']:.4f} Hz != golden {g['freq_hz']:.4f} Hz"
            )
    return errors


def _compare_static(actual: dict, golden: dict) -> list[str]:
    errors = []
    for key, tol in (("max_stress_mpa", TOL_STRESS), ("max_deformation_mm", TOL_DISP)):
        a, g = actual.get(key), golden.get(key)
        if a is None or g is None:
            errors.append(f"{key}: missing value")
        elif abs(a - g) > tol:
            errors.append(f"{key}: {a} != golden {g} (tol {tol})")
    return errors


def _compare_harmonic(actual: dict, golden: dict) -> list[str]:
    errors = []
    a, g = actual.get("peak_displacement_mm"), golden.get("peak_displacement_mm")
    if a is None or g is None:
        errors.append("peak_displacement_mm: missing")
    elif abs(a - g) > TOL_DISP:
        errors.append(f"peak_displacement_mm: {a} != golden {g}")
    return errors


def run_all(*, write_golden: bool = False, compare: bool = True) -> int:
    spikes = {
        "2a_modal.json": spike_modal(),
        "2b_static_step3.json": spike_static(),
        "2c_harmonic_x.json": spike_harmonic_x(),
        "2d_shock_plus_x.json": spike_shock_plus_x(),
    }

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    exit_code = 0

    for name, data in spikes.items():
        out_path = GOLDEN_DIR / name
        if write_golden:
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"Wrote {out_path}")
        else:
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(json.dumps(data, indent=2))

        if compare and not write_golden:
            golden_path = GOLDEN_DIR / name
            if not golden_path.exists():
                print(f"  [skip compare] no golden file {name}")
                continue
            golden = json.loads(golden_path.read_text(encoding="utf-8"))
            if "modal" in name:
                errs = _compare_modal(data, golden)
            elif "harmonic" in name:
                errs = _compare_harmonic(data, golden)
            else:
                errs = _compare_static(data, golden)
            if errs:
                exit_code = 1
                for e in errs:
                    print(f"  FAIL: {e}")
            else:
                print(f"  OK: matches golden {name}")

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="EP2737 Phase 2 DPF spikes")
    parser.add_argument(
        "--write-golden",
        action="store_true",
        help="Capture current DPF output as golden reference files",
    )
    parser.add_argument("--no-compare", action="store_true")
    args = parser.parse_args()
    code = run_all(write_golden=args.write_golden, compare=not args.no_compare)
    sys.exit(code)


if __name__ == "__main__":
    main()
