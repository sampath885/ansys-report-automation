"""Interactive production workflow: prompt paths, validate, build report."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "project.ep2737.production.yaml"
DEFAULT_OUTPUT = Path("automated_scripts_output")
DEFAULT_IMAGE_MAP = REPO_ROOT / "config" / "image_map.example.yaml"


@dataclass
class ProductionInputs:
    project_dir: Path
    image_assets: Path
    excel_calcs: Path
    excel_bolt_preload: Path | None
    out_dir: Path


def _normalize_path(raw: str) -> Path:
    return Path(raw.strip().strip('"').strip("'")).expanduser().resolve()


def _prompt_path(
    console: Console,
    label: str,
    *,
    must_exist: bool = True,
    allow_create: bool = False,
    required: bool = True,
) -> Path | None:
    while True:
        raw = typer.prompt(label, default="") if not required else typer.prompt(label)
        raw = raw.strip()
        if not raw:
            if not required:
                return None
            console.print("[yellow]This path is required.[/yellow]")
            continue

        path = _normalize_path(raw)
        if path.exists():
            return path
        if allow_create:
            try:
                path.mkdir(parents=True, exist_ok=True)
                console.print(f"[green]Created folder: {path}[/green]")
                return path
            except OSError as exc:
                console.print(f"[red]Could not create folder: {exc}[/red]")
                continue
        if must_exist:
            console.print(f"[yellow]Path not found: {path}[/yellow]")
            retry = typer.confirm("Use this path anyway?", default=False)
            if retry:
                return path
            continue
        return path


def prompt_production_inputs(console: Console | None = None) -> ProductionInputs:
    """Ask for image assets and required program file paths."""
    console = console or Console()
    console.print("\n[bold]ANSYS Report — Production Run[/bold]")
    console.print("Enter paths to your solved Workbench project and supporting files.\n")

    project_dir = _prompt_path(
        console,
        "ANSYS Workbench project folder (.wbpj location)",
        must_exist=True,
    )
    assert project_dir is not None

    image_assets = _prompt_path(
        console,
        "Image assets folder (export Mechanical plots here)",
        must_exist=False,
        allow_create=True,
    )
    assert image_assets is not None

    excel_calcs = _prompt_path(
        console,
        "Design calculations Excel file",
        must_exist=True,
    )
    assert excel_calcs is not None

    excel_bolt = _prompt_path(
        console,
        "Bolt preload Excel file (press Enter to skip)",
        must_exist=True,
        required=False,
    )

    out_dir = (Path.cwd() / DEFAULT_OUTPUT).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"\n[dim]Report output folder: {out_dir}[/dim]\n")

    return ProductionInputs(
        project_dir=project_dir,
        image_assets=image_assets,
        excel_calcs=excel_calcs,
        excel_bolt_preload=excel_bolt,
        out_dir=out_dir,
    )


def inputs_from_flags(
    *,
    project_dir: Path,
    image_assets: Path,
    excel_calcs: Path,
    excel_bolt_preload: Path | None = None,
    out_dir: Path | None = None,
) -> ProductionInputs:
    return ProductionInputs(
        project_dir=project_dir.resolve(),
        image_assets=image_assets.resolve(),
        excel_calcs=excel_calcs.resolve(),
        excel_bolt_preload=excel_bolt_preload.resolve() if excel_bolt_preload else None,
        out_dir=(out_dir or Path.cwd() / DEFAULT_OUTPUT).resolve(),
    )


def apply_production_inputs(cfg, inputs: ProductionInputs) -> None:
    """Override loaded project config with production paths."""
    case_root = _infer_case_root(inputs)
    cfg.project_dir = inputs.project_dir
    cfg.case_root = case_root
    cfg.image_folder = str(inputs.image_assets)
    cfg.excel_calcs = str(inputs.excel_calcs)
    cfg.excel_bolt_preload = (
        str(inputs.excel_bolt_preload) if inputs.excel_bolt_preload else None
    )
    cfg.skip_images = False


def _infer_case_root(inputs: ProductionInputs) -> Path:
    """Pick the case folder that contains Excel workbooks and related assets."""
    candidates = [
        inputs.excel_calcs.parent,
        inputs.project_dir.parent,
        inputs.image_assets.parent,
        inputs.project_dir,
    ]
    for path in candidates:
        if path.exists():
            return path.resolve()
    return inputs.project_dir.resolve()


def default_production_config() -> Path:
    if DEFAULT_CONFIG.exists():
        return DEFAULT_CONFIG
    fallback = REPO_ROOT / "config" / "project.ep2737.yaml"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        "Production config not found. Expected config/project.ep2737.production.yaml"
    )


def default_image_map() -> Path | None:
    return DEFAULT_IMAGE_MAP if DEFAULT_IMAGE_MAP.exists() else None
