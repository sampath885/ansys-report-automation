"""Scaffold per-job project config and report defaults from Workbench scan + CAERep."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ansys_report.extract.metadata import (
    extract_modelling_metadata,
    extract_project_metadata,
)
from ansys_report.scanner import scan_project

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_TEMPLATE = REPO_ROOT / "config" / "templates" / "project.template.yaml"
REPORT_DEFAULTS_TEMPLATE = REPO_ROOT / "config" / "templates" / "report_defaults.template.yaml"


class ProjectInitError(Exception):
    pass


def _load_template(path: Path) -> str:
    if not path.exists():
        raise ProjectInitError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def _rel_to_config(path: Path, config_dir: Path) -> str:
    try:
        rel = path.resolve().relative_to(config_dir.resolve())
        return f"../{rel.as_posix()}"
    except ValueError:
        return str(path.resolve())


def _slug(bom_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", bom_id.strip()).strip("_").lower()


def _default_material_props(yield_mpa: float | None) -> dict[str, float]:
    y = yield_mpa or 205.0
    uts = round(y * 2.5, 2)
    static_allow = round(min(y * (2 / 3), uts / 3.5), 2)
    fatigue = round(static_allow / 2, 2)
    return {
        "yield_mpa": y,
        "uts_mpa": uts,
        "static_allowable_mpa": static_allow,
        "fatigue_allowable_mpa": fatigue,
    }


def discover_project_facts(
    project_dir: Path,
    *,
    case_root: Path | None = None,
    bom_id: str,
    title: str,
    excel_calcs: str = "design_calcs.xlsx",
    excel_bolt_preload: str | None = "Bolt pre load.xlsx",
) -> dict[str, Any]:
    """Scan Workbench tree and CAERep; return values for template substitution."""
    inventory = scan_project(
        project_dir,
        "exports",
        excel_calcs,
        case_root=case_root,
        excel_bolt_preload=excel_bolt_preload,
    )
    meta = extract_project_metadata(inventory, bom_id, title)
    modelling = extract_modelling_metadata(inventory)

    primary_material = "Material"
    yield_from_matml: float | None = None
    for mat in modelling.materials:
        name = (mat.name or "").lower()
        if "nylon" in name or "gasket" in name:
            continue
        primary_material = mat.name
        yield_from_matml = mat.tensile_yield_mpa
        break
    if primary_material == "Material" and meta.equipment.material_names:
        primary_material = meta.equipment.material_names[0]

    props = _default_material_props(yield_from_matml)
    assembly_mass = meta.equipment.assembly.mass_kg if meta.equipment.assembly else None
    drawing_mass = f"{assembly_mass:.3g} kg" if assembly_mass else "TBD"

    preload_count = 8
    for load in modelling.loads:
        if load.load_type == "bolt_pretension" and load.count:
            preload_count = load.count

    excel_name = Path(excel_calcs).name
    bolt_excel = Path(excel_bolt_preload).name if excel_bolt_preload else ""

    return {
        "inventory": inventory,
        "metadata": meta,
        "modelling": modelling,
        "bom_id": bom_id,
        "title": title,
        "ansys_version": inventory.ansys_version or "2025 R2",
        "project_dir": str(project_dir.resolve()),
        "case_root": str(case_root.resolve()) if case_root else str(project_dir.resolve()),
        "excel_calcs": excel_name,
        "excel_bolt_preload": bolt_excel,
        "part_name": title.title(),
        "material_grade": primary_material,
        "primary_material": primary_material,
        "drawing_mass_kg": drawing_mass,
        "bolt_count": preload_count,
        "yield_mpa": props["yield_mpa"],
        "uts_mpa": props["uts_mpa"],
        "static_allowable_mpa": props["static_allowable_mpa"],
        "fatigue_allowable_mpa": props["fatigue_allowable_mpa"],
        "node_count": modelling.node_count,
        "element_count": modelling.element_count,
        "load_count": len(modelling.loads),
        "bc_count": len(modelling.boundary_conditions),
        "contact_count": len(modelling.contacts),
        "systems_count": len(inventory.systems),
    }


def render_project_yaml(facts: dict[str, Any], config_dir: Path) -> str:
    """Fill project.template.yaml with discovered facts."""
    slug = _slug(facts["bom_id"])
    defaults_path = config_dir / f"{slug}_report_defaults.yaml"
    facts = {
        **facts,
        "project_dir": _rel_to_config(Path(facts["project_dir"]), config_dir),
        "case_root": _rel_to_config(Path(facts["case_root"]), config_dir),
        "report_defaults_path": _rel_to_config(defaults_path, config_dir),
    }
    template = _load_template(PROJECT_TEMPLATE)
    for key, value in facts.items():
        template = template.replace(f"{{{{ {key} }}}}", str(value))
    return template


def render_report_defaults_yaml(facts: dict[str, Any]) -> str:
    """Minimal report defaults with scanned summary in comments."""
    template = _load_template(REPORT_DEFAULTS_TEMPLATE)
    return template


def init_project_config(
    *,
    bom_id: str,
    title: str,
    project_dir: Path,
    case_root: Path | None = None,
    customer: str = "Customer name",
    config_dir: Path | None = None,
    excel_calcs: str = "design_calcs.xlsx",
    excel_bolt_preload: str | None = "Bolt pre load.xlsx",
    overwrite: bool = False,
) -> dict[str, Path]:
    """Write project YAML + report_defaults YAML under config/."""
    project_dir = project_dir.resolve()
    if not project_dir.exists():
        raise ProjectInitError(f"project_dir not found: {project_dir}")

    config_dir = (config_dir or REPO_ROOT / "config").resolve()
    config_dir.mkdir(parents=True, exist_ok=True)

    facts = discover_project_facts(
        project_dir,
        case_root=case_root.resolve() if case_root else None,
        bom_id=bom_id,
        title=title,
        excel_calcs=excel_calcs,
        excel_bolt_preload=excel_bolt_preload,
    )
    facts["customer"] = customer

    slug = _slug(bom_id)
    project_path = config_dir / f"project.{slug}.yaml"
    defaults_path = config_dir / f"{slug}_report_defaults.yaml"

    if project_path.exists() and not overwrite:
        raise ProjectInitError(f"Config already exists: {project_path} (use overwrite=True)")
    if defaults_path.exists() and not overwrite:
        raise ProjectInitError(f"Defaults already exist: {defaults_path} (use overwrite=True)")

    project_path.write_text(render_project_yaml(facts, config_dir), encoding="utf-8")
    defaults_path.write_text(render_report_defaults_yaml(facts), encoding="utf-8")

    return {"project_config": project_path, "report_defaults": defaults_path}
