"""Create EP2737 style shell from reference DOCX (one-time, preserves headers/styles)."""

from __future__ import annotations

from pathlib import Path

from ansys_report.report.docx_sanitize import sanitize_docx_for_word
from ansys_report.report.ep2737_styles import create_style_shell

from ansys_report.ep2737_paths import ep2737_reference_docx

ROOT = Path(__file__).resolve().parents[1]
REF = ep2737_reference_docx()
OUT = ROOT / "templates" / "EP2737_style_shell.docx"


def main() -> int:
    if not REF.exists():
        print(f"Reference not found: {REF}")
        return 1
    create_style_shell(REF, OUT)
    sanitize_docx_for_word(OUT)
    print(f"Wrote style shell: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
