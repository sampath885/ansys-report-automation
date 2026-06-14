"""Export front-matter tables from reference DOCX."""

from __future__ import annotations

from pathlib import Path

import yaml
from docx import Document

from ansys_report.ep2737_paths import ep2737_reference_docx

ROOT = Path(__file__).resolve().parents[1]
REF = ep2737_reference_docx()
OUT = ROOT / "config" / "ep2737_front_matter.yaml"


def _table(table, *, header_row: int = 0, data_start: int | None = None) -> dict:
    rows = [[c.text.strip() for c in r.cells] for r in table.rows]
    start = data_start if data_start is not None else header_row + 1
    return {
        "headers": rows[header_row],
        "rows": rows[start:],
    }


def export() -> dict:
    doc = Document(str(REF))
    return {
        "revision_log": {
            "caption": "Table 1: Revision Log",
            **_table(doc.tables[1]),
        },
        "scope_analysis": {
            "caption": "Table 3: Scope of Design Analysis",
            **_table(doc.tables[3], header_row=1, data_start=2),
        },
        "software_tools": {
            "caption": "Table 4: Software used",
            **_table(doc.tables[4]),
        },
        "references": {
            "caption": "Table 4: References",
            **_table(doc.tables[5]),
        },
        "static_flange_conclusion": {
            "caption": "Table 16: Static Structural Analysis Conclusion (flange)",
            "headers": [c.text.strip() for c in doc.tables[18].rows[0].cells],
            "rows": [[c.text.strip() for c in r.cells] for r in doc.tables[18].rows[1:]],
        },
    }


def main() -> int:
    OUT.write_text(yaml.safe_dump(export(), sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
