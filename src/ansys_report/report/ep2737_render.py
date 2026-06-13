"""Build EP2737 Word reports via section content spec + block renderer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ansys_report.config import ProjectConfig, load_project_config
from ansys_report.report.block_assembler import assemble_ep2737_document, validate_assembled_document
from ansys_report.report.block_render import render_blocks_document
from ansys_report.report.table_builders import enrich_context_tables

logger = logging.getLogger(__name__)


def render_ep2737_report(
    context: dict[str, Any],
    output_path: Path,
    cfg: ProjectConfig | None = None,
) -> Path:
    """Render EP2737 report from section content matrix and build context."""
    if cfg is None:
        cfg = load_project_config(
            Path(__file__).resolve().parents[3] / "config" / "project.ep2737.yaml"
        )

    enrich_context_tables(context, cfg)
    doc_model = assemble_ep2737_document(context, cfg, spec_path=cfg.section_content_path)
    warnings = validate_assembled_document(doc_model)
    for w in warnings:
        logger.debug("Block assembly: %s", w)

    use_reference_layout = cfg.use_reference_front_matter and _resolve_reference_layout(cfg) is not None

    return render_blocks_document(
        doc_model,
        context,
        output_path,
        style_shell_path=_resolve_style_shell(cfg),
        skip_cover=use_reference_layout,
        reference_layout_path=_resolve_reference_layout(cfg) if use_reference_layout else None,
    )


def _resolve_reference_layout(cfg: ProjectConfig) -> Path | None:
    path = getattr(cfg, "reference_layout_path", None)
    if path is not None and Path(path).exists():
        return Path(path)
    default = Path(__file__).resolve().parents[3] / "EP 2737" / "Design Report_EP2737_UPDATED.docx"
    return default if default.exists() else None


def _resolve_style_shell(cfg: ProjectConfig) -> Path | None:
    shell = getattr(cfg, "style_shell_path", None)
    if shell is not None and Path(shell).exists():
        return Path(shell)
    default = Path(__file__).resolve().parents[3] / "templates" / "EP2737_style_shell.docx"
    return default if default.exists() else None
