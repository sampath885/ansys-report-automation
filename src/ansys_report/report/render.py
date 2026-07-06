"""Render Word reports from template + context."""

from __future__ import annotations

import logging
from pathlib import Path

from docxtpl import DocxTemplate

from ansys_report.config import ProjectConfig
from ansys_report.report.docx_sanitize import sanitize_docx_for_word

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_NAME = "EP1763_report_template.docx"
EP2737_TEMPLATE_NAME = "EP2737_report_template.docx"


def default_template_path() -> Path:
    return Path(__file__).resolve().parents[3] / "templates" / DEFAULT_TEMPLATE_NAME


def ep2737_template_path() -> Path:
    return Path(__file__).resolve().parents[3] / "templates" / EP2737_TEMPLATE_NAME


def render_report(
    template_path: Path,
    context: dict,
    output_path: Path,
    *,
    native_ep2737: bool = False,
    cfg: ProjectConfig | None = None,
) -> Path:
    layout = (cfg.layout if cfg else "").lower()
    if layout == "ep1581" and cfg is not None:
        from ansys_report.report.ep1581_render import render_ep1581_report

        return render_ep1581_report(context, output_path, cfg)

    if native_ep2737 or "EP2737" in template_path.name.upper():
        from ansys_report.report.ep2737_render import render_ep2737_report

        return render_ep2737_report(context, output_path, cfg=cfg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tpl = DocxTemplate(str(template_path))
    tpl.render(context)
    tpl.save(str(output_path))
    sanitize_docx_for_word(output_path)
    logger.info("Wrote report: %s", output_path)
    return output_path
