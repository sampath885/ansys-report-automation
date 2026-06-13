"""Create bundled EP2737 layout template (cover, TOC, headers) from reference DOCX."""

from __future__ import annotations

import shutil
from pathlib import Path

from ansys_report.report.docx_sanitize import sanitize_docx_for_word

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "EP 2737" / "Design Report_EP2737_UPDATED.docx"
OUT = ROOT / "templates" / "EP2737_layout_template.docx"


def export_layout_template(
    reference_docx: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Copy reference report as reusable layout shell for new BOM jobs."""
    ref = reference_docx or REF
    out = output_path or OUT
    if not ref.exists():
        raise FileNotFoundError(f"Reference layout not found: {ref}")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ref, out)
    sanitize_docx_for_word(out)
    return out


def main() -> int:
    try:
        path = export_layout_template()
    except FileNotFoundError as exc:
        print(exc)
        return 1
    print(f"Wrote layout template: {path}")
    print("Point reference_layout_path at this file for new jobs (cover/TOC/headers only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
