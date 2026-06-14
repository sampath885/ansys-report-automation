"""Fast table export from reference DOCX via zipfile XML (avoids slow python-docx load)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ansys_report.ep2737_paths import ep2737_reference_docx

ROOT = Path(__file__).resolve().parents[1]
REF = ep2737_reference_docx()
REF_TABLES_OUT = ROOT / "config" / "ep2737_reference_tables.yaml"
STATIC_BOLT_OUT = ROOT / "tests" / "fixtures" / "ep2737_golden" / "7_static_bolt_loads.json"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _text_in(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter(f"{{{W_NS}}}t"):
        if node.text:
            parts.append(node.text)
        if node.tail:
            parts.append(node.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _table_rows(table_el: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table_el.findall("w:tr", NS):
        cells = [_text_in(tc) for tc in tr.findall("w:tc", NS)]
        rows.append(cells)
    return rows


def load_all_tables(docx_path: Path) -> list[list[list[str]]]:
    with zipfile.ZipFile(docx_path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    return [_table_rows(tbl) for tbl in root.findall(".//w:tbl", NS)]


def _table_dict(caption: str, rows: list[list[str]], *, header_row: int = 0, data_start: int | None = None) -> dict:
    if not rows:
        return {"caption": caption, "headers": [], "rows": []}
    start = data_start if data_start is not None else header_row + 1
    return {
        "caption": caption,
        "headers": rows[header_row],
        "rows": rows[start:],
    }


def _parse_bolt_rows(rows: list[list[str]], *, data_start: int = 2) -> list[dict]:
    out: list[dict] = []
    for cells in rows[data_start:]:
        if not cells or not cells[0].isdigit():
            continue
        out.append(
            {
                "bolt_no": int(cells[0]),
                "axial_force_n": _float(cells[1]),
                "shear_force_n": _float(cells[2]),
                "tensile_stress_area_mm2": _float(cells[3]) if len(cells) > 3 else None,
                "shear_stress_area_mm2": _float(cells[4]) if len(cells) > 4 else None,
                "normal_stress_mpa": _float(cells[5]) if len(cells) > 5 else None,
                "shear_stress_mpa": _float(cells[6]) if len(cells) > 6 else None,
                "yield_stress_mpa": _float(cells[7]) if len(cells) > 7 else 205.0,
                "conclusion": cells[-1] if cells else "Accepted",
            }
        )
    return out


def _float(text: str) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def export_reference_tables(tables: list[list[list[str]]]) -> dict:
    return {
        "design_changes": _table_dict(
            "Table 2: Current Design changes comparison Table w.r.t previous reference design/ drawing of NTD-117-96.",
            tables[2],
            header_row=0,
            data_start=1,
        ),
        "mass_balance_reference": _table_dict(
            "Table 5: Mass Balance",
            tables[7],
            header_row=0,
            data_start=1,
        ),
        "centre_of_gravity": _table_dict(
            "Table 6: Centre of gravity",
            tables[8],
            header_row=0,
            data_start=0,
        ),
        "technical_specifications": _table_dict(
            "Table 7: Technical Specifications",
            tables[9],
            header_row=0,
            data_start=1,
        ),
        "mesh_control_reference": _table_dict(
            "Table 8: Mesh Control",
            tables[10],
            header_row=0,
            data_start=1,
        ),
        "mesh_quality": _table_dict(
            "Table 9: Mesh Quality",
            tables[11],
            header_row=0,
            data_start=1,
        ),
        "material_properties_modelling": _table_dict(
            "Table 10: Material Properties",
            tables[12],
            header_row=0,
            data_start=1,
        ),
        "shock_pulse_specifications": _table_dict(
            "Table 11: Shock Pulse Specifications",
            tables[13],
            header_row=0,
            data_start=1,
        ),
        "material_properties_results": _table_dict(
            "Table 12: Material Properties",
            tables[14],
            header_row=0,
            data_start=1,
        ),
        "material_allowable_strength": _table_dict(
            "Table 13: Material allowable strength – Static and Fatigue",
            tables[15],
            header_row=0,
            data_start=1,
        ),
        "static_bolt_loads_reference": _table_dict(
            "Table 15: Bolt Loads for Static Structural Analysis",
            tables[17],
            header_row=0,
            data_start=2,
        ),
        "surface_finish_factors": _table_dict(
            "Table 28: Surface Finish Factors",
            tables[31],
            header_row=1,
            data_start=2,
        ),
        "reliability_factors": _table_dict(
            "Table 29: Reliability Factors",
            tables[32],
            header_row=0,
            data_start=1,
        ),
    }


def export_static_bolt_golden(tables: list[list[list[str]]]) -> dict:
    return {
        "phase": "9_static_bolt_loads",
        "bolt_loads": _parse_bolt_rows(tables[17]),
    }


def main() -> int:
    import json

    import yaml

    print(f"Reading tables from {REF} …")
    tables = load_all_tables(REF)
    print(f"  Found {len(tables)} tables")

    ref_data = export_reference_tables(tables)
    REF_TABLES_OUT.write_text(
        yaml.safe_dump(ref_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"Wrote {REF_TABLES_OUT}")

    static = export_static_bolt_golden(tables)
    STATIC_BOLT_OUT.parent.mkdir(parents=True, exist_ok=True)
    STATIC_BOLT_OUT.write_text(json.dumps(static, indent=2), encoding="utf-8")
    print(f"Wrote {STATIC_BOLT_OUT} ({len(static['bolt_loads'])} bolts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
