"""Build EP1581 Word reports via section content spec + block renderer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ansys_report.config import ProjectConfig
from ansys_report.ep1581_paths import ep1581_layout_template, ep1581_style_shell
from ansys_report.report.block_assembler import assemble_report_document, validate_assembled_document
from ansys_report.report.block_render import render_blocks_document
from ansys_report.report.section_spec import load_section_content_spec
from ansys_report.report.table_builders import enrich_context_tables

logger = logging.getLogger(__name__)


def render_ep1581_report(
    context: dict[str, Any],
    output_path: Path,
    cfg: ProjectConfig,
) -> Path:
    """Render EP1581-format report from section content matrix and build context."""
    enrich_context_tables(context, cfg)
    spec = load_section_content_spec(cfg.section_content_path)
    doc_model = assemble_report_document(context, cfg, spec=spec)
    warnings = validate_assembled_document(doc_model)
    for w in warnings:
        logger.debug("Block assembly: %s", w)

    use_reference_layout = cfg.use_reference_front_matter and _resolve_reference_layout(cfg) is not None
    marker = spec.content_start_marker or cfg.content_start_marker or "Revision Log"

    return render_blocks_document(
        doc_model,
        context,
        output_path,
        style_shell_path=_resolve_style_shell(cfg),
        skip_cover=use_reference_layout,
        reference_layout_path=_resolve_reference_layout(cfg) if use_reference_layout else None,
        content_start_marker=marker,
        layout=cfg.layout or spec.layout or "ep1581",
    )


def _resolve_reference_layout(cfg: ProjectConfig) -> Path | None:
    path = getattr(cfg, "reference_layout_path", None)
    if path is not None and Path(path).exists():
        return Path(path)
    default = ep1581_layout_template()
    return default if default.exists() else None


def _resolve_style_shell(cfg: ProjectConfig) -> Path | None:
    shell = getattr(cfg, "style_shell_path", None)
    if shell is not None and Path(shell).exists():
        return Path(shell)
    default = ep1581_style_shell()
    return default if default.exists() else None
