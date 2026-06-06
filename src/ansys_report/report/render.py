"""Render Word reports from template + context."""

from __future__ import annotations

import logging
from pathlib import Path

from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_NAME = "EP1763_report_template.docx"


def default_template_path() -> Path:
    return Path(__file__).resolve().parents[3] / "templates" / DEFAULT_TEMPLATE_NAME


def render_report(
    template_path: Path,
    context: dict,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tpl = DocxTemplate(str(template_path))
    tpl.render(context)
    tpl.save(str(output_path))
    logger.info("Wrote report: %s", output_path)
    return output_path
