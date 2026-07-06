"""Post-figure descriptive paragraphs (EP1581 material stress plots)."""

from __future__ import annotations

import re
from typing import Any

from ansys_report.config import ProjectConfig
from ansys_report.report.table_builders import material_allowable_mpa

_SAFE_TEMPLATES = (
    "The computed maximum stress of {stress:.2f} MPa is found to be below the {allowable_label} stress of "
    "{allowable:.2f} MPa, confirming that the component will perform reliably under the given loading.",
    "The stress distribution shows a peak value of {stress:.3f} MPa at the most critically loaded region, "
    "which is within the acceptable limit of {allowable:.2f} MPa. The design is deemed satisfactory.",
    "From the FEA results, the maximum stress developed is {stress:.3f} MPa against an allowable Yield of "
    "{allowable:g} MPa. Hence the component is safe.",
    "Analysis results confirm that the highest stress value of {stress:.3f} MPa does not breach the allowable "
    "threshold of {allowable:.2f} MPa. The structural integrity is maintained.",
    "The maximum equivalent stress observed is {stress:.3f} MPa, which is within the allowable limit of "
    "{allowable:g} MPa. The design is therefore acceptable.",
    "The equivalent stress contour reveals a maximum value of {stress:.3f} MPa, which is less than the "
    "allowable limit of {allowable:.2f} MPa. The component satisfies the design criteria.",
    "FE analysis indicates a maximum stress of {stress:.3f} MPa at the critical location, which does not "
    "exceed the {allowable_label} of {allowable:.2f} MPa. The design is acceptable.",
)

_UNSAFE_TEMPLATES = (
    "The computed maximum stress of {stress:.2f} MPa exceeds the {allowable_label} stress of {allowable:.2f} MPa. "
    "Design review is required.",
    "Analysis results show a peak stress of {stress:.3f} MPa above the allowable limit of {allowable:.2f} MPa. "
    "The component does not meet the acceptance criteria.",
)


def _normalize_material(name: str | None) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"^mat[_\s]*", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", cleaned.lower())


def _lookup_stress(material_label: str, per_material: dict[str, float]) -> float | None:
    target = _normalize_material(material_label)
    if not target:
        return None
    for name, value in per_material.items():
        if value is None:
            continue
        if _normalize_material(name) == target:
            return float(value)
        if target in _normalize_material(name) or _normalize_material(name) in target:
            return float(value)
    return None


def _resolve_material_name(material_label: str, cfg: ProjectConfig) -> str:
    target = _normalize_material(material_label)
    for mat in cfg.materials:
        normalized = _normalize_material(mat.name)
        if normalized == target or target in normalized or normalized in target:
            return mat.name
    return material_label.replace("MAT_", "").replace("_", " ")


def resolve_material_stress_mpa(material_label: str, data: dict[str, Any]) -> float | None:
    """Peak von-Mises stress (MPa) for a gallery material label."""
    per_material = data.get("per_material") or {}
    stress = _lookup_stress(material_label, per_material)
    if stress is not None:
        return stress

    target = _normalize_material(material_label)
    for body in data.get("per_body") or []:
        material = body.get("material")
        if not material:
            continue
        if _normalize_material(material) == target or target in _normalize_material(material):
            value = body.get("max_stress_mpa")
            if value is not None:
                return float(value)
    return None


def material_stress_figure_description(
    material_label: str,
    data: dict[str, Any],
    cfg: ProjectConfig,
    *,
    allowable_label: str = "permissible",
) -> str | None:
    """EP1581-style paragraph after a per-material von-Mises stress figure."""
    stress = resolve_material_stress_mpa(material_label, data)
    if stress is None:
        return None

    material_name = _resolve_material_name(material_label, cfg)
    allowable = material_allowable_mpa(cfg, material_name)
    if allowable is None:
        return None

    templates = _SAFE_TEMPLATES if stress <= allowable else _UNSAFE_TEMPLATES
    idx = sum(ord(c) for c in material_label) % len(templates)
    return templates[idx].format(
        stress=stress,
        allowable=allowable,
        allowable_label=allowable_label,
    )
