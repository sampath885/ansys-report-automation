#!/usr/bin/env python3
"""Debug: map DOCX embedded images to source export folders."""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def main() -> int:
    docx = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "automated_scripts_output" / "EP_2741_report.docx"
    exports = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(r"C:\Users\HP\AppData\Local\Temp\exports")

    with zipfile.ZipFile(docx) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        rid_to_media = dict(re.findall(r'Id="(rId\d+)".*?Target="([^"]+)"', rels))

    markers = [
        "Figure 35 - Static Structural Analysis: Boundary Conditions",
        "Figure - Harmonic Response X: Boundary Conditions",
        "Equivalent Static Analysis in +X Direction",
        "Equivalent Static Analysis in -X Direction",
        "Equivalent Static Analysis in -X: Boundary Conditions",
    ]
    for key in markers:
        idx = xml.find(key)
        print(f"\n=== {key} ===")
        if idx < 0:
            print("NOT FOUND")
            continue
        chunk = xml[idx : idx + 2500]
        names = re.findall(r'name="([^"]+\.png)"', chunk)
        rids = re.findall(r'r:embed="(rId\d+)"', chunk)
        print("embedded names:", names[:5])
        for rid in rids[:3]:
            media = rid_to_media.get(rid, "?")
            print(f"  {rid} -> {media}")

    print("\n=== SHOCK HEADINGS (images?) ===")
    for m in re.finditer(r"Equivalent Static Analysis in ([+-][XYZ]) Direction", xml):
        direction = m.group(1)
        start = m.start()
        chunk = xml[start : start + 1200]
        has_img = "w:drawing" in chunk
        names = re.findall(r'name="([^"]+\.png)"', chunk)
        print(f"{direction}: has_image={has_img} files={names[:2]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
