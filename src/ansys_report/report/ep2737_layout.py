"""Merge reference EP2737 front matter (cover, TOC, LOF, LOT) with generated body."""

from __future__ import annotations

import copy
import io
import logging
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
DEFAULT_CONTENT_START_MARKER = "Revision log"


def _body_children(root: ET.Element) -> list[ET.Element]:
    body = root.find("w:body", NS)
    if body is None:
        return []
    return list(body)


def _paragraph_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{{{W_NS}}}t")).strip()


def find_content_start_index(body_children: list[ET.Element], marker: str = DEFAULT_CONTENT_START_MARKER) -> int:
    """Index of first body paragraph equal to *marker* (e.g. 'Revision log')."""
    for index, element in enumerate(body_children):
        if element.tag != f"{{{W_NS}}}p":
            continue
        if _paragraph_text(element) == marker:
            return index
    raise ValueError(f"Content start marker {marker!r} not found in reference document body")


def _find_sect_pr_with_headers(body_children: list[ET.Element]) -> ET.Element | None:
    for element in body_children:
        for sect_pr in element.iter(f"{{{W_NS}}}sectPr"):
            if any("headerReference" in child.tag for child in sect_pr):
                return sect_pr
    return None


def _apply_header_footer_refs(target: ET.Element, source: ET.Element) -> None:
    """Copy header/footer (and page border) settings from reference section properties."""
    for child in list(target):
        if any(
            tag in child.tag
            for tag in ("headerReference", "footerReference", "titlePg", "pgBorders")
        ):
            target.remove(child)

    insert_at = 0
    for child in source:
        if any(
            tag in child.tag
            for tag in ("headerReference", "footerReference", "titlePg", "pgBorders")
        ):
            target.insert(insert_at, copy.deepcopy(child))
            insert_at += 1


def merge_reference_front_matter(
    reference_path: Path,
    generated_path: Path,
    output_path: Path,
    *,
    content_start_marker: str = DEFAULT_CONTENT_START_MARKER,
) -> Path:
    """Keep reference cover/TOC/LOF/LOT; append generated report body after them."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(reference_path, "r") as zref:
        ref_root = ET.fromstring(zref.read("word/document.xml"))
        ref_children = _body_children(ref_root)
        start = find_content_start_index(ref_children, content_start_marker)
        front_matter = [copy.deepcopy(el) for el in ref_children[:start]]
        sect_pr = copy.deepcopy(ref_children[-1]) if ref_children and ref_children[-1].tag == f"{{{W_NS}}}sectPr" else None
        if sect_pr is None:
            for el in ref_children:
                if el.tag == f"{{{W_NS}}}sectPr":
                    sect_pr = copy.deepcopy(el)
                    break
        header_sect_pr = _find_sect_pr_with_headers(ref_children)
        if sect_pr is not None and header_sect_pr is not None:
            _apply_header_footer_refs(sect_pr, header_sect_pr)

    with zipfile.ZipFile(generated_path, "r") as zgen:
        gen_root = ET.fromstring(zgen.read("word/document.xml"))
        generated = [
            copy.deepcopy(el)
            for el in _body_children(gen_root)
            if el.tag != f"{{{W_NS}}}sectPr"
        ]

    new_body = ET.Element(f"{{{W_NS}}}body")
    for element in front_matter:
        new_body.append(element)
    for element in generated:
        new_body.append(element)
    if sect_pr is not None:
        new_body.append(sect_pr)

    for old in list(ref_root):
        if old.tag == f"{{{W_NS}}}body":
            ref_root.remove(old)
    ref_root.append(new_body)

    ET.register_namespace("w", W_NS)
    ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    ET.register_namespace("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006")
    ET.register_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
    ET.register_namespace("w15", "http://schemas.microsoft.com/office/word/2012/wordml")
    new_doc_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(
        ref_root, encoding="unicode", xml_declaration=False
    )

    shutil.copy2(reference_path, output_path)
    buffer = output_path.read_bytes()
    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buffer), "r") as zin:
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    data = new_doc_xml.encode("utf-8")
                zout.writestr(info, data)
    output_path.write_bytes(out_buf.getvalue())
    logger.info(
        "Merged reference front matter (%d elements) with generated body (%d elements)",
        len(front_matter),
        len(generated),
    )
    return output_path
