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
_REL_ID_NUM = re.compile(r"rId(\d+)")


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


def _next_rel_id(used_ids: set[str]) -> str:
    nums = []
    for rel_id in used_ids:
        match = _REL_ID_NUM.match(rel_id or "")
        if match:
            nums.append(int(match.group(1)))
    return f"rId{max(nums or [0]) + 1}"


def _normalize_part_path(target: str) -> str:
    if target.startswith("/"):
        target = target.lstrip("/")
    if not target.startswith("word/"):
        target = f"word/{target}"
    return target


def _allocate_unique_media_path(target: str, occupied: set[str]) -> str:
    norm = _normalize_part_path(target)
    if norm not in occupied:
        return norm
    suffix = Path(norm).suffix or ".png"
    index = 1
    while True:
        candidate = f"word/media/gen_{index:04d}{suffix}"
        if candidate not in occupied:
            return candidate
        index += 1


def _replace_relationship_id(xml: str, old_id: str, new_id: str) -> str:
    """Replace one relationship id without corrupting longer ids (rId1 vs rId10)."""
    pattern = rf'r:(embed|link)="{re.escape(old_id)}"'
    return re.sub(pattern, rf'r:\1="{new_id}"', xml)


def _remap_generated_relationships(
    generated_xml: str,
    generated_rels: bytes,
    reference_rels: bytes,
    occupied_parts: set[str],
) -> tuple[str, bytes, dict[str, str]]:
    """
    Assign fresh relationship IDs (and media part names) for generated embeds.

    Reference front matter already owns many rIds and media parts; generated
    python-docx output typically reuses rId1/image1.png which would otherwise
    collide and break embedded figures after merge.
    """
    ref_root = ET.fromstring(reference_rels)
    used_ids = {rel.get("Id") for rel in ref_root if rel.tag == f"{{{REL_NS}}}Relationship"}

    gen_root = ET.fromstring(generated_rels)
    gen_by_id = {
        rel.get("Id"): rel
        for rel in gen_root
        if rel.tag == f"{{{REL_NS}}}Relationship"
    }

    needed = _collect_relationship_ids(generated_xml)
    remapped_xml = generated_xml
    id_map: dict[str, str] = {}

    for old_id in sorted(needed, key=lambda rid: int(_REL_ID_NUM.match(rid).group(1))):  # type: ignore[union-attr]
        rel = gen_by_id.get(old_id)
        if rel is None:
            continue

        new_id = _next_rel_id(used_ids)
        while new_id in used_ids:
            new_id = _next_rel_id(used_ids | {new_id})
        used_ids.add(new_id)
        id_map[old_id] = new_id

        new_rel = copy.deepcopy(rel)
        new_rel.set("Id", new_id)

        target = rel.get("Target") or ""
        if "media/" in target.lower():
            media_path = _allocate_unique_media_path(target, occupied_parts)
            occupied_parts.add(media_path)
            new_rel.set("Target", media_path.replace("word/", ""))
        ref_root.append(new_rel)

        remapped_xml = _replace_relationship_id(remapped_xml, old_id, new_id)

    merged_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        + ET.tostring(ref_root, encoding="unicode", xml_declaration=False)
    ).encode("utf-8")
    return remapped_xml, merged_rels, id_map


def _media_copy_plan(
    generated_rels: bytes,
    merged_rels: bytes,
    id_map: dict[str, str],
) -> list[tuple[str, str]]:
    """Map generated zip media path -> unique output media path."""
    gen_targets = _relationship_targets(ET.fromstring(generated_rels))
    merged_targets = _relationship_targets(ET.fromstring(merged_rels))

    plan: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for old_id, new_id in id_map.items():
        old_target = gen_targets.get(old_id)
        new_target = merged_targets.get(new_id)
        if not old_target or not new_target or "media/" not in old_target.lower():
            continue
        src = _normalize_part_path(old_target)
        dest = _normalize_part_path(new_target)
        key = (src, dest)
        if key in seen:
            continue
        seen.add(key)
        plan.append(key)
    return plan


def _write_merged_package(
    reference_path: Path,
    generated_path: Path,
    output_path: Path,
    document_xml: str,
    merged_rels: bytes,
    media_plan: list[tuple[str, str]],
) -> None:
    """Write reference DOCX shell with merged body and generated embedded media."""
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(reference_path, "r") as zin:
        for info in zin.infolist():
            entries[info.filename] = zin.read(info.filename)

    entries["word/document.xml"] = document_xml.encode("utf-8")
    entries["word/_rels/document.xml.rels"] = merged_rels

    with zipfile.ZipFile(generated_path, "r") as zgen:
        for src, dest in media_plan:
            if src in zgen.namelist():
                entries[dest] = zgen.read(src)

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
        ref_rels = zref.read("word/_rels/document.xml.rels")

    occupied_parts = {name for name in zipfile.ZipFile(reference_path).namelist() if name.startswith("word/")}

    with zipfile.ZipFile(generated_path, "r") as zgen:
        gen_xml = zgen.read("word/document.xml").decode("utf-8")
        gen_rels = zgen.read("word/_rels/document.xml.rels")
        remapped_gen_xml, merged_rels, id_map = _remap_generated_relationships(
            gen_xml, gen_rels, ref_rels, occupied_parts
        )
        media_plan = _media_copy_plan(gen_rels, merged_rels, id_map)

        gen_root = ET.fromstring(remapped_gen_xml)
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
    ET.register_namespace("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
    ET.register_namespace("a", "http://schemas.openxmlformats.org/drawingml/2006/main")
    ET.register_namespace("pic", "http://schemas.openxmlformats.org/drawingml/2006/picture")
    new_doc_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(
        ref_root, encoding="unicode", xml_declaration=False
    )

    _write_merged_package(
        reference_path,
        generated_path,
        output_path,
        new_doc_xml,
        merged_rels,
        media_plan,
    )
    logger.info(
        "Merged reference front matter (%d elements) with generated body (%d elements, %d media)",
        len(front_matter),
        len(generated),
        len(media_plan),
    )
    return output_path
