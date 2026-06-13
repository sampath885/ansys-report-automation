"""Debug Word compatibility for docxtpl rendering."""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate

from ansys_report.config import load_project_config
from ansys_report.excel.reader import read_design_calcs
from ansys_report.report.docx_sanitize import sanitize_docx_for_word


def word_open_ok(path: Path) -> bool:
    import win32com.client

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(str(path.resolve()))
        doc.Close(False)
        return True
    except Exception:
        return False
    finally:
        word.Quit()


def main() -> None:
    cfg = load_project_config(Path("config/project.ep2737.yaml"))
    case = cfg.case_root or cfg.project_dir
    calcs = read_design_calcs(
        cfg.excel_path,
        excel_map_path=cfg.excel_map_path,
        case_root=case,
    )
    rows = [r.model_dump() for r in calcs.end_flange]
    ctx = {"design_calcs": {"end_flange": rows}}

    # Table row template (docxtpl {% tr %} syntax)
    doc = Document()
    table = doc.add_table(rows=2, cols=3)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Parameter"
    table.rows[0].cells[1].text = "Value"
    table.rows[0].cells[2].text = "Unit"
    row = table.rows[1].cells
    row[0].text = "{% tr for r in design_calcs.end_flange %}{{ r.label }}"
    row[1].text = "{{ r.value }}"
    row[2].text = "{{ r.unit or '' }}{% endtr %}"

    tpl_path = Path("output/test_table_tpl.docx")
    doc.save(str(tpl_path))
    sanitize_docx_for_word(tpl_path)

    out = Path("output/test_table_render.docx")
    tpl = DocxTemplate(str(tpl_path))
    tpl.render(ctx)
    tpl.save(str(out))
    sanitize_docx_for_word(out)
    print("table 44 rows:", "OK" if word_open_ok(out) else "FAIL")


if __name__ == "__main__":
    main()
