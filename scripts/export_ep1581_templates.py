"""Create EP1581 layout template and style shell from reference DOCX."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ansys_report.ep1581_paths import ep1581_layout_template, ep1581_reference_docx, ep1581_style_shell
from ansys_report.report.docx_sanitize import sanitize_docx_for_word
from ansys_report.report.ep2737_styles import create_style_shell


def export_layout_template(
    reference_docx: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    ref = reference_docx or ep1581_reference_docx()
    out = output_path or ep1581_layout_template()
    if not ref.exists():
        raise FileNotFoundError(f"EP1581 reference not found: {ref}")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ref, out)
    sanitize_docx_for_word(out)
    return out


def export_style_shell(
    reference_docx: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    ref = reference_docx or ep1581_reference_docx()
    out = output_path or ep1581_style_shell()
    if not ref.exists():
        raise FileNotFoundError(f"EP1581 reference not found: {ref}")
    return create_style_shell(ref, out)


def main() -> int:
    ref = ep1581_reference_docx()
    source_dir = ROOT / "templates" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    bundled = source_dir / "EP1581_reference.docx"
    if ref.exists() and ref.resolve() != bundled.resolve():
        shutil.copy2(ref, bundled)
        print(f"Bundled reference: {bundled}")

    try:
        layout = export_layout_template(reference_docx=bundled if bundled.exists() else ref)
        shell = export_style_shell(reference_docx=bundled if bundled.exists() else ref)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    print(f"Wrote layout template: {layout}")
    print(f"Wrote style shell: {shell}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
