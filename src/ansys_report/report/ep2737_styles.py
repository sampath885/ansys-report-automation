"""EP2737 Word style shell — preserve reference DOCX styles/headers while clearing body."""

from __future__ import annotations

import copy
import io
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _extract_document_shell(doc_xml: str, *, prefer_portrait: bool = False) -> str:
    """Return document.xml with empty body preserving namespaces and sectPr."""
    root = ET.fromstring(doc_xml)
    body = root.find("w:body", NS)
    if body is None:
        return doc_xml

    sect_pr = _select_shell_sect_pr(body, prefer_portrait=prefer_portrait)
    new_body = ET.Element(f"{{{W_NS}}}body")
    if sect_pr is not None:
        new_body.append(sect_pr)

    for child in list(root):
        if child.tag == f"{{{W_NS}}}body":
            root.remove(child)
    root.append(new_body)

    ET.register_namespace("w", W_NS)
    ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    ET.register_namespace("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006")
    ET.register_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
    ET.register_namespace("w15", "http://schemas.microsoft.com/office/word/2012/wordml")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _select_shell_sect_pr(body: ET.Element, *, prefer_portrait: bool) -> ET.Element | None:
    candidates: list[ET.Element] = []
    for element in body:
        if element.tag == f"{{{W_NS}}}sectPr":
            candidates.append(element)
        if element.tag == f"{{{W_NS}}}p":
            ppr = element.find("w:pPr", NS)
            if ppr is not None:
                sect = ppr.find("w:sectPr", NS)
                if sect is not None:
                    candidates.append(sect)

    if not candidates:
        return None

    if prefer_portrait:
        for sect in candidates:
            pg = sect.find("w:pgSz", NS)
            if pg is None:
                continue
            width = pg.get(f"{{{W_NS}}}w")
            height = pg.get(f"{{{W_NS}}}h")
            if width and height and int(width) < int(height):
                return copy.deepcopy(sect)

    return copy.deepcopy(candidates[-1])


def create_style_shell(reference_docx: Path, output_path: Path) -> Path:
    """Copy reference DOCX and replace document body with portrait sectPr only."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(reference_docx, output_path)

    with zipfile.ZipFile(output_path, "r") as zin:
        doc_xml = zin.read("word/document.xml").decode("utf-8")

    new_doc = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + _extract_document_shell(
        doc_xml, prefer_portrait=True
    )

    buffer = output_path.read_bytes()
    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buffer), "r") as zin:
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    data = new_doc.encode("utf-8")
                zout.writestr(info, data)
    output_path.write_bytes(out_buf.getvalue())
    return output_path


def open_document_from_shell(shell_path: Path | None):
    """Open style shell; fall back to blank document if the shell is invalid."""
    from docx import Document

    if shell_path is not None and shell_path.exists():
        try:
            return Document(str(shell_path))
        except (KeyError, OSError, ValueError, Exception):
            pass
    return Document()
