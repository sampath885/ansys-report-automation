"""Create minimal EP1763-style docxtpl templates."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Pt


def create_minimal_template_from_scratch(dest: Path) -> Path:
    """Build a minimal Jinja2 Word template when no sample docx is available."""
    doc = Document()
    _add_cover(doc)
    _add_section(doc, "Revision Log", "{{ sections.revision.body }}")
    _add_section(doc, "Scope", "{{ sections.scope.body }}")
    _add_section(doc, "Software and Tools", "ANSYS {{ ansys_version }}")
    _add_modal_section(doc)
    _add_static_section(doc)
    _add_design_calcs_section(doc)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(dest))
    return dest


def create_minimal_template(source: Path, dest: Path) -> Path:
    """Copy sample docx and inject placeholder paragraphs (best-effort)."""
    try:
        from docxtpl import DocxTemplate

        tpl = DocxTemplate(str(source))
        tpl.save(str(dest))
        doc = Document(str(dest))
        doc.add_page_break()
        doc.add_heading("Automated Sections", level=1)
        doc.add_paragraph("BOM: {{ bom_id }} — {{ title }}")
        doc.save(str(dest))
        return dest
    except Exception:
        return create_minimal_template_from_scratch(dest)


def _add_cover(doc: Document) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run("{{ bom_id }}\n")
    run.bold = True
    run.font.size = Pt(16)
    p.add_run("{{ title }}\n")
    doc.add_paragraph("Customer: {{ customer }}")
    doc.add_paragraph(
        "Prepared by: {{ prepared_by.name }} ({{ prepared_by.role }}) | "
        "Checked by: {{ checked_by.name }} | Approved by: {{ approved_by.name }}"
    )
    doc.add_page_break()


def _add_section(doc: Document, heading: str, body_placeholder: str) -> None:
    doc.add_heading(heading, level=1)
    doc.add_paragraph(body_placeholder)


def _add_modal_section(doc: Document) -> None:
    doc.add_heading("Modal Analysis", level=1)
    doc.add_paragraph("{% for mode in modal.modes %}")
    doc.add_paragraph("Mode {{ mode.index }}: {{ mode.freq_hz }} Hz")
    doc.add_paragraph("{% endfor %}")
    doc.add_paragraph("{% for obs in modal.narrative.observations %}{{ obs }}{% endfor %}")
    doc.add_paragraph("{% for c in modal.narrative.conclusions %}{{ c }}{% endfor %}")


def _add_static_section(doc: Document) -> None:
    doc.add_heading("Static Structural", level=1)
    doc.add_paragraph("Max von-Mises stress: {{ static.max_stress_mpa }} MPa")
    doc.add_paragraph("Max deformation: {{ static.max_deformation_mm }} mm")
    doc.add_paragraph("FOS: {{ static.fos }}")
    doc.add_paragraph("{% for obs in static.narrative.observations %}{{ obs }}{% endfor %}")


def _add_design_calcs_section(doc: Document) -> None:
    doc.add_heading("Design Calculations", level=1)
    doc.add_paragraph("{% for row in design_calcs.bolt_load %}")
    doc.add_paragraph("{{ row.label }} | {{ row.value }} {{ row.unit }} | {{ row.verdict }}")
    doc.add_paragraph("{% endfor %}")
    doc.add_paragraph("Executive summary: {{ narrative.executive_summary }}")
