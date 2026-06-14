"""Merge reference EP2737 front matter (cover, TOC, LOF, LOT) with generated body."""

from __future__ import annotations

import copy
import io
import logging
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
DEFAULT_CONTENT_START_MARKER = "Revision log"


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _collect_relationship_ids(document_xml: str) -> set[str]:
    return set(re.findall(r'r:(?:embed|link)="(rId\d+)"', document_xml))


def _relationship_targets(root: ET.Element) -> dict[str, str]:
    targets: dict[str, str] = {}
    for rel in root:
        if rel.tag != f"{{{REL_NS}}}Relationship":
            continue
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if rel_id and target:
            targets[rel_id] = target
    return targets


def _merge_document_relationships(
    reference_rels: bytes,
    generated_rels: bytes,
    document_xml: str,
) -> bytes:
    """Keep reference rels and append generated image/media rels referenced by *document_xml*."""
    needed = _collect_relationship_ids(document_xml)
    ref_root = ET.fromstring(reference_rels)
    ref_ids = {rel.get("Id") for rel in ref_root if rel.tag == f"{{{REL_NS}}}Relationship"}

    gen_root = ET.fromstring(generated_rels)
    for rel in gen_root:
        if rel.tag != f"{{{REL_NS}}}Relationship":
            continue
        rel_id = rel.get("Id")
        if rel_id in needed and rel_id not in ref_ids:
            ref_root.append(copy.deepcopy(rel))
            ref_ids.add(rel_id)

    xml = ET.tostring(ref_root, encoding="unicode", xml_declaration=False)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + xml).encode("utf-8")


def _media_paths_for_relationships(rels_xml: bytes, rel_ids: set[str]) -> set[str]:
    root = ET.fromstring(rels_xml)
    targets = _relationship_targets(root)
    paths: set[str] = set()
    for rel_id in rel_ids:
        target = targets.get(rel_id)
        if not target:
            continue
        if target.startswith("/"):
            target = target.lstrip("/")
        if not target.startswith("word/"):
            target = f"word/{target}"
        paths.add(target)
    return paths


def _write_merged_package(
    reference_path: Path,
    generated_path: Path,
    output_path: Path,
    document_xml: str,
) -> None:
    """Write reference DOCX shell with merged body and generated embedded media."""
    needed_ids = _collect_relationship_ids(document_xml)

    with zipfile.ZipFile(reference_path, "r") as zref:
        ref_rels = zref.read("word/_rels/document.xml.rels")

    with zipfile.ZipFile(generated_path, "r") as zgen:
        gen_rels = zgen.read("word/_rels/document.xml.rels")
        merged_rels = _merge_document_relationships(ref_rels, gen_rels, document_xml)
        media_paths = _media_paths_for_relationships(gen_rels, needed_ids)

        entries: dict[str, bytes] = {}
        with zipfile.ZipFile(reference_path, "r") as zin:
            for info in zin.infolist():
                entries[info.filename] = zin.read(info.filename)

        entries["word/document.xml"] = document_xml.encode("utf-8")
        entries["word/_rels/document.xml.rels"] = merged_rels
        for media_path in media_paths:
            if media_path in zgen.namelist():
                entries[media_path] = zgen.read(media_path)

        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in entries.items():
                zout.writestr(name, data)

    output_path.write_bytes(out_buf.getvalue())


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

    _write_merged_package(reference_path, generated_path, output_path, new_doc_xml)
    logger.info(
        "Merged reference front matter (%d elements) with generated body (%d elements)",
        len(front_matter),
        len(generated),
    )
    return output_path
