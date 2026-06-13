"""Repair DOCX packages so Microsoft Word desktop can open them."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

# python-docx / docxtpl often emit this legacy part; Word on Windows rejects it.
_STYLES_WITH_EFFECTS = "word/stylesWithEffects.xml"
_RELS_STYLES_WITH_EFFECTS = re.compile(
    r'<Relationship[^>]*stylesWithEffects[^>]*/>\s*',
    re.IGNORECASE,
)
_CT_STYLES_WITH_EFFECTS = re.compile(
    r'<Override PartName="/word/stylesWithEffects\.xml"[^>]*/>\s*',
    re.IGNORECASE,
)


def sanitize_docx_for_word(path: Path) -> None:
    """Remove OOXML parts that commonly break Microsoft Word."""
    source = path.read_bytes()
    buffer = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(source), "r") as zin:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename == _STYLES_WITH_EFFECTS:
                    continue
                data = zin.read(info.filename)
                if info.filename == "[Content_Types].xml":
                    data = _CT_STYLES_WITH_EFFECTS.sub("", data.decode("utf-8")).encode("utf-8")
                elif info.filename == "word/_rels/document.xml.rels":
                    data = _RELS_STYLES_WITH_EFFECTS.sub("", data.decode("utf-8")).encode("utf-8")
                zout.writestr(info, data)

    path.write_bytes(buffer.getvalue())
