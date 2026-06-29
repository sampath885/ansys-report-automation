"""Build report tables from live project data (RST, CAERep, Excel, config).

Word-exported YAML (``ep2737_reference_tables.yaml`` / ``ep2737_front_matter.yaml``) is
opt-in via ``use_word_table_data`` for regression against the sample report only.
Production builds must use ``use_word_table_data: false``.
"""

from __future__ import annotations

import re
from typing import Any

from pathlib import Path

from ansys_report.config import ProjectConfig
from ansys_report.extract.metadata import top_level_part_name


def build_static_conclusion_table(
    static: dict[str, Any],
    cfg: ProjectConfig,
    *,
    context: dict[str, Any] | None = None,
    reference_tables: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Table 16 — static structural analysis conclusion."""
    per_body = static.get("per_body") or []
    per_material = static.get("per_material") or {}
    if per_body:
        rows = _rows_from_per_body(per_body, cfg)
    elif _dedupe_body_dicts(_bodies_from_context(context)):
        rows = _rows_from_body_metadata(
            _dedupe_body_dicts(_bodies_from_context(context)),
            cfg,
            per_material=per_material,
            default_location=static.get("max_stress_location"),
        )
    else:
        return [_assembly_static_row(static, cfg)]

    if _uses_ep1581_style(cfg):
        rows = _collapse_rows_by_material(rows)
    return rows


def build_shock_conclusion_table(
    shock: dict[str, Any],
    cfg: ProjectConfig,
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Table 23 — shock conclusion (EP1581: one row per direction × material)."""
    rows: list[dict[str, Any]] = []
    sr_no = 1
    fallback_bodies = _dedupe_body_dicts(_bodies_from_context(context))
    ep1581 = _uses_ep1581_style(cfg)

    for direction in shock.get("directions") or []:
        label = direction.get("direction") or "?"
        per_body = direction.get("per_body") or []

        if per_body:
            targets = _group_per_body_by_material(per_body) if ep1581 else per_body
            for body in targets:
                material = body.get("material") or _primary_material(cfg)
                stress = body.get("max_stress_mpa")
                allowable = material_allowable_mpa(cfg, material)
                rows.append(
                    {
                        "sr_no": sr_no,
                        "direction": label,
                        "material": material,
                        "location": body.get("location") or body.get("body_name") or label,
                        "stress_mpa": stress,
                        "allowable_mpa": allowable,
                        "remarks": _stress_remarks(stress, allowable),
                    }
                )
                sr_no += 1
            continue

        if fallback_bodies:
            targets = _unique_material_bodies(fallback_bodies) if ep1581 else fallback_bodies
            dir_per_material = direction.get("per_material") or {}
            for body in targets:
                material = body.get("material") or _primary_material(cfg)
                if dir_per_material:
                    stress = dir_per_material.get(material)
                elif ep1581:
                    stress = None
                else:
                    stress = direction.get("max_stress_mpa")
                allowable = material_allowable_mpa(cfg, material)
                rows.append(
                    {
                        "sr_no": sr_no,
                        "direction": label,
                        "material": material,
                        "location": body.get("name") or label,
                        "stress_mpa": stress,
                        "allowable_mpa": allowable,
                        "remarks": _stress_remarks(stress, allowable),
                    }
                )
                sr_no += 1
            continue

        material = _primary_material(cfg)
        stress = direction.get("max_stress_mpa")
        allowable = material_allowable_mpa(cfg, material)
        rows.append(
            {
                "sr_no": sr_no,
                "direction": label,
                "material": material,
                "location": direction.get("max_stress_location") or "Assembly",
                "stress_mpa": stress,
                "allowable_mpa": allowable,
                "remarks": _stress_remarks(stress, allowable),
            }
        )
        sr_no += 1

    return rows


def build_vibration_conclusion_table(
    context: dict[str, Any],
    cfg: ProjectConfig | None = None,
) -> list[dict[str, Any]]:
    """Summary table for vibration resistance conclusion."""
    ep1581 = cfg is None or _uses_ep1581_style(cfg)
    component = _assembly_component_name(context)
    material = cfg_material_name(context)

    rows: list[dict[str, Any]] = []
    sr_no = 1
    for key in ("harmonic_x", "harmonic_y", "harmonic_z"):
        block = context.get(key)
        if not block:
            continue
        direction = block.get("direction") or key.split("_")[-1].upper()

        if ep1581:
            targets = [{"name": component, "material": material}]
        else:
            bodies = _dedupe_body_dicts(_bodies_from_context(context))
            if not bodies:
                bodies = [{"name": component, "material": material}]
            per_body = block.get("per_body") or []
            targets = per_body if per_body else bodies

        for body in targets:
            rows.append(
                {
                    "sr_no": sr_no,
                    "analysis": f"Harmonic Response {direction}",
                    "component": body.get("body_name") or body.get("name") or component,
                    "material": body.get("material") or material,
                    "peak_frequency_hz": block.get("peak_frequency_hz"),
                    "peak_displacement_mm": block.get("peak_displacement_mm"),
                    "remarks": _harmonic_remark(block),
                }
            )
            sr_no += 1
    return rows


def cfg_material_name(context: dict[str, Any]) -> str:
    equipment = context.get("equipment") or {}
    names = equipment.get("material_names") or []
    return names[0] if names else "ASTM A182 F321"


def enrich_context_tables(context: dict[str, Any], cfg: ProjectConfig) -> None:
    """Attach derived table payloads for the section content matrix."""
    from ansys_report.report.live_table_builders import build_live_reference_tables

    refs: dict[str, Any] = {}
    refs.update(load_standards_tables(cfg))
    refs.update(load_report_defaults(cfg))
    refs.update(build_live_reference_tables(context, cfg))
    if cfg.use_word_table_data:
        refs.update(load_reference_tables(cfg))
        refs.update(load_front_matter_tables(cfg))
    context["reference_tables"] = refs

    static = context.get("static")
    if static:
        static["conclusion_table"] = build_static_conclusion_table(static, cfg, context=context)

    shock = context.get("shock")
    if shock:
        shock["conclusion_table"] = build_shock_conclusion_table(shock, cfg, context=context)

    from ansys_report.narrative.harmonic_merge import (
        HARMONIC_SECTION_KEYS,
        merge_harmonic_conclusion_narrative,
    )

    enabled = set(cfg.sections_enabled or [])
    merged = merge_harmonic_conclusion_narrative(context, enabled_sections=enabled)
    vib = build_vibration_conclusion_table(context, cfg)
    if vib or any(key in enabled and key in context for key in HARMONIC_SECTION_KEYS):
        context["vibration_conclusion"] = {"rows": vib, "narrative": merged}

    if not context.get("methodology"):
        from ansys_report.narrative.methodology import build_methodology, polish_methodology

        context["methodology"] = polish_methodology(build_methodology(context, cfg))


def load_standards_tables(cfg: ProjectConfig) -> dict[str, Any]:
    path = getattr(cfg, "standards_tables_path", None)
    if path is None or not Path(path).exists():
        default = Path(__file__).resolve().parents[3] / "config" / "ep2737_standards_tables.yaml"
        path = default if default.exists() else None
    else:
        path = Path(path)
    if path is None or not path.exists():
        return {}
    import yaml

    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_report_defaults(cfg: ProjectConfig) -> dict[str, Any]:
    path = getattr(cfg, "report_defaults_path", None)
    if path is None or not Path(path).exists():
        default = Path(__file__).resolve().parents[3] / "config" / "ep2737_report_defaults.yaml"
        path = default if default.exists() else None
    else:
        path = Path(path)
    if path is None or not path.exists():
        return {}
    import yaml

    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_reference_tables(cfg: ProjectConfig) -> dict[str, Any]:
    path = getattr(cfg, "reference_tables_path", None)
    if path is None or not Path(path).exists():
        default = Path(__file__).resolve().parents[3] / "config" / "ep2737_reference_tables.yaml"
        path = default if default.exists() else None
    else:
        path = Path(path)
    if path is None or not path.exists():
        return {}
    import yaml

    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_front_matter_tables(cfg: ProjectConfig) -> dict[str, Any]:
    default = Path(__file__).resolve().parents[3] / "config" / "ep2737_front_matter.yaml"
    if not default.exists():
        return {}
    import yaml

    with default.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _uses_ep1581_style(cfg: ProjectConfig) -> bool:
    style = (cfg.static.conclusion_table_style or "ep1581").lower()
    return style != "per_body"


def _assembly_component_name(context: dict[str, Any] | None) -> str:
    if not context:
        return "Assembly"
    if context.get("title"):
        return str(context["title"])
    equipment = context.get("equipment") or {}
    if equipment.get("title"):
        return str(equipment["title"])
    return "Assembly"


def _group_per_body_by_material(per_body: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """EP1581 — one entry per material; location is top-level part at peak stress."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in per_body:
        material = row.get("material") or "—"
        stress = row.get("max_stress_mpa")
        location = top_level_part_name(str(row.get("location") or row.get("body_name") or row.get("name") or "—"))
        prev = merged.get(material)
        if prev is None or (
            stress is not None
            and (prev.get("max_stress_mpa") is None or stress > prev.get("max_stress_mpa"))
        ):
            merged[material] = {
                **row,
                "material": material,
                "body_name": location,
                "location": location,
            }
            if material not in order:
                order.append(material)
    return [merged[material] for material in order]


def _unique_material_bodies(bodies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str | None] = set()
    unique: list[dict[str, Any]] = []
    for body in bodies:
        material = body.get("material")
        if material in seen:
            continue
        seen.add(material)
        unique.append(
            {
                **body,
                "name": top_level_part_name(str(body.get("name") or "")),
            }
        )
    return unique


def _collapse_rows_by_material(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse built table rows to one row per material (keep highest stress)."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        material = str(row.get("material") or "—")
        stress = row.get("stress_mpa")
        prev = merged.get(material)
        if prev is None or (
            stress is not None
            and (prev.get("stress_mpa") is None or stress > prev.get("stress_mpa"))
        ):
            merged[material] = dict(row)
            if material not in order:
                order.append(material)
    return [{**merged[material], "sr_no": idx} for idx, material in enumerate(order, start=1)]


def _assembly_static_row(static: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
    stress = static.get("max_stress_mpa")
    material = _primary_material(cfg)
    allowable = material_allowable_mpa(cfg, material)
    location = static.get("max_stress_location") or "Welded Plane Pipe Flange Assembly"
    return {
        "sr_no": 1,
        "material": material,
        "location": location,
        "stress_mpa": stress,
        "allowable_mpa": allowable,
        "remarks": _stress_remarks(stress, allowable),
    }


def _rows_from_per_body(per_body: list[dict[str, Any]], cfg: ProjectConfig) -> list[dict[str, Any]]:
    grouped = _group_per_body_by_material(per_body) if _uses_ep1581_style(cfg) else per_body
    rows: list[dict[str, Any]] = []
    for idx, body in enumerate(grouped, start=1):
        material = body.get("material") or _primary_material(cfg)
        stress = body.get("max_stress_mpa")
        allowable = material_allowable_mpa(cfg, material)
        rows.append(
            {
                "sr_no": idx,
                "material": material,
                "location": body.get("location") or body.get("body_name") or "—",
                "stress_mpa": stress,
                "allowable_mpa": allowable,
                "remarks": _stress_remarks(stress, allowable),
            }
        )
    return rows


def _rows_from_body_metadata(
    bodies: list[dict[str, Any]],
    cfg: ProjectConfig,
    *,
    per_material: dict[str, float] | None = None,
    default_location: str | None = None,
) -> list[dict[str, Any]]:
    targets = _unique_material_bodies(bodies) if _uses_ep1581_style(cfg) else bodies
    per_material = per_material or {}
    rows: list[dict[str, Any]] = []
    for idx, body in enumerate(targets, start=1):
        material = body.get("material") or _primary_material(cfg)
        allowable = material_allowable_mpa(cfg, material)
        stress_mpa = per_material.get(material) if material in per_material else None
        rows.append(
            {
                "sr_no": idx,
                "material": material,
                "location": body.get("name") or default_location or "—",
                "stress_mpa": stress_mpa,
                "allowable_mpa": allowable,
                "remarks": _stress_remarks(stress_mpa, allowable),
            }
        )
    return rows


def _bodies_from_context(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not context:
        return []
    equipment = context.get("equipment") or {}
    bodies = equipment.get("bodies") or []
    if bodies:
        return list(bodies)
    static_analysis = context.get("static_analysis") or {}
    return list(static_analysis.get("bodies") or [])


def _dedupe_body_dicts(bodies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str | None], dict[str, Any]] = {}
    order: list[tuple[str, str | None]] = []
    for body in bodies:
        name = top_level_part_name(str(body.get("name") or body.get("body_name") or ""))
        material = body.get("material")
        key = (name, material)
        if key in grouped:
            continue
        normalized = dict(body)
        normalized["name"] = name
        grouped[key] = normalized
        order.append(key)
    return [grouped[key] for key in order]


def _primary_material(cfg: ProjectConfig) -> str:
    return cfg.materials[0].name if cfg.materials else "—"


def material_allowable_mpa(cfg: ProjectConfig, material_name: str | None) -> float | None:
    if material_name:
        target = _normalize_material(material_name)
        for mat in cfg.materials:
            if _materials_match(target, _normalize_material(mat.name)):
                if mat.static_allowable_mpa is not None:
                    return mat.static_allowable_mpa
                if mat.yield_mpa:
                    return mat.yield_mpa / cfg.static.fos_target
    return _static_allowable_mpa(cfg)


def _static_allowable_mpa(cfg: ProjectConfig) -> float | None:
    if cfg.materials and cfg.materials[0].static_allowable_mpa is not None:
        return cfg.materials[0].static_allowable_mpa
    yield_mpa = cfg.primary_yield_mpa
    if yield_mpa is None:
        return None
    return yield_mpa / cfg.static.fos_target


def _normalize_material(name: str | None) -> str:
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _materials_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return left in right or right in left


def _stress_remarks(stress: float | None, allowable: float | None) -> str:
    if stress is None or allowable is None:
        return "Pending stress or allowable value."
    if stress <= allowable:
        return "Stresses less than allowable."
    return "Stresses exceed allowable — review required."


def _harmonic_remark(block: dict[str, Any]) -> str:
    narr = block.get("narrative") or {}
    verdict = narr.get("verdict", "PASS")
    if verdict == "FAIL":
        return "Not acceptable — review required."
    if verdict == "CAUTION":
        return "Review against vibration specification."
    return "Within configured assessment limits."
