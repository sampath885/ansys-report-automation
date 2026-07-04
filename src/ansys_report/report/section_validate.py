"""Validate build context against EP2737 section content matrix."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ansys_report.config import ProjectConfig, ValidationReport, load_project_config
from ansys_report.report.block_assembler import assemble_ep2737_document
from ansys_report.report.section_spec import SectionContentSpec, load_section_content_spec
from ansys_report.report.table_builders import enrich_context_tables


def validate_section_content(
    context: dict[str, Any],
    cfg: ProjectConfig,
    spec: SectionContentSpec | None = None,
) -> ValidationReport:
    """Check enabled sections against content matrix (figures, pending tables, data gaps)."""
    report = ValidationReport()
    spec = spec or load_section_content_spec(cfg.section_content_path)
    ctx = dict(context)
    enrich_context_tables(ctx, cfg)
    doc = assemble_ep2737_document(ctx, cfg, spec=spec)

    if cfg.skip_images:
        for slot in doc.missing_figures:
            report.add("figures", f"Figure slot missing (expected while skip_images): {slot}", "warning")
    else:
        for slot in doc.missing_figures:
            report.add("figures", f"Missing required figure: {slot}", "error")

    for label in doc.pending_blocks:
        report.add("content", f"Pending content block: {label}", "warning")

    for section in spec.sections:
        if not _section_relevant(section, cfg):
            continue
        section_key = section.section_key or section.key
        data = ctx.get(section_key)
        if data is None and section.key != "cover":
            if section.enabled_when_any:
                if not any(k in ctx for k in section.enabled_when_any):
                    report.add("sections", f"No data for section: {section.key}", "warning")
            elif section_key in cfg.sections_enabled:
                report.add("sections", f"No data for enabled section: {section_key}", "warning")
        _check_block_specs(section, data or {}, report)

    dc = ctx.get("design_calcs") or {}
    if "design_calcs" in cfg.sections_enabled:
        has_legacy = any(dc.get(k) for k in ("bolt_load", "flange_moments", "effort", "end_flange"))
        has_discovered = bool(dc.get("discovered_sections"))
        if not has_legacy and not has_discovered:
            src = dc.get("extraction_source") or "unknown"
            report.add(
                "excel",
                f"No design calculation tables extracted from workbook (source={src}). "
                "Check --excel-calcs path points to the UDPL calculation workbook.",
                "warning",
            )

    return report


def _section_relevant(section, cfg: ProjectConfig) -> bool:
    if section.key == "cover":
        return True
    if section.enabled_when_any:
        return any(k in cfg.sections_enabled for k in section.enabled_when_any)
    section_key = section.section_key or section.key
    return section_key in cfg.sections_enabled


def _check_block_specs(section, data: dict[str, Any], report: ValidationReport) -> None:
    _walk_block_specs(section.blocks, data, section.key, report)


def _walk_block_specs(blocks, data: dict[str, Any], section_key: str, report: ValidationReport) -> None:
    for block in blocks:
        if block.implemented is False:
            cap = block.caption or block.caption_template or block.note or block.type
            report.add("content", f"Not implemented: {section_key} / {cap}", "warning")
        if block.type == "table" and block.implemented is not False:
            if block.rows_path and not _has_rows(data, block.rows_path):
                cap = block.caption or block.rows_path
                report.add("data", f"Empty table data: {section_key} → {cap}", "warning")
        if block.type == "repeat":
            items = data.get(block.items_path or "") if isinstance(data, dict) else None
            if not items:
                continue
            for item in items:
                _walk_block_specs(block.blocks, item, section_key, report)


def _has_rows(data: dict[str, Any], rows_path: str) -> bool:
    cur: Any = data
    for part in rows_path.split("."):
        if not isinstance(cur, dict):
            return False
        cur = cur.get(part)
    return bool(cur)


def validate_ep2737_from_config(
    config_path: Path,
    context: dict[str, Any] | None = None,
) -> ValidationReport:
    cfg = load_project_config(config_path)
    if context is None:
        from ansys_report.report.context_builder import build_context
        from ansys_report.scanner import scan_project

        inventory = scan_project(
            cfg.project_dir,
            cfg.image_folder,
            cfg.excel_calcs,
            case_root=cfg.case_root,
            excel_bolt_preload=cfg.excel_bolt_preload,
        )
        context, build_report = build_context(cfg, inventory=inventory, use_ai=False)
        report = build_report
    else:
        report = ValidationReport()
    report.merge(validate_section_content(context, cfg))
    return report
