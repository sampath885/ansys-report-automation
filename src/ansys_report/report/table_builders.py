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


def build_static_conclusion_table(
    static: dict[str, Any],
    cfg: ProjectConfig,
    *,
    context: dict[str, Any] | None = None,
    reference_tables: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Table 16 — static structural analysis conclusion (one row per body when available)."""
    per_body = static.get("per_body") or []
    if per_body:
        return _rows_from_per_body(per_body, cfg)

    bodies = _dedupe_body_dicts(_bodies_from_context(context))
    if bodies:
        return _rows_from_body_metadata(
            bodies,
            cfg,
            stress_mpa=static.get("max_stress_mpa"),
            default_location=static.get("max_stress_location"),
        )

    return [_assembly_static_row(static, cfg)]


def build_shock_conclusion_table(
    shock: dict[str, Any],
    cfg: ProjectConfig,
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Table 23 — per-direction/per-body shock conclusion (EP1581 Table 28 style)."""
    rows: list[dict[str, Any]] = []
    sr_no = 1
    fallback_bodies = _dedupe_body_dicts(_bodies_from_context(context))

    for direction in shock.get("directions") or []:
        label = direction.get("direction") or "?"
        per_body = direction.get("per_body") or []
        if per_body:
            for body in per_body:
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
            for body in fallback_bodies:
                material = body.get("material") or _primary_material(cfg)
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


def build_vibration_conclusion_table(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Summary table for vibration resistance conclusion (per body × enabled axis)."""
    bodies = _dedupe_body_dicts(_bodies_from_context(context))
    if not bodies:
        bodies = [{"name": "Welded Plane Pipe Flange", "material": cfg_material_name(context)}]

    rows: list[dict[str, Any]] = []
    sr_no = 1
    for key in ("harmonic_x", "harmonic_y", "harmonic_z"):
        block = context.get(key)
        if not block:
            continue
        direction = block.get("direction") or key.split("_")[-1].upper()
        per_body = block.get("per_body") or []
        targets = per_body if per_body else bodies
        for body in targets:
            component = body.get("body_name") or body.get("name") or "Component"
            material = body.get("material") or cfg_material_name(context)
            rows.append(
                {
                    "sr_no": sr_no,
                    "analysis": f"Harmonic Response {direction}",
                    "component": component,
                    "material": material,
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
    vib = build_vibration_conclusion_table(context)
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
    rows: list[dict[str, Any]] = []
    for idx, body in enumerate(per_body, start=1):
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
    stress_mpa: float | None,
    default_location: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, body in enumerate(bodies, start=1):
        material = body.get("material") or _primary_material(cfg)
        allowable = material_allowable_mpa(cfg, material)
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
    seen: set[tuple[str, str | None]] = set()
    unique: list[dict[str, Any]] = []
    for body in bodies:
        name = str(body.get("name") or "")
        material = body.get("material")
        key = (name, material)
        if key in seen:
            continue
        seen.add(key)
        unique.append(body)
    return unique


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
