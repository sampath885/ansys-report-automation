"""Tests for EP2737 layout merge preserving embedded figures."""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

from docx import Document
from docx.shared import Inches

from ansys_report.report.ep2737_layout import (
    _replace_relationship_id,
    merge_reference_front_matter,
)

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


def test_replace_relationship_id_does_not_corrupt_longer_ids():
    xml = (
        '<p r:embed="rId1"/> middle '
        '<p r:embed="rId10"/> '
        '<p r:embed="rId11"/> '
        '<p r:link="rId2"/> '
        '<p r:link="rId20"/>'
    )
    out = _replace_relationship_id(xml, "rId1", "rId500")
    assert 'r:embed="rId500"' in out
    assert 'r:embed="rId10"' in out
    assert 'r:embed="rId11"' in out
    assert 'r:embed="rId1"' not in out

    out2 = _replace_relationship_id(out, "rId2", "rId501")
    assert 'r:link="rId501"' in out2
    assert 'r:link="rId20"' in out2
    assert 'r:link="rId2"' not in out2


def test_layout_merge_preserves_fifteen_distinct_images(tmp_path, tiny_png):
    """Regression: ascending str.replace turned rId10 into rId500 after remapping rId1."""
    assert LAYOUT.exists()

    pngs: list[Path] = []
    for idx in range(15):
        path = tmp_path / f"fig_{idx:02d}.png"
        path.write_bytes(tiny_png.read_bytes() + bytes([idx]))
        pngs.append(path)

    generated = tmp_path / "generated.docx"
    output = tmp_path / "merged.docx"

    doc = Document()
    doc.add_heading("Revision log", level=1)
    for idx, png in enumerate(pngs):
        doc.add_paragraph(f"Figure block {idx}")
        doc.add_picture(str(png), width=Inches(2))
    doc.save(generated)

    def _ordered_media_hashes(docx_path: Path) -> list[bytes]:
        with zipfile.ZipFile(docx_path, "r") as z:
            doc_xml = z.read("word/document.xml").decode("utf-8")
            rels_xml = z.read("word/_rels/document.xml.rels").decode("utf-8")
        embed_ids = re.findall(r'r:embed="(rId\d+)"', doc_xml)
        targets = dict(re.findall(r'Id="(rId\d+)"[^>]+Target="([^"]+)"', rels_xml))
        hashes: list[bytes] = []
        with zipfile.ZipFile(docx_path, "r") as z:
            for embed_id in embed_ids:
                target = targets.get(embed_id)
                if not target:
                    continue
                part = target if target.startswith("word/") else f"word/{target.lstrip('/')}"
                if part in z.namelist():
                    hashes.append(z.read(part))
        return hashes

    expected = _ordered_media_hashes(generated)
    assert len(expected) >= 15

    merge_reference_front_matter(LAYOUT, generated, output)

    embeds, _, missing = _embed_ids_and_missing_rels(output)
    assert embeds >= 15
    assert missing == 0

    with zipfile.ZipFile(output, "r") as zout:
        doc_xml = zout.read("word/document.xml").decode("utf-8")
    assert "rId500" not in doc_xml
    assert "rId505" not in doc_xml

    # Body embeds (after merge) must keep the same image sequence as the generated doc.
    merged_hashes = _ordered_media_hashes(output)
    body_start = len(merged_hashes) - len(expected)
    assert body_start >= 0
    assert merged_hashes[body_start:] == expected
