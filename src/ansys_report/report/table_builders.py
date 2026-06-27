"""Build report tables from live project data (RST, CAERep, Excel, config).

Word-exported YAML (``ep2737_reference_tables.yaml`` / ``ep2737_front_matter.yaml``) is
opt-in via ``use_word_table_data`` for regression against the sample report only.
Production builds must use ``use_word_table_data: false``.
"""

from __future__ import annotations

from typing import Any

from pathlib import Path

from ansys_report.config import ProjectConfig


def build_static_conclusion_table(
    static: dict[str, Any],
    cfg: ProjectConfig,
    *,
    reference_tables: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Table 16 — static structural analysis conclusion from live static extraction."""
    stress = static.get("max_stress_mpa")
    material = cfg.materials[0].name if cfg.materials else "—"
    allowable = _static_allowable_mpa(cfg)
    remarks = _stress_remarks(stress, allowable)
    location = static.get("max_stress_location") or "Welded Plane Pipe Flange Assembly"
    return [
        {
            "sr_no": 1,
            "material": material,
            "location": location,
            "stress_mpa": stress,
            "allowable_mpa": allowable,
            "remarks": remarks,
        }
    ]


def build_vibration_conclusion_table(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Summary table for vibration resistance conclusion."""
    rows: list[dict[str, Any]] = []
    material = cfg_material_name(context)
    for idx, key in enumerate(("harmonic_x", "harmonic_y", "harmonic_z"), start=1):
        block = context.get(key)
        if not block:
            continue
        direction = block.get("direction") or key.split("_")[-1].upper()
        rows.append(
            {
                "sr_no": idx,
                "analysis": f"Harmonic Response {direction}",
                "component": "Welded Plane Pipe Flange",
                "material": material,
                "peak_frequency_hz": block.get("peak_frequency_hz"),
                "peak_displacement_mm": block.get("peak_displacement_mm"),
                "remarks": _harmonic_remark(block),
            }
        )
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
        static["conclusion_table"] = build_static_conclusion_table(static, cfg)

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


def _static_allowable_mpa(cfg: ProjectConfig) -> float | None:
    if cfg.materials and cfg.materials[0].static_allowable_mpa is not None:
        return cfg.materials[0].static_allowable_mpa
    yield_mpa = cfg.primary_yield_mpa
    if yield_mpa is None:
        return None
    return yield_mpa / cfg.static.fos_target


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
