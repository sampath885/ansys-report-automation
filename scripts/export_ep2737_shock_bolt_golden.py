"""Export shock bolt load tables from reference DOCX to golden JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document

from ansys_report.ep2737_paths import ep2737_reference_docx

ROOT = Path(__file__).resolve().parents[1]
REF = ep2737_reference_docx()
OUT = ROOT / "tests" / "fixtures" / "ep2737_golden" / "8_shock_bolt_loads.json"

# Reference table indices for Tables 17–22 (verified against DOCX structure)
DIRECTION_TABLE_INDEX = {
    "plus_x": 17,
    "plus_y": 20,
    "plus_z": 21,
    "minus_x": 22,
    "minus_y": 23,
    "minus_z": 24,
}


def _parse_bolt_table(table) -> list[dict]:
    rows: list[dict] = []
    if len(table.rows) < 3:
        return rows
    for row in table.rows[2:]:
        cells = [c.text.strip() for c in row.cells]
        if not cells or not cells[0].isdigit():
            continue
        axial = _float(cells[1])
        shear = _float(cells[2])
        tensile_area = _float(cells[3])
        shear_area = _float(cells[4])
        normal_stress = _float(cells[5]) if len(cells) > 5 else None
        shear_stress = _float(cells[6]) if len(cells) > 6 else None
        yield_mpa = _float(cells[7]) if len(cells) > 7 else 205.0
        conclusion = cells[-1] if cells else "Accepted"
        rows.append(
            {
                "bolt_no": int(cells[0]),
                "axial_force_n": axial,
                "shear_force_n": shear,
                "tensile_stress_area_mm2": tensile_area,
                "shear_stress_area_mm2": shear_area,
                "normal_stress_mpa": normal_stress,
                "shear_stress_mpa": shear_stress,
                "yield_stress_mpa": yield_mpa,
                "conclusion": conclusion,
            }
        )
    return rows


def _float(text: str) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def export_golden() -> dict:
    doc = Document(str(REF))
    payload: dict = {"phase": "8_shock_bolt_loads", "directions": {}}
    for key, idx in DIRECTION_TABLE_INDEX.items():
        payload["directions"][key] = _parse_bolt_table(doc.tables[idx])
    return payload


def main() -> int:
    data = export_golden()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({sum(len(v) for v in data['directions'].values())} bolt rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
