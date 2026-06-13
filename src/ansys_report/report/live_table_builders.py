"""Build EP2737 reference tables from live CAERep context and project config."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig


def build_live_reference_tables(context: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
    """Tables derived from extraction context (CAERep/MatML), not Word exports."""
    tables: dict[str, Any] = {}
    equipment = context.get("equipment") or {}
    modelling = context.get("modelling") or context.get("static_analysis") or {}
    materials = modelling.get("materials") or []
    design_calcs = context.get("design_calcs") or {}

    mass = build_mass_balance_table(equipment, cfg)
    if mass:
        tables["mass_balance"] = mass

    cog = build_centre_of_gravity_table(equipment)
    if cog:
        tables["centre_of_gravity"] = cog

    tech = build_technical_specifications_table(equipment, cfg)
    if tech:
        tables["technical_specifications"] = tech

    mat_mod = build_material_properties_modelling(materials, cfg)
    if mat_mod:
        tables["material_properties_modelling"] = mat_mod

    mat_res = build_material_properties_results(materials, cfg)
    if mat_res:
        tables["material_properties_results"] = mat_res

    allow = build_material_allowable_strength(cfg)
    if allow:
        tables["material_allowable_strength"] = allow

    mesh = build_mesh_control_table(modelling)
    if mesh:
        tables["mesh_control_reference"] = mesh

    quality = build_mesh_quality_table(modelling, cfg)
    if quality:
        tables["mesh_quality"] = quality

    loads_table = build_loads_summary_table(context.get("loads") or {})
    if loads_table:
        tables["loads_summary"] = loads_table

    fatigue = build_fatigue_strength_table(design_calcs, cfg)
    if fatigue:
        tables["fatigue_strength_calculations"] = fatigue

    return tables


def build_mass_balance_table(equipment: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
    spec = cfg.equipment_spec
    assembly = equipment.get("assembly") or {}
    assembly_mass = assembly.get("mass_kg")

    flange_mass = _flange_fe_mass_kg(equipment.get("bodies") or [])
    fe_mass = _fmt(flange_mass) if flange_mass is not None else ""
    total_mass = _fmt(assembly_mass) if assembly_mass is not None else ""

    return {
        "caption": "Table 5: Mass Balance",
        "headers": [
            "S.No.",
            "Part Name",
            "Material Std/Grade",
            "Qty",
            "Drawing (Kg)",
            "FE Model Mass (Kg)",
            "Total Mass",
        ],
        "rows": [
            [
                "1",
                spec.part_name,
                spec.material_grade,
                "1",
                spec.drawing_mass_kg,
                spec.fe_mass_note,
                "Total Mass",
            ],
            ["", "", "", "", "", fe_mass, total_mass],
        ],
    }


def build_centre_of_gravity_table(equipment: dict[str, Any]) -> dict[str, Any] | None:
    assembly = equipment.get("assembly") or {}
    cog = assembly.get("cog_mm") or {}
    if not cog:
        return None
    x = cog.get("x_mm", 0)
    y = cog.get("y_mm", 0)
    z = cog.get("z_mm", 0)
    text = (
        f"From the reference coordinate cg. Wt= ∫ x dw "
        f"XCG = {x:.4g} mm YCG = {y:.4g} mm ZCG = {z:.4g} mm"
    )
    return {
        "caption": "Table 6: Centre of gravity",
        "headers": [text, ""],
        "rows": [[text, ""]],
    }


def build_technical_specifications_table(
    equipment: dict[str, Any],
    cfg: ProjectConfig,
) -> dict[str, Any]:
    spec = cfg.equipment_spec
    primary_mat = cfg.materials[0].name if cfg.materials else "—"
    return {
        "caption": "Table 7: Technical Specifications",
        "headers": ["S.No", "Parameter", "Value"],
        "rows": [
            ["1", "Nominal Bore", "100 mm"],
            ["2", "Working Pressure", "10 kg/cm²"],
            ["3", "Working Medium", "Air"],
            ["5", "Weight", f"{spec.drawing_mass_kg.replace('±', '±')} kg"],
            ["6", "Material", primary_mat],
        ],
    }


def build_material_properties_modelling(
    materials: list[dict[str, Any]],
    cfg: ProjectConfig,
) -> dict[str, Any] | None:
    mat = _primary_material(materials, cfg)
    if not mat:
        return None
    name = mat.get("name") or (cfg.materials[0].name if cfg.materials else "Material")
    report = _report_material(cfg)
    ref = "ASME Sec II Part D-2023"
    rows: list[list[str]] = [
        ["S.No", "Property", "Value", "Units", ""],
        ["1", "Density", _fmt(mat.get("density_kg_m3")), "Kg/m^3", f"{ref}, Table PRD, Page No. 1154 (series 300)"],
        ["2", "Elastic Modulus", _fmt(mat.get("youngs_modulus_gpa")), "GPa", f"{ref}, Table TM1, Group G, Pg No. 1148"],
        ["3", "Poisson's Ratio", _fmt(mat.get("poissons_ratio")), "", f"{ref}, Table PRD, Page No. 1154 (series 300)"],
        ["4", "Yield Strength", _fmt(report.get("yield_mpa")), "MPa / (N/mm^2)", f"{ref}, Pg No. 112, Group 20"],
        ["5", "Tensile Strength", _fmt(report.get("uts_mpa")), "MPa / (N/mm^2)", ""],
        ["6", "% of Elongation", _fmt(report.get("elongation_pct")), "%", "ASTM A182/A182M-12a, Table 3, Pg- 11"],
        [
            "7",
            "Static Allowable Strength (Min (2/3YTS or 1/3.5UTS))",
            _fmt(report.get("static_allowable_mpa")),
            "MPa / (N/mm^2)",
            f"{ref}, Pg No. 114, Group 20",
        ],
    ]
    return {
        "caption": "Table 10: Material Properties",
        "headers": ["ASTM A 182 F32100", "References"],
        "rows": rows,
    }


def build_material_properties_results(
    materials: list[dict[str, Any]],
    cfg: ProjectConfig,
) -> dict[str, Any] | None:
    mat = _primary_material(materials, cfg)
    if not mat:
        return None
    trade, grade = _split_material_name("ASTM A 182 F32100")
    return {
        "caption": "Table 12: Material Properties",
        "headers": [
            "Trade name of Material",
            "Material Grade",
            "Young's Modulus (GPa)",
            "Density (kg/m3)",
            "Poisson's Ratio",
            "Reference Standard",
        ],
        "rows": [
            [
                trade,
                grade,
                _fmt(mat.get("youngs_modulus_gpa")),
                _fmt(mat.get("density_kg_m3")),
                _fmt(mat.get("poissons_ratio")),
                "ASME Section II, Part D",
            ]
        ],
    }


def build_material_allowable_strength(cfg: ProjectConfig) -> dict[str, Any] | None:
    if not cfg.materials:
        return None
    report = _report_material(cfg)
    trade, grade = _split_material_name("ASTM A 182 F32100")
    return {
        "caption": "Table 13: Material allowable strength – Static and Fatigue",
        "headers": [
            "Trade name of Material",
            "Material Grade",
            "Yield (MPa)",
            "Ultimate Tensile Strength (MPa)",
            "% Elongation",
            "Static Allowable (MPa)",
            "Fatigue Allowable(MPa) Base Material",
            "Fatigue Allowable(MPa) Welds",
        ],
        "rows": [
            [
                trade,
                grade,
                _fmt(report.get("yield_mpa")),
                _fmt(report.get("uts_mpa")),
                _fmt(report.get("elongation_pct")),
                _fmt(report.get("static_allowable_mpa")),
                _fmt(report.get("fatigue_allowable_mpa")),
                "N.A",
            ],
            [
                "",
                "*Allowable stresses for Strength: Min of (1/3.5 x UTS) or (2/3 x Yield strength)",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
        ],
    }


def build_mesh_quality_table(
    modelling: dict[str, Any],
    cfg: ProjectConfig,
) -> dict[str, Any] | None:
    metrics = modelling.get("quality_metrics") or {}
    if not metrics:
        return None

    criteria = cfg.mesh_quality_criteria
    rows: list[list[str]] = []

    def _row(
        index: int,
        label: str,
        key: str,
        criterion: Any,
        value_key: str,
        *,
        suffix: str = "",
    ) -> None:
        block = metrics.get(key) or {}
        measured = block.get(value_key)
        if measured is None:
            return
        acceptance = f"{criterion.operator} {_fmt(criterion.limit)}{suffix}"
        rows.append([str(index), label, acceptance, f"{_fmt(measured)}{suffix}"])

    _row(1, "Aspect Ratio", "aspect_ratio", criteria.aspect_ratio, "max")
    _row(2, "Skewness", "skewness", criteria.skewness, "max")
    _row(3, "Jacobian ratio", "jacobian_ratio", criteria.jacobian_ratio, "min")
    _row(5, "Element Quality", "element_quality", criteria.element_quality, "min")
    _row(6, "Maximum Corner Angle", "max_corner_angle_deg", criteria.max_corner_angle_deg, "max", suffix="°")

    if not rows:
        return None

    return {
        "caption": "Table 9: Mesh Quality",
        "headers": ["S. No.", "Parameter", "Acceptance", "Measured"],
        "rows": rows,
    }


def build_loads_summary_table(loads_section: dict[str, Any]) -> dict[str, Any] | None:
    rows: list[list[str]] = []
    index = 1
    for load in loads_section.get("loads") or []:
        caption = load.get("caption") or load.get("load_type") or "Load"
        detail = load.get("load_type") or ""
        magnitude = load.get("magnitude")
        extra = ""
        if load.get("count"):
            extra = f" (×{load['count']})"
        if magnitude is not None:
            detail = f"{detail}: {_fmt(magnitude)}{extra}".strip(": ")
        rows.append([str(index), "Load", caption, detail])
        index += 1

    for bc in loads_section.get("boundary_conditions") or []:
        rows.append(
            [
                str(index),
                "Boundary condition",
                bc.get("caption") or bc.get("bc_type") or "BC",
                bc.get("bc_type") or "",
            ]
        )
        index += 1

    if not rows:
        return None

    return {
        "caption": "Table: Loads & boundary conditions (from CAERep)",
        "headers": ["S. No.", "Kind", "Name", "Details"],
        "rows": rows,
    }


def build_mesh_control_table(modelling: dict[str, Any]) -> dict[str, Any] | None:
    nodes = modelling.get("node_count")
    elements = modelling.get("element_count")
    if nodes is None and elements is None:
        return None
    rows = [
        ["1", "Type of Element", "Tetrahedron and 1D Beam (Solid 187, Beam 188)"],
        ["2", "Type of method", "Patch Conforming"],
        ["3", "Element Size", "5 mm"],
        ["4", "Control Sizing", "Curvature control"],
    ]
    if elements is not None:
        rows.append(["5", "No. of Elements", _fmt(elements)])
    if nodes is not None:
        rows.append(["6", "No. of Nodes", _fmt(nodes)])
    rows.append(["7", "Quality", "1"])
    return {
        "caption": "Table 8: Mesh Control",
        "headers": ["S. No.", "Parameter", "Value"],
        "rows": rows,
    }


def build_fatigue_strength_table(
    design_calcs: dict[str, Any],
    cfg: ProjectConfig,
) -> dict[str, Any] | None:
    effort = design_calcs.get("effort") or []
    if not effort:
        return None

    bolt_header = next((row.get("symbol") for row in effort if row.get("symbol")), "M14X2")
    rows: list[list[str]] = []
    for row in effort:
        label = str(row.get("label") or "")
        value = row.get("value")
        if value is None:
            continue
        rows.append([label, _fmt(value), row.get("source_ref") or ""])

    if not rows:
        return None

    return {
        "caption": "Table 27: Fatigue Strength Calculations",
        "headers": ["Parameter", bolt_header, "Reference"],
        "rows": rows,
    }


def _flange_fe_mass_kg(bodies: list[dict[str, Any]]) -> float | None:
    for body in bodies:
        name = (body.get("name") or "").lower()
        if "cut-extrude" in name or "flange" in name:
            mass = body.get("mass_kg")
            if mass is not None:
                return float(mass)
    for body in bodies:
        if body.get("mass_kg") is not None:
            return float(body["mass_kg"])
    return None


def _report_material(cfg: ProjectConfig) -> dict[str, Any]:
    mat = cfg.materials[0] if cfg.materials else None
    if mat is None:
        return {}
    yield_mpa = mat.yield_mpa
    uts_mpa = mat.uts_mpa
    static_allow = mat.static_allowable_mpa
    fatigue_allow = mat.fatigue_allowable_mpa
    if static_allow is None and yield_mpa and uts_mpa:
        static_allow = min(yield_mpa * (2 / 3), uts_mpa / 3.5)
    if fatigue_allow is None and static_allow is not None:
        fatigue_allow = static_allow / 2
    return {
        "yield_mpa": yield_mpa,
        "uts_mpa": uts_mpa,
        "elongation_pct": mat.elongation_pct,
        "static_allowable_mpa": static_allow,
        "fatigue_allowable_mpa": fatigue_allow,
    }


def _primary_material(
    materials: list[dict[str, Any]],
    cfg: ProjectConfig,
) -> dict[str, Any] | None:
    if materials:
        for mat in materials:
            name = (mat.get("name") or "").lower()
            if "nylon" not in name and "gasket" not in name:
                return mat
        return materials[0]
    if cfg.materials:
        return {"name": cfg.materials[0].name}
    return None


def _split_material_name(name: str) -> tuple[str, str]:
    parts = name.strip().split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return name, ""


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.4g}"
    return str(value)
