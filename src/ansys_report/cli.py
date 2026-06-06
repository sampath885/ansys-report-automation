"""Command-line interface for ansys-report."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ansys_report.config import (
    ValidationReport,
    load_image_map,
    load_project_config,
    load_thresholds,
    validate_project_paths,
)
from ansys_report.images.mapper import assets_to_validation, build_inline_images, resolve_assets
from ansys_report.report.context_builder import build_context, load_mock_results
from ansys_report.report.pdf import convert_to_pdf
from ansys_report.report.render import default_template_path, render_report
from ansys_report.scanner import scan_project

app = typer.Typer(help="ANSYS EP1763-style report automation")
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _print_validation(report: ValidationReport) -> None:
    if not report.issues:
        console.print("[green]Validation passed — no issues found.[/green]")
        return
    table = Table(title="Validation checklist")
    table.add_column("Severity")
    table.add_column("Category")
    table.add_column("Message")
    for issue in report.issues:
        color = "red" if issue.severity == "error" else "yellow"
        table.add_row(f"[{color}]{issue.severity}[/{color}]", issue.category, issue.message)
    console.print(table)


def _resolve_paths(
    config: Path,
    project_dir: Optional[Path],
    image_map: Optional[Path],
    template: Optional[Path],
):
    cfg = load_project_config(config, project_dir)
    repo = config.resolve().parent.parent
    if image_map is None:
        candidate = repo / "config" / "image_map.example.yaml"
        image_map = candidate if candidate.exists() else None
    if template is None:
        template = default_template_path()
    cfg.thresholds_path = repo / "config" / "thresholds.yaml"
    cfg.template_path = template
    cfg.image_map_path = image_map
    return cfg


@app.command()
def build(
    config: Path = typer.Option(..., "--config", "-c", help="Path to project.yaml"),
    project_dir: Optional[Path] = typer.Option(None, "--project-dir", help="Workbench project folder"),
    out: Path = typer.Option(Path("output"), "--out", "-o", help="Output directory"),
    image_map: Optional[Path] = typer.Option(None, "--image-map", help="image_map.yaml path"),
    template: Optional[Path] = typer.Option(None, "--template", help="docxtpl template path"),
    mock: Optional[Path] = typer.Option(None, "--mock", help="Use mock_results.json instead of ANSYS"),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF export"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable AI narrative polish"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate DOCX (and optionally PDF) report."""
    _setup_logging(verbose)
    cfg = _resolve_paths(config, project_dir, image_map, template)

    mock_data = load_mock_results(mock) if mock else None
    inventory = None
    if not mock_data:
        inventory = scan_project(cfg.project_dir, cfg.image_folder, cfg.excel_calcs)

    validation = validate_project_paths(cfg)
    images_ctx: dict = {}
    tpl_path = cfg.template_path or default_template_path()

    if cfg.image_map_path and cfg.image_map_path.exists():
        imap = load_image_map(cfg.image_map_path)
        root = cfg.image_root if cfg.image_root.exists() else cfg.project_dir
        assets = resolve_assets(root, imap)
        validation.merge(assets_to_validation(assets))
        if tpl_path.exists():
            from docxtpl import DocxTemplate

            tpl = DocxTemplate(str(tpl_path))
            images_ctx = build_inline_images(tpl, assets)

    context, build_validation = build_context(
        cfg,
        inventory=inventory,
        mock_data=mock_data,
        use_ai=not no_ai,
        images=images_ctx,
    )
    validation.merge(build_validation)

    if validation.has_errors:
        _print_validation(validation)
        raise typer.Exit(code=2)

    safe_name = cfg.bom_id.replace(" ", "_")
    docx_out = out / f"{safe_name}_report.docx"
    if not tpl_path.exists():
        console.print(f"[red]Template not found: {tpl_path}[/red]")
        console.print("Run: ansys-report template --out templates/")
        raise typer.Exit(code=1)

    render_report(tpl_path, context, docx_out)
    if not no_pdf:
        convert_to_pdf(docx_out)

    _print_validation(validation)
    console.print(f"[green]Report written to {docx_out}[/green]")


@app.command()
def validate(
    config: Path = typer.Option(..., "--config", "-c"),
    project_dir: Optional[Path] = typer.Option(None, "--project-dir"),
    image_map: Optional[Path] = typer.Option(None, "--image-map"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Validate inputs without rendering."""
    _setup_logging(verbose)
    cfg = _resolve_paths(config, project_dir, image_map, None)
    validation = validate_project_paths(cfg)

    try:
        inventory = scan_project(cfg.project_dir, cfg.image_folder, cfg.excel_calcs)
    except FileNotFoundError as exc:
        validation.add("paths", str(exc), "error")
        inventory = None

    if inventory and cfg.image_map_path and cfg.image_map_path.exists():
        imap = load_image_map(cfg.image_map_path)
        root = cfg.image_root if cfg.image_root.exists() else cfg.project_dir
        assets = resolve_assets(root, imap)
        validation.merge(assets_to_validation(assets))

    if inventory:
        _, build_validation = build_context(cfg, inventory=inventory, use_ai=False)
        validation.merge(build_validation)

    _print_validation(validation)
    if validation.has_errors or any(i.severity == "warning" for i in validation.issues):
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


@app.command()
def template(
    from_docx: Optional[Path] = typer.Option(None, "--from", help="Source EP1763 sample docx"),
    out: Path = typer.Option(Path("templates"), "--out", help="Output directory"),
) -> None:
    """Create or regenerate the report template."""
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "EP1763_report_template.docx"
    from ansys_report.report.template_builder import (
        create_minimal_template,
        create_minimal_template_from_scratch,
    )

    if from_docx and from_docx.exists():
        create_minimal_template(from_docx, dest)
    else:
        create_minimal_template_from_scratch(dest)
    console.print(f"[green]Template written to {dest}[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
