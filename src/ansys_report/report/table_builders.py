"""Build report tables from live project data (RST, CAERep, Excel, config).

Word-exported YAML (``ep2737_reference_tables.yaml`` / ``ep2737_front_matter.yaml``) is
opt-in via ``use_word_table_data`` for regression against the sample report only.
Production builds must use ``use_word_table_data: false``.
"""

from __future__ import annotations

import re
from typing import Any

from pathlib import Path

from ansys_report.config import ProjectConfig, load_thresholds
from ansys_report.extract.metadata import top_level_part_name


def build_static_conclusion_table(
    static: dict[str, Any],
    cfg: ProjectConfig,
    *,
    context: dict[str, Any] | None = None,
    reference_tables: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Table 16 — static structural analysis conclusion (EP1581: one row per material)."""
    per_body = static.get("per_body") or []
    per_material = static.get("per_material") or {}

    if per_body:
        rows = _rows_from_per_body(per_body, cfg)
    elif per_material:
        rows = _rows_from_per_material(per_material, cfg, context)
    elif _dedupe_body_dicts(_bodies_from_context(context)):
        rows = _rows_from_body_metadata(
            _dedupe_body_dicts(_bodies_from_context(context)),
            cfg,
            per_material=per_material,
            default_location=static.get("max_stress_location"),
        )
    elif static.get("max_stress_mpa") is not None:
        rows = [_assembly_static_row(static, cfg)]
    else:
        rows = []

    if _uses_ep1581_style(cfg) and per_body:
        rows = _collapse_rows_by_material(rows)
    return _filter_rows_with_stress(rows)


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
    """Summary table for vibration resistance conclusion (EP1581-style, real values only)."""
    ep1581 = cfg is None or _uses_ep1581_style(cfg)
    component = _assembly_component_name(context)
    bodies = _dedupe_body_dicts(_bodies_from_context(context))

    rows: list[dict[str, Any]] = []
    sr_no = 1
    for key in ("harmonic_x", "harmonic_y", "harmonic_z"):
        block = context.get(key)
        if not block:
            continue
        direction = block.get("direction") or key.split("_")[-1].upper()
        analysis = f"Harmonic Response {direction}"
        peak_hz = block.get("peak_frequency_hz")
        per_material = block.get("per_material") or {}

        if per_material:
            for material, displacement in per_material.items():
                if displacement is None:
                    continue
                rows.append(
                    _vibration_row(
                        sr_no,
                        analysis,
                        _peak_location_for_material(material, bodies) or component,
                        material,
                        peak_hz,
                        displacement,
                        block,
                    )
                )
                sr_no += 1
            continue

        displacement = block.get("peak_displacement_mm")
        if displacement is None:
            continue

        if ep1581:
            targets = [{"name": component, "material": cfg_material_name(context)}]
        else:
            if not bodies:
                targets = [{"name": component, "material": cfg_material_name(context)}]
            else:
                per_body = block.get("per_body") or []
                targets = per_body if per_body else bodies

        for body in targets:
            rows.append(
                _vibration_row(
                    sr_no,
                    analysis,
                    body.get("body_name") or body.get("name") or component,
                    body.get("material") or cfg_material_name(context),
                    peak_hz,
                    displacement,
                    block,
                )
            )
            sr_no += 1
    return rows


_HARMONIC_DIRECTION_LABELS = {
    "X": "Along X Axis",
    "Y": "Along Y Axis",
    "Z": "Along Z Axis",
}


def build_modal_conclusion_table(
    modal: dict[str, Any],
    cfg: ProjectConfig,
    *,
    resonance_margin_hz: float = 10.0,
) -> list[dict[str, Any]]:
    """EP1581 Table 14 — modal summary with operating-band remarks."""
    operating = _operating_frequency_text(cfg)
    rows: list[dict[str, Any]] = []
    low, high = cfg.operating_freq_hz

    for idx, mode in enumerate(modal.get("modes") or [], start=1):
        freq = mode.get("freq_hz")
        if freq is None:
            continue
        rows.append(
            {
                "sr_no": idx,
                "freq_hz": freq,
                "operating_frequency": operating,
                "dominant_direction": mode.get("dominant_direction") or "—",
                "remark": _modal_remark(freq, low, high, resonance_margin_hz),
            }
        )
    return rows


def build_modal_intro_text(modal: dict[str, Any], cfg: ProjectConfig) -> str:
    """Introductory paragraph for modal conclusions (EP1581 style)."""
    modes = modal.get("modes") or []
    freqs = [m["freq_hz"] for m in modes if m.get("freq_hz") is not None]
    base = (
        "The Modal Analysis is performed to extract the modes of vibration of the structure."
    )
    if not freqs:
        return base

    fundamental = min(freqs)
    text = (
        f"{base} The fundamental frequency of vibration was found to be {fundamental:.3f} Hz."
    )
    shock_threshold = getattr(getattr(cfg, "modal", None), "shock_approach_threshold_hz", None) or 160.0
    if fundamental < shock_threshold:
        text += (
            f" As this is less than {shock_threshold:g} Hz, the Transient Shock approach "
            f"will be used to perform the Shock Analysis."
        )
    else:
        text += (
            f" The operating frequency range is {_operating_frequency_text(cfg)}. "
            f"Refer to the modal summary table for mode-by-mode assessment."
        )
    return text


def build_harmonic_stress_conclusion_table(
    context: dict[str, Any],
    cfg: ProjectConfig,
) -> list[dict[str, Any]]:
    """EP1581 Table 28 — harmonic stress by direction × material."""
    bodies = _dedupe_body_dicts(_bodies_from_context(context))
    component = _assembly_component_name(context)
    rows: list[dict[str, Any]] = []
    sr_no = 1

    for key in ("harmonic_x", "harmonic_y", "harmonic_z"):
        block = context.get(key)
        if not block:
            continue
        direction = str(block.get("direction") or key.split("_")[-1].upper())
        dir_label = _HARMONIC_DIRECTION_LABELS.get(direction, f"Along {direction} Axis")
        per_material = block.get("per_material_stress") or {}

        if not per_material:
            continue

        for material, stress in per_material.items():
            if stress is None:
                continue
            allowable = material_allowable_mpa(cfg, material)
            rows.append(
                {
                    "sr_no": sr_no,
                    "direction": dir_label,
                    "material": material,
                    "location": _peak_location_for_material(material, bodies) or component,
                    "stress_mpa": stress,
                    "allowable_mpa": allowable,
                    "remarks": _stress_remarks(stress, allowable),
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

    modal = context.get("modal")
    if modal:
        thresholds = load_thresholds(cfg.thresholds_path)
        modal["summary_table"] = build_modal_conclusion_table(
            modal,
            cfg,
            resonance_margin_hz=thresholds.modal.resonance_margin_hz,
        )
        modal["intro_text"] = build_modal_intro_text(modal, cfg)

    from ansys_report.narrative.harmonic_merge import (
        HARMONIC_SECTION_KEYS,
        merge_harmonic_conclusion_narrative,
    )

    enabled = set(cfg.sections_enabled or [])
    merged = merge_harmonic_conclusion_narrative(context, enabled_sections=enabled)
    vib = build_vibration_conclusion_table(context, cfg)
    stress_table = build_harmonic_stress_conclusion_table(context, cfg)
    if _uses_ep1581_style(cfg):
        merged = {**merged, "observations": []}
    if vib or stress_table or any(key in enabled and key in context for key in HARMONIC_SECTION_KEYS):
        context["vibration_conclusion"] = {
            "rows": vib,
            "stress_table": stress_table,
            "narrative": merged,
        }

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


def _rows_from_per_material(
    per_material: dict[str, float],
    cfg: ProjectConfig,
    context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """One conclusion row per material from worksheet Result Summary."""
    bodies = _dedupe_body_dicts(_bodies_from_context(context))
    rows: list[dict[str, Any]] = []
    for idx, (material, stress) in enumerate(per_material.items(), start=1):
        if stress is None:
            continue
        allowable = material_allowable_mpa(cfg, material)
        rows.append(
            {
                "sr_no": idx,
                "material": material,
                "location": _peak_location_for_material(material, bodies)
                or _assembly_component_name(context),
                "stress_mpa": stress,
                "allowable_mpa": allowable,
                "remarks": _stress_remarks(stress, allowable),
            }
        )
    return rows


def _peak_location_for_material(material: str, bodies: list[dict[str, Any]]) -> str | None:
    """Top-level part name for a material (EP1581 'Maximum occurs on' column)."""
    target = _normalize_material(material)
    for body in bodies:
        body_mat = body.get("material")
        if not body_mat or not _materials_match(target, _normalize_material(body_mat)):
            continue
        name = body.get("name") or body.get("body_name") or ""
        if name:
            return top_level_part_name(str(name))
    return None


def _filter_rows_with_stress(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop placeholder rows — only include materials with extracted stress."""
    kept = [row for row in rows if row.get("stress_mpa") is not None]
    return [{**row, "sr_no": idx} for idx, row in enumerate(kept, start=1)]


def _vibration_row(
    sr_no: int,
    analysis: str,
    component: str,
    material: str,
    peak_hz: float | None,
    displacement: float,
    block: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sr_no": sr_no,
        "analysis": analysis,
        "component": component,
        "material": material,
        "peak_frequency_hz": peak_hz,
        "peak_displacement_mm": displacement,
        "remarks": _harmonic_remark(block, displacement_mm=displacement),
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
        stress_mpa = _resolve_material_stress(material, per_material)
        if stress_mpa is None:
            continue
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


def _resolve_material_stress(material: str, per_material: dict[str, float]) -> float | None:
    if not per_material:
        return None
    target = _normalize_material(material)
    for name, value in per_material.items():
        if _materials_match(target, _normalize_material(name)):
            return value
    return None


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


def _harmonic_remark(block: dict[str, Any], *, displacement_mm: float | None = None) -> str:
    disp = displacement_mm if displacement_mm is not None else block.get("peak_displacement_mm")
    if disp is None:
        return ""
    narr = block.get("narrative") or {}
    verdict = narr.get("verdict", "PASS")
    if verdict == "FAIL":
        return "Not acceptable — review required."
    if verdict == "CAUTION":
        return "Review against vibration specification."
    return "Within configured assessment limits."


def _operating_frequency_text(cfg: ProjectConfig) -> str:
    low, high = cfg.operating_freq_hz

    def _fmt(value: float) -> str:
        return str(int(value)) if value == int(value) else str(value)

    return f"{_fmt(low)} to {_fmt(high)} Hz"


def _modal_remark(freq_hz: float, low: float, high: float, margin: float) -> str:
    if (low - margin) <= freq_hz <= (high + margin):
        return "Within or near operating frequency — resonance risk."
    return "Not in or near operating Frequency"
