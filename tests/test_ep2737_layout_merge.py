"""Tests for EP2737 layout merge preserving embedded figures."""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

from docx import Document
from docx.shared import Inches

from ansys_report.report.ep2737_layout import merge_reference_front_matter

REPO = Path(__file__).resolve().parents[1]
LAYOUT = REPO / "templates" / "EP2737_layout_template.docx"


def _embed_ids_and_missing_rels(docx_path: Path) -> tuple[int, int, int]:
    with zipfile.ZipFile(docx_path, "r") as z:
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        doc = z.read("word/document.xml").decode("utf-8")
    rel_ids = set(re.findall(r'Id="(rId\d+)"', rels))
    embed_ids = re.findall(r'r:embed="(rId\d+)"', doc)
    unique = set(embed_ids)
    return len(embed_ids), len(unique), len(unique - rel_ids)


def test_layout_merge_preserves_generated_image_relationships(tiny_png):
    assert LAYOUT.exists()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        generated = tmp_path / "generated.docx"
        output = tmp_path / "merged.docx"

        doc = Document()
        doc.add_heading("Revision log", level=1)
        doc.add_paragraph("Generated body")
        doc.add_picture(str(tiny_png), width=Inches(2))
        doc.save(generated)

        merge_reference_front_matter(LAYOUT, generated, output)

        embeds, _, missing = _embed_ids_and_missing_rels(output)
        assert embeds >= 1
        assert missing == 0


def test_layout_merge_preserves_multiple_generated_images(tiny_png):
    assert LAYOUT.exists()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        generated = tmp_path / "generated.docx"
        output = tmp_path / "merged.docx"

        doc = Document()
        doc.add_heading("Revision log", level=1)
        for idx in range(5):
            doc.add_paragraph(f"Figure block {idx}")
            doc.add_picture(str(tiny_png), width=Inches(2))
        doc.save(generated)

        merge_reference_front_matter(LAYOUT, generated, output)

        embeds, _, missing = _embed_ids_and_missing_rels(output)
        assert embeds >= 5
        assert missing == 0
        with zipfile.ZipFile(output) as zout:
            doc = zout.read("word/document.xml").decode("utf-8")
        assert doc.count("pic:pic") >= 5
