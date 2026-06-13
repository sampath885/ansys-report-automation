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
    ProjectConfig,
    ValidationReport,
    load_image_map,
    load_project_config,
    validate_project_paths,
)
from ansys_report.images.mapper import assets_to_validation, build_inline_images, resolve_assets
from ansys_report.production_flow import (
    apply_production_inputs,
    default_image_map,
    default_production_config,
    inputs_from_flags,
    prompt_production_inputs,
)
from ansys_report.report.context_builder import build_context, load_mock_results
from ansys_report.report.pdf import convert_to_pdf
from ansys_report.report.render import default_template_path, render_report
from ansys_report.scanner import scan_project

app = typer.Typer(help="ANSYS EP1763-style report automation")
console = Console()


def _scan(cfg) -> "ProjectInventory":
    return scan_project(
        cfg.project_dir,
        cfg.image_folder,
        cfg.excel_calcs,
        case_root=cfg.case_root,
        excel_bolt_preload=cfg.excel_bolt_preload,
    )


def _print_inventory(inventory) -> None:
    table = Table(title="Project inventory")
    table.add_column("Key")
    table.add_column("Folder")
    table.add_column("Display name")
    table.add_column("Primary .rst")
    table.add_column("Status")
    for key, sys in sorted(inventory.systems.items()):
        rst = str(sys.primary_rst.name) if sys.primary_rst else "—"
        err = sys.mapdl_errors if sys.mapdl_errors is not None else "?"
        table.add_row(key, sys.folder, sys.display_name, rst, f"mapdl_errors={err}")
    console.print(table)
    meta = Table(title="Assets")
    meta.add_column("Item")
    meta.add_column("Path")
    meta.add_row("project_dir", str(inventory.project_dir))
    meta.add_row("case_root", str(inventory.case_root or "—"))
    meta.add_row("wbpj", str(inventory.wbpj_primary or "—"))
    meta.add_row("ansys_version", str(inventory.ansys_version or "—"))
    meta.add_row("excel", str(inventory.excel_path or "—"))
    meta.add_row("excel_bolt", str(inventory.excel_bolt_preload or "—"))
    meta.add_row("images", str(inventory.image_root))
    meta.add_row("cad_step", str(inventory.cad_step or "—"))
    console.print(meta)
    if inventory.warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for w in inventory.warnings:
            console.print(f"  • {w}")


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
) -> ProjectConfig:
    cfg = load_project_config(config, project_dir)
    repo = config.resolve().parent.parent
    if image_map is None:
        candidate = repo / "config" / "image_map.example.yaml"
        image_map = candidate if candidate.exists() else None
    if template is None:
        template = cfg.template_path if cfg.template_path else default_template_path()
    cfg.thresholds_path = repo / "config" / "thresholds.yaml"
    cfg.template_path = template
    cfg.image_map_path = image_map
    return cfg


def _execute_build(
    cfg: ProjectConfig,
    *,
    out: Path,
    mock_data: Optional[dict] = None,
    golden_dpf: bool = False,
    no_pdf: bool = False,
    no_ai: bool = False,
    verbose: bool = False,
) -> Path:
    """Scan, validate, render DOCX (and optional PDF). Returns path to DOCX."""
    inventory = None
    if not mock_data:
        inventory = _scan(cfg)

    validation = validate_project_paths(cfg)
    images_ctx: dict = {}
    tpl_path = cfg.template_path or default_template_path()

    if cfg.image_map_path and cfg.image_map_path.exists() and not cfg.skip_images:
        imap = load_image_map(cfg.image_map_path)
        root = cfg.image_root if cfg.image_root.exists() else cfg.project_dir
        assets = resolve_assets(root, imap)
        validation.merge(assets_to_validation(assets))
        if tpl_path.exists() and "EP2737" in tpl_path.name.upper():
            images_ctx = dict(assets.resolved)
        elif tpl_path.exists():
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
    if not mock_data:
        from ansys_report.report.ep2737_overlay import apply_golden_dpf_overlay, needs_golden_overlay

        if golden_dpf or (cfg.use_dpf_golden_fallback and needs_golden_overlay(context)):
            apply_golden_dpf_overlay(context, cfg, force=golden_dpf)
        elif cfg.use_dpf_golden_fallback:
            apply_golden_dpf_overlay(context, cfg, force=False)
    validation.merge(build_validation)

    if not mock_data and cfg.section_content_path and cfg.section_content_path.exists():
        from ansys_report.report.section_validate import validate_section_content
        from ansys_report.report.table_builders import enrich_context_tables

        enrich_context_tables(context, cfg)
        validation.merge(validate_section_content(context, cfg))

    if validation.has_errors:
        _print_validation(validation)
        raise typer.Exit(code=2)

    safe_name = cfg.bom_id.replace(" ", "_")
    out.mkdir(parents=True, exist_ok=True)
    docx_out = out / f"{safe_name}_report.docx"
    if not tpl_path.exists():
        console.print(f"[red]Template not found: {tpl_path}[/red]")
        console.print("Run: ansys-report template --out templates/")
        raise typer.Exit(code=1)

    render_report(tpl_path, context, docx_out, cfg=cfg)
    if verbose:
        from ansys_report.report.data_sources import format_data_sources_report

        console.print(format_data_sources_report(context, cfg))
    if not no_pdf:
        convert_to_pdf(docx_out)

    _print_validation(validation)
    console.print(f"[green]Report written to {docx_out}[/green]")
    return docx_out


@app.command()
def run(
    project_dir: Optional[Path] = typer.Option(
        None,
        "--project-dir",
        help="Workbench project folder (skip prompt when set with other paths)",
    ),
    image_assets: Optional[Path] = typer.Option(
        None,
        "--image-assets",
        help="Folder for exported Mechanical plot images",
    ),
    excel_calcs: Optional[Path] = typer.Option(
        None,
        "--excel-calcs",
        help="Design calculations Excel workbook",
    ),
    excel_bolt_preload: Optional[Path] = typer.Option(
        None,
        "--excel-bolt-preload",
        help="Bolt preload Excel workbook",
    ),
    out: Path = typer.Option(
        Path("automated_scripts_output"),
        "--out",
        "-o",
        help="Output folder for generated DOCX/PDF",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Base project config (default: production EP2737)",
    ),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF export"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable AI narrative polish"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Production: prompt for paths, validate, and build report to automated_scripts_output."""
    _setup_logging(verbose)
    config_path = config or default_production_config()
    cfg = _resolve_paths(config_path, None, default_image_map(), None)

    flag_paths = [project_dir, image_assets, excel_calcs]
    if all(flag_paths):
        inputs = inputs_from_flags(
            project_dir=project_dir,
            image_assets=image_assets,
            excel_calcs=excel_calcs,
            excel_bolt_preload=excel_bolt_preload,
            out_dir=out,
        )
    elif any(flag_paths):
        console.print(
            "[red]Provide all of --project-dir, --image-assets, and --excel-calcs "
            "or run without flags for interactive prompts.[/red]"
        )
        raise typer.Exit(code=1)
    else:
        inputs = prompt_production_inputs(console)

    apply_production_inputs(cfg, inputs)
    console.print("[bold]Step 1/3[/bold] Scanning Workbench project…")
    inventory = _scan(cfg)
    _print_inventory(inventory)

    console.print("[bold]Step 2/3[/bold] Validating inputs…")
    validation = validate_project_paths(cfg)
    if cfg.image_map_path and cfg.image_map_path.exists():
        imap = load_image_map(cfg.image_map_path)
        root = cfg.image_root if cfg.image_root.exists() else cfg.project_dir
        assets = resolve_assets(root, imap)
        validation.merge(assets_to_validation(assets))
    _print_validation(validation)
    if validation.has_errors:
        raise typer.Exit(code=2)

    console.print("[bold]Step 3/3[/bold] Building report…")
    _execute_build(cfg, out=inputs.out_dir, no_pdf=no_pdf, no_ai=no_ai, verbose=verbose)


@app.command()
def build(
    config: Path = typer.Option(..., "--config", "-c", help="Path to project.yaml"),
    project_dir: Optional[Path] = typer.Option(None, "--project-dir", help="Workbench project folder"),
    out: Path = typer.Option(Path("output"), "--out", "-o", help="Output directory"),
    image_map: Optional[Path] = typer.Option(None, "--image-map", help="image_map.yaml path"),
    template: Optional[Path] = typer.Option(None, "--template", help="docxtpl template path"),
    mock: Optional[Path] = typer.Option(None, "--mock", help="Use mock_results.json instead of ANSYS"),
    golden_dpf: bool = typer.Option(False, "--golden-dpf", help="Use golden modal/static when DPF unavailable"),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF export"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable AI narrative polish"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate DOCX (and optionally PDF) report."""
    _setup_logging(verbose)
    cfg = _resolve_paths(config, project_dir, image_map, template)
    mock_data = load_mock_results(mock) if mock else None
    _execute_build(
        cfg,
        out=out,
        mock_data=mock_data,
        golden_dpf=golden_dpf,
        no_pdf=no_pdf,
        no_ai=no_ai,
        verbose=verbose,
    )


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
        inventory = _scan(cfg)
    except FileNotFoundError as exc:
        validation.add("paths", str(exc), "error")
        inventory = None

    if inventory and cfg.image_map_path and cfg.image_map_path.exists():
        imap = load_image_map(cfg.image_map_path)
        root = cfg.image_root if cfg.image_root.exists() else cfg.project_dir
        assets = resolve_assets(root, imap)
        validation.merge(assets_to_validation(assets))

    if inventory:
        from ansys_report.report.context_builder import build_context
        from ansys_report.report.section_validate import validate_section_content
        from ansys_report.report.table_builders import enrich_context_tables

        context, build_validation = build_context(cfg, inventory=inventory, use_ai=False)
        validation.merge(build_validation)
        if cfg.section_content_path and cfg.section_content_path.exists():
            enrich_context_tables(context, cfg)
            validation.merge(validate_section_content(context, cfg))

    _print_validation(validation)
    if validation.has_errors or any(i.severity == "warning" for i in validation.issues):
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


@app.command()
def excel(
    config: Path = typer.Option(
        Path("config/project.ep2737.yaml"),
        "--config",
        "-c",
        help="project.yaml",
    ),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write excel summary JSON"),
    write_golden: bool = typer.Option(False, "--write-golden", help="Refresh golden JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Extract EP2737 design calculation tables from Excel (Phase 4)."""
    _setup_logging(verbose)

    if write_golden or json_out is None:
        import subprocess
        import sys

        script = Path(__file__).resolve().parents[2] / "scripts" / "spikes" / "run_ep2737_excel.py"
        args = [sys.executable, str(script)]
        if write_golden:
            args.append("--write-golden")
        proc = subprocess.run(args, cwd=str(script.parents[2]))
        if proc.returncode != 0:
            raise typer.Exit(code=proc.returncode)

    if json_out:
        from ansys_report.config import load_project_config
        from ansys_report.excel.ep2737 import summarize_for_golden
        from ansys_report.excel.reader import read_design_calcs

        cfg = load_project_config(config)
        case_root = cfg.case_root or cfg.project_dir
        result = read_design_calcs(
            cfg.excel_path,
            excel_map_path=cfg.excel_map_path,
            case_root=case_root,
            fos_target=cfg.static.fos_target,
        )
        payload = summarize_for_golden(result)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"[green]Excel summary JSON: {json_out}[/green]")
    raise typer.Exit(code=0)


@app.command()
def phase7(
    write_golden: bool = typer.Option(False, "--write-golden", help="Refresh Phase 7 golden JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run Phase 7 harmonic Y/Z + shock DPF spikes (slow; requires ANSYS)."""
    _setup_logging(verbose)
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2] / "scripts" / "spikes" / "run_ep2737_phase7.py"
    args = [sys.executable, str(script)]
    if write_golden:
        args.append("--write-golden")
    proc = subprocess.run(args, cwd=str(script.parents[2]))
    raise typer.Exit(code=proc.returncode)


@app.command()
def metadata(
    config: Path = typer.Option(
        Path("config/project.ep2737.yaml"),
        "--config",
        "-c",
        help="project.yaml",
    ),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write metadata JSON"),
    write_golden: bool = typer.Option(False, "--write-golden", help="Refresh golden JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Extract Equipment/Modelling metadata from CAERep/MatML (Phase 3, no DPF)."""
    _setup_logging(verbose)

    if write_golden or json_out is None:
        import subprocess
        import sys

        script = Path(__file__).resolve().parents[2] / "scripts" / "spikes" / "run_ep2737_metadata.py"
        args = [sys.executable, str(script)]
        if write_golden:
            args.append("--write-golden")
        proc = subprocess.run(args, cwd=str(script.parents[2]))
        if proc.returncode != 0:
            raise typer.Exit(code=proc.returncode)

    if json_out:
        from ansys_report.config import load_project_config
        from ansys_report.extract.metadata import extract_project_metadata
        from ansys_report.scanner import scan_project

        cfg = load_project_config(config)
        inv = scan_project(
            cfg.project_dir,
            cfg.image_folder,
            cfg.excel_calcs,
            case_root=cfg.case_root,
            excel_bolt_preload=cfg.excel_bolt_preload,
        )
        meta = extract_project_metadata(inv, cfg.bom_id, cfg.title)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(meta.to_json_dict(), indent=2), encoding="utf-8")
        console.print(f"[green]Metadata JSON: {json_out}[/green]")
    raise typer.Exit(code=0)


@app.command()
def spike(
    write_golden: bool = typer.Option(False, "--write-golden", help="Refresh golden JSON files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run Phase 2 DPF spikes on EP2737 and compare to golden values."""
    _setup_logging(verbose)
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2] / "scripts" / "spikes" / "run_ep2737_spikes.py"
    args = [sys.executable, str(script)]
    if write_golden:
        args.append("--write-golden")
    proc = subprocess.run(args, cwd=str(script.parents[2]))
    raise typer.Exit(code=proc.returncode)


@app.command()
def inventory(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="project.yaml"),
    project_dir: Optional[Path] = typer.Option(None, "--project-dir", help="Workbench folder"),
    case_root: Optional[Path] = typer.Option(None, "--case-root", help="Case folder (Excel, exports)"),
    excel_calcs: str = typer.Option("design_calcs.xlsx", "--excel-calcs"),
    excel_bolt_preload: Optional[str] = typer.Option(None, "--excel-bolt-preload"),
    image_folder: str = typer.Option("exports", "--image-folder"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write inventory JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List discovered Workbench systems and asset paths (Phase 1)."""
    _setup_logging(verbose)
    if config:
        cfg = load_project_config(config, project_dir)
        if case_root:
            cfg.case_root = case_root.resolve()
        inv = _scan(cfg)
    else:
        if project_dir is None:
            console.print("[red]Provide --config or --project-dir[/red]")
            raise typer.Exit(code=1)
        inv = scan_project(
            project_dir,
            image_folder,
            excel_calcs,
            case_root=case_root,
            excel_bolt_preload=excel_bolt_preload,
        )
    _print_inventory(inv)
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(inv.to_json_dict(), indent=2), encoding="utf-8")
        console.print(f"[green]Inventory JSON: {json_out}[/green]")
    if inv.warnings:
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)


@app.command()
def template(
    from_docx: Optional[Path] = typer.Option(None, "--from", help="Source EP1763 sample docx"),
    out: Path = typer.Option(Path("templates"), "--out", help="Output directory"),
    ep2737: bool = typer.Option(False, "--ep2737", help="Create EP2737 Phase 6 template"),
) -> None:
    """Create or regenerate the report template."""
    out.mkdir(parents=True, exist_ok=True)
    from ansys_report.report.template_builder import (
        create_ep2737_template,
        create_minimal_template,
        create_minimal_template_from_scratch,
    )

    if ep2737:
        dest = out / "EP2737_report_template.docx"
        create_ep2737_template(dest)
    else:
        dest = out / "EP1763_report_template.docx"
        if from_docx and from_docx.exists():
            create_minimal_template(from_docx, dest)
        else:
            create_minimal_template_from_scratch(dest)
    console.print(f"[green]Template written to {dest}[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
