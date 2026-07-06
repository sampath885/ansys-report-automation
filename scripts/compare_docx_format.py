"""Compare DOCX formatting (page size, styles, sample paragraphs)."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _attr(el: ET.Element | None, name: str) -> str | None:
    if el is None:
        return None
    return el.get(f"{{{W_NS}}}{name}")


def analyze(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        styles = z.read("word/styles.xml").decode("utf-8") if "word/styles.xml" in z.namelist() else ""

    root = ET.fromstring(doc)
    body = root.find(f"{W}body")
    sect = body.find(f"{W}sectPr") if body is not None else None
    pg = sect.find(f"{W}pgSz") if sect is not None else None
    pgmar = sect.find(f"{W}pgMar") if sect is not None else None

    info: dict = {"file": path.name}
    if pg is not None:
        info["page_w"] = _attr(pg, "w")
        info["page_h"] = _attr(pg, "h")
    if pgmar is not None:
        info["margins"] = {k.split("}")[-1]: v for k, v in pgmar.attrib.items()}

    paras = []
    for p in root.iter(f"{W}p"):
        texts = "".join(t.text or "" for t in p.iter(f"{W}t")).strip()
        if not texts:
            continue
        ppr = p.find(f"{W}pPr")
        style = _attr(ppr.find(f"{W}pStyle") if ppr is not None else None, "val")
        rpr = p.find(f".//{W}rPr")
        fonts: dict[str, str] = {}
        if rpr is not None:
            rf = rpr.find(f"{W}rFonts")
            if rf is not None:
                for a in ("ascii", "hAnsi", "cs"):
                    v = _attr(rf, a)
                    if v:
                        fonts[a] = v
            sz = rpr.find(f"{W}sz")
            if sz is not None:
                fonts["sz"] = _attr(sz, "val") or ""
        if any(
            texts.startswith(prefix)
            for prefix in ("Revision", "Scope", "Figure 1", "Details", "Equipment", "Modal")
        ):
            paras.append((texts[:70], style, fonts))

    info["sample_paras"] = paras[:12]

    style_samples = []
    if styles:
        sroot = ET.fromstring(styles)
        for st in sroot.findall(f"{W}style"):
            sid = _attr(st, "styleId") or ""
            name_el = st.find(f"{W}name")
            name = _attr(name_el, "val") or ""
            if sid in ("Heading1", "Heading2", "Heading3", "Caption", "Normal", "TableGrid") or name.lower() in (
                "heading 1",
                "heading 2",
                "heading 3",
                "caption",
                "normal",
            ):
                rpr = st.find(f"{W}rPr")
                fonts: dict[str, str] = {}
                if rpr is not None:
                    rf = rpr.find(f"{W}rFonts")
                    if rf is not None:
                        fonts["ascii"] = _attr(rf, "ascii") or ""
                    sz = rpr.find(f"{W}sz")
                    if sz is not None:
                        fonts["sz"] = _attr(sz, "val") or ""
                style_samples.append((sid, name, fonts))
    info["styles"] = style_samples
    return info


def find_marker_index(root: ET.Element, marker: str) -> int | None:
    paras = [p for p in root.iter(f"{W}p") if "".join(t.text or "" for t in p.iter(f"{W}t")).strip()]
    for idx, p in enumerate(paras):
        text = "".join(t.text or "" for t in p.iter(f"{W}t")).strip()
        if text == marker:
            return idx
    return None


def body_after_marker(path: Path, marker: str = "Revision Log") -> list[tuple[str, str | None, dict]]:
    with zipfile.ZipFile(path) as z:
        doc = z.read("word/document.xml").decode("utf-8")
    root = ET.fromstring(doc)
    paras = []
    for p in root.iter(f"{W}p"):
        texts = "".join(t.text or "" for t in p.iter(f"{W}t")).strip()
        if not texts:
            continue
        ppr = p.find(f"{W}pPr")
        style = _attr(ppr.find(f"{W}pStyle") if ppr is not None else None, "val")
        rpr = p.find(f".//{W}rPr")
        fonts: dict[str, str] = {}
        if rpr is not None:
            rf = rpr.find(f"{W}rFonts")
            if rf is not None:
                for a in ("ascii", "hAnsi", "cs"):
                    v = _attr(rf, a)
                    if v:
                        fonts[a] = v
            sz = rpr.find(f"{W}sz")
            if sz is not None:
                fonts["sz"] = _attr(sz, "val") or ""
            b = rpr.find(f"{W}b")
            if b is not None:
                fonts["bold"] = _attr(b, "val") or "1"
        paras.append((texts, style, fonts))

    start = None
    for i, (text, _, _) in enumerate(paras):
        if text == marker:
            start = i
            break
    if start is None:
        return paras[:30]
    return paras[start : start + 40]


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    marker = "Revision Log"
    for path in paths:
        i = analyze(path)
        print(f"=== {i['file']} ===")
        print(f"page: w={i.get('page_w')} h={i.get('page_h')}")
        print(f"margins: {i.get('margins')}")
        print("styles:")
        for row in i.get("styles", []):
            print(f"  {row}")
        print(f"body after {marker!r}:")
        for row in body_after_marker(path, marker):
            print(f"  {row}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
