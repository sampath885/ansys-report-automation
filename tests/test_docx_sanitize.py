"""DOCX sanitization tests."""

import zipfile

from ansys_report.report.docx_sanitize import sanitize_docx_for_word


def test_sanitize_removes_styles_with_effects(tmp_path):
    from docx import Document

    src = tmp_path / "raw.docx"
    out = tmp_path / "clean.docx"
    Document().save(str(src))
    out.write_bytes(src.read_bytes())
    sanitize_docx_for_word(out)

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "word/stylesWithEffects.xml" not in names
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        assert "stylesWithEffects" not in rels
        ct = z.read("[Content_Types].xml").decode("utf-8")
        assert "stylesWithEffects" not in ct
