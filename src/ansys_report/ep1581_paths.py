"""EP1581 reference report paths."""

from __future__ import annotations

import os
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_REFERENCE = _REPO / "templates" / "source" / "EP1581_reference.docx"


def ep1581_reference_docx() -> Path:
    override = os.getenv("EP1581_REFERENCE_DOCX")
    if override:
        return Path(override).expanduser().resolve()
    downloads = Path.home() / "Downloads" / "EP1581_29APR_R0 (1).docx"
    if downloads.exists():
        return downloads.resolve()
    return _DEFAULT_REFERENCE.resolve()


def ep1581_layout_template() -> Path:
    return _REPO / "templates" / "EP1581_layout_template.docx"


def ep1581_style_shell() -> Path:
    return _REPO / "templates" / "EP1581_style_shell.docx"
