"""Load Mechanical worksheet Result Summary exports (primary result source)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ansys_report.extract.dpf_body_stress import _canonical_material_key, _materials_match
from ansys_report.models import BodyMetadata, BodyStressRow, HarmonicPeakResult, ProjectInventory, ResultSummary, ResultSummaryRow, StaticResult

logger = logging.getLogger(__name__)

RESULT_SUMMARY_SUBDIR = "result_summaries"
MANIFEST_NAME = "manifest.json"

# Export filename stem → inventory system key (matches EP2741 image export folders).
FILENAME_TO_SYSTEM_KEY: dict[str, str] = {
    "static_structural": "static_structural",
    "static": "static_structural",
    "sys": "static_structural",
    "modal": "modal",
    "modal_analysis": "modal",
    "sys-1": "modal",
    "vibration_resistance_analysis_x": "vibration_x",
    "vibration_resistance_analysis_y": "vibration_y",
    "vibration_resistance_analysis_z": "vibration_z",
    "harmonic_x": "vibration_x",
    "harmonic_y": "vibration_y",
    "harmonic_z": "vibration_z",
    "equivalent_static_analysis_posx": "shock_plus_x",
    "equivalent_static_analysis_posy": "shock_plus_y",
    "equivalent_static_analysis_posz": "shock_plus_z",
    "equivalent_static_analysis_negx": "shock_minus_x",
    "equivalent_static_analysis_negy": "shock_minus_y",
    "equivalent_static_analysis_negz": "shock_minus_z",
    "shock_plus_x": "shock_plus_x",
    "shock_plus_y": "shock_plus_y",
    "shock_plus_z": "shock_plus_z",
    "shock_minus_x": "shock_minus_x",
    "shock_minus_y": "shock_minus_y",
    "shock_minus_z": "shock_minus_z",
}

_ASSEMBLY_RESULT_NAMES = frozenset(
    {
        "total deformation",
        "equivalent stress",
        "equivalent von-mises stress",
        "von mises stress",
        "von-mises stress",
    }
)


def discover_result_summaries(image_root: Path) -> dict[str, Path]:
    """Map inventory system keys to Result Summary JSON paths under image_root."""
    root = image_root / RESULT_SUMMARY_SUBDIR
    if not root.is_dir():
        return {}

    mapped: dict[str, Path] = {}
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest.get("summaries") or []:
                system_key = entry.get("system_key")
                rel = entry.get("file")
                if not system_key or not rel:
                    continue
                path = (root / rel).resolve()
                if path.is_file():
                    mapped[str(system_key)] = path
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read result summary manifest: %s", exc)

    for path in sorted(root.glob("*.json")):
        if path.name == MANIFEST_NAME:
            continue
        system_key = _system_key_from_filename(path.stem)
        if system_key and system_key not in mapped:
            mapped[system_key] = path.resolve()

    return mapped


def load_result_summary(path: Path) -> ResultSummary | None:
    """Parse one exported Result Summary JSON file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load result summary %s: %s", path, exc)
        return None

    rows: list[ResultSummaryRow] = []
    for raw in payload.get("rows") or []:
        rows.append(
            ResultSummaryRow(
                result=str(raw.get("result") or ""),
                minimum=_parse_float(raw.get("minimum")),
                maximum=_parse_float(raw.get("maximum")),
                unit=_clean_unit(raw.get("unit")),
                time_s=_parse_float(raw.get("time_s")),
            )
        )

    return ResultSummary(
        analysis_name=str(payload.get("analysis_name") or path.stem),
        system_key=payload.get("system_key"),
        workbench_folder=payload.get("workbench_folder"),
        time_s=_parse_float(payload.get("time_s")),
        rows=rows,
        source_file=path.resolve(),
    )


def pick_result_summary(inventory: ProjectInventory, system_key: str) -> ResultSummary | None:
    """Resolve and load the Result Summary for a pipeline system key."""
    path = inventory.result_summaries.get(system_key)
    if path is None:
        return None
    summary = load_result_summary(path)
    if summary is None:
        return None
    if not summary.system_key:
        summary.system_key = system_key
    return summary


def summary_to_static_result(
    summary: ResultSummary,
    bodies: list[BodyMetadata] | None = None,
    *,
    yield_mpa: float | None = None,
) -> StaticResult:
    """Convert worksheet Result Summary rows into a StaticResult."""
    result = StaticResult(extraction_source="worksheet_summary")
    manual: list[str] = []

    for row in summary.rows:
        label = row.result.strip()
        if not label:
            continue
        key = label.lower()

        if _is_deformation_row(key, row.unit):
            if row.maximum is not None:
                result.max_deformation_mm = row.maximum
            continue

        if _is_assembly_stress_row(key, row.unit):
            if row.maximum is not None:
                result.max_stress_mpa = row.maximum
            continue

        if row.unit and "mpa" in row.unit.lower() and row.maximum is not None:
            material = display_material_name(label)
            prev = result.per_material.get(material)
            if prev is None or row.maximum > prev:
                result.per_material[material] = row.maximum

    if result.max_stress_mpa is None:
        manual.append("max_stress_mpa")
    if result.max_deformation_mm is None:
        manual.append("max_deformation_mm")

    if bodies:
        result.per_body = _per_body_from_summary(result.per_material, bodies)

    if yield_mpa and result.max_stress_mpa and result.max_stress_mpa > 0:
        result.fos = round(yield_mpa / result.max_stress_mpa, 2)

    result.manual_fields = manual
    return result


def summary_to_harmonic_peak(summary: ResultSummary) -> HarmonicPeakResult:
    """Best-effort harmonic peak from Result Summary (displacement; frequency often absent)."""
    manual: list[str] = []
    peak_mm: float | None = None
    max_stress_mpa: float | None = None
    per_material: dict[str, float] = {}
    per_material_stress: dict[str, float] = {}

    for row in summary.rows:
        key = row.result.lower()
        if row.maximum is None:
            continue
        if _is_deformation_row(key, row.unit):
            if key in _ASSEMBLY_RESULT_NAMES or key == "total deformation":
                peak_mm = row.maximum
            elif row.unit and row.unit.lower() == "mm":
                material = display_material_name(row.result)
                prev = per_material.get(material)
                if prev is None or row.maximum > prev:
                    per_material[material] = row.maximum
            continue
        if _is_assembly_stress_row(key, row.unit):
            max_stress_mpa = row.maximum
            continue
        if row.unit and "mpa" in row.unit.lower():
            material = display_material_name(row.result)
            prev = per_material_stress.get(material)
            if prev is None or row.maximum > prev:
                per_material_stress[material] = row.maximum
            continue
        if row.unit and row.unit.lower() == "mm":
            material = display_material_name(row.result)
            prev = per_material.get(material)
            if prev is None or row.maximum > prev:
                per_material[material] = row.maximum
            continue

    if peak_mm is None and per_material:
        peak_mm = max(per_material.values())

    if peak_mm is None:
        manual.append("peak_displacement_mm")
    manual.append("peak_frequency_hz")

    return HarmonicPeakResult(
        peak_displacement_mm=peak_mm,
        peak_frequency_hz=None,
        per_material=per_material,
        per_material_stress=per_material_stress,
        max_stress_mpa=max_stress_mpa,
        manual_fields=manual,
        extraction_source="worksheet_summary",
    )


def merge_static_results(primary: StaticResult, fallback: StaticResult) -> StaticResult:
    """Prefer worksheet summary; fill gaps from DPF/RST fallback."""
    data = primary.model_dump()
    fb = fallback.model_dump()

    for field in ("max_stress_mpa", "max_deformation_mm", "reaction_force_n", "reaction_moment_nmm", "fos"):
        if data.get(field) is None and fb.get(field) is not None:
            data[field] = fb[field]

    if not data.get("per_material") and fb.get("per_material"):
        data["per_material"] = fb["per_material"]
    elif data.get("per_material") and fb.get("per_material"):
        merged = dict(fb["per_material"])
        merged.update(data["per_material"])
        data["per_material"] = merged

    if not data.get("per_body") and fb.get("per_body"):
        data["per_body"] = fb["per_body"]

    manual = list(data.get("manual_fields") or [])
    for field in fb.get("manual_fields") or []:
        if field not in manual and data.get(field) is None:
            manual.append(field)
    data["manual_fields"] = [f for f in manual if _field_still_missing(f, data)]

    if primary.extraction_source:
        data["extraction_source"] = primary.extraction_source
    elif fallback.extraction_source:
        data["extraction_source"] = fallback.extraction_source
    else:
        data["extraction_source"] = "dpf"

    return StaticResult(**data)


def merge_harmonic_results(primary: HarmonicPeakResult, fallback: HarmonicPeakResult) -> HarmonicPeakResult:
    """Prefer worksheet displacement; fill frequency from DPF when missing."""
    peak_mm = primary.peak_displacement_mm or fallback.peak_displacement_mm
    peak_hz = primary.peak_frequency_hz or fallback.peak_frequency_hz
    max_stress_mpa = primary.max_stress_mpa or fallback.max_stress_mpa
    per_material = dict(fallback.per_material or {})
    per_material.update(primary.per_material or {})
    per_material_stress = dict(fallback.per_material_stress or {})
    per_material_stress.update(primary.per_material_stress or {})
    manual = []
    if peak_mm is None:
        manual.append("peak_displacement_mm")
    if peak_hz is None:
        manual.append("peak_frequency_hz")

    source = primary.extraction_source or fallback.extraction_source or "dpf"
    return HarmonicPeakResult(
        peak_displacement_mm=peak_mm,
        peak_frequency_hz=peak_hz,
        num_frequency_sets=fallback.num_frequency_sets or primary.num_frequency_sets,
        per_material=per_material,
        per_material_stress=per_material_stress,
        max_stress_mpa=max_stress_mpa,
        manual_fields=manual,
        extraction_source=source,
    )


def display_material_name(raw: str) -> str:
    """Mechanical summary labels use underscores; report tables use spaced names."""
    text = raw.strip().replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _per_body_from_summary(
    per_material: dict[str, float],
    bodies: list[BodyMetadata],
) -> list[BodyStressRow]:
    """Attach summary material peaks to CAERep bodies for conclusion tables."""
    if not per_material:
        return []

    rows: list[BodyStressRow] = []
    seen_materials: set[str] = set()

    for body in bodies:
        material = body.material
        if not material:
            continue
        stress = _stress_for_body_material(material, per_material)
        if stress is None:
            continue

        mat_key = _canonical_material_key(material)
        if mat_key in seen_materials:
            continue
        seen_materials.add(mat_key)

        location = body.name.split("\\")[0] if "\\" in body.name else body.name
        rows.append(
            BodyStressRow(
                body_name=body.name,
                material=material,
                max_stress_mpa=stress,
                location=location,
            )
        )

    return rows


def _stress_for_body_material(material: str, per_material: dict[str, float]) -> float | None:
    target = _canonical_material_key(material)
    for name, value in per_material.items():
        if _materials_match(target, _canonical_material_key(name)):
            return value
    return None


def _is_deformation_row(key: str, unit: str | None) -> bool:
    if "deformation" not in key:
        return False
    if unit and unit.lower() in ("mm", "m"):
        return True
    return "total deformation" in key


def _is_assembly_stress_row(key: str, unit: str | None) -> bool:
    if key in _ASSEMBLY_RESULT_NAMES:
        return True
    if "equivalent" in key and "stress" in key:
        return unit is None or "mpa" in unit.lower()
    return False


def _system_key_from_filename(stem: str) -> str | None:
    normalized = stem.lower().strip()
    if normalized in FILENAME_TO_SYSTEM_KEY:
        return FILENAME_TO_SYSTEM_KEY[normalized]
    compact = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if compact in FILENAME_TO_SYSTEM_KEY:
        return FILENAME_TO_SYSTEM_KEY[compact]
    for pattern, key in FILENAME_TO_SYSTEM_KEY.items():
        if pattern in compact or compact in pattern:
            return key
    return None


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_unit(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _field_still_missing(field: str, data: dict[str, Any]) -> bool:
    mapping = {
        "max_stress_mpa": "max_stress_mpa",
        "max_deformation_mm": "max_deformation_mm",
        "reaction_force_n": "reaction_force_n",
        "peak_displacement_mm": "peak_displacement_mm",
        "peak_frequency_hz": "peak_frequency_hz",
        "all": "max_stress_mpa",
    }
    key = mapping.get(field, field)
    return data.get(key) is None
