"""Infer analysis physics and slot mappings from export manifest/log (no per-project hardcoding)."""

from __future__ import annotations

from pathlib import Path

from ansys_report.images.component_figures import shock_analysis_folder
from ansys_report.images.slot_semantics import (
    SlotSemantics,
    analysis_root_from_rel_path,
    parse_slot_semantics,
)

_AXIS_FROM_TEXT = (
    ("x", (" response_x", " response x", "_x", "-x", "+x", "horizontal")),
    ("y", (" response_y", " response y", "_y", "-y", "+y", "vertical")),
    ("z", (" response_z", " response z", "_z", "-z", "+z", "longitud")),
)

_SIGN_MINUS = ("-x", "-y", "-z", "minus", "negative", " neg")
_SIGN_PLUS = ("+x", "+y", "+z", "plus", "positive", " pos")


def classify_export_folder(entry: dict) -> dict:
    """Classify one export folder from manifest/log analysis names (export tree is truth)."""
    folder = str(entry.get("folder") or "")
    names = " ".join(entry.get("analysis_names") or [])
    keys = " ".join(str(k) for k in entry.get("manifest_keys") or [])
    text = f"{folder} {names} {keys}".lower()
    names_lower = names.lower()

    physics = "unknown"
    axis: str | None = None
    sign: str | None = None

    if "modal" in text and "transient" not in text and "harmonic" not in text:
        physics = "modal"
    elif "static structural" in names_lower or (
        "static" in names_lower
        and "equivalent" not in names_lower
        and "transient" not in names_lower
        and "harmonic" not in names_lower
    ):
        physics = "static"
    elif _is_harmonic_response(names_lower, text):
        physics = "harmonic_vibration"
        axis = _detect_axis(f"{names_lower} {folder.lower()}")
    elif _is_transient_shock(names_lower, text):
        physics = "shock_transient"
        axis = _detect_axis(f"{names_lower} {folder.lower()}")
        sign = _detect_sign(f"{names_lower} {folder.lower()}") or "minus"

    canonical_gallery: str | None = None
    shock_plus_gallery: str | None = None
    if physics == "harmonic_vibration" and axis:
        canonical_gallery = f"vibration_resistance_analysis_{axis}"
        shock_plus_gallery = shock_analysis_folder(f"plus_{axis}")
    elif physics == "shock_transient" and axis and sign:
        canonical_gallery = shock_analysis_folder(f"{sign}_{axis}")
    elif physics == "static":
        canonical_gallery = "static_structural"

    return {
        "physics": physics,
        "axis": axis,
        "sign": sign,
        "canonical_gallery_folder": canonical_gallery,
        "shock_plus_gallery_folder": shock_plus_gallery,
    }


def enrich_export_context(context: dict) -> dict:
    """Attach per-folder classification to export context."""
    folders = []
    for entry in context.get("analysis_folders") or []:
        item = dict(entry)
        item["classification"] = classify_export_folder(item)
        folders.append(item)
    context = dict(context)
    context["analysis_folders"] = folders
    return context


def build_folder_aliases_from_export_context(context: dict) -> dict[str, str]:
    """
    Map EP1581 canonical gallery folder names to actual export folders.

    Harmonic Response exports serve both §7.3 harmonic galleries and §7.4 shock +X/+Y/+Z.
    Transient exports serve §7.4 shock -X/-Y/-Z.
    """
    aliases: dict[str, str] = {}
    for entry in context.get("analysis_folders") or []:
        cls = entry.get("classification") or {}
        folder = entry.get("folder")
        if not folder:
            continue
        canonical = cls.get("canonical_gallery_folder")
        if canonical:
            aliases[str(canonical)] = str(folder)
        shock_plus = cls.get("shock_plus_gallery_folder")
        if shock_plus:
            aliases[str(shock_plus)] = str(folder)
    return aliases


def infer_semantic_mappings_from_context(
    context: dict,
    pending_slots: list[str],
    candidate_paths: list[str],
) -> dict[str, str]:
    """
    Deterministic slot → path map from export metadata.

    Uses analysis_names from manifest/log, not EP2741 folder spellings.
    """
    by_physics: dict[tuple[str, str | None, str | None], str] = {}
    for entry in context.get("analysis_folders") or []:
        cls = entry.get("classification") or {}
        physics = cls.get("physics")
        if physics in {"harmonic_vibration", "shock_transient", "static"}:
            by_physics[(physics, cls.get("axis"), cls.get("sign"))] = str(entry["folder"])

    path_index = _index_solution_paths(candidate_paths)
    assignments: dict[str, str] = {}

    for slot in pending_slots:
        sem = parse_slot_semantics(slot)
        if sem is None:
            continue
        folder = _folder_for_slot(sem, by_physics)
        if not folder:
            continue
        rel = _pick_path_for_slot(slot, sem, folder, path_index)
        if rel:
            assignments[slot] = rel

    return assignments


def _folder_for_slot(
    sem: SlotSemantics,
    by_physics: dict[tuple[str, str | None, str | None], str],
) -> str | None:
    if sem.analysis_type == "static":
        return by_physics.get(("static", None, None))
    if sem.analysis_type == "harmonic":
        return by_physics.get(("harmonic_vibration", sem.axis, None))
    if sem.analysis_type == "shock" and sem.axis and sem.sign:
        if sem.sign == "plus":
            return by_physics.get(("harmonic_vibration", sem.axis, None))
        return by_physics.get(("shock_transient", sem.axis, sem.sign))
    return None


def _index_solution_paths(candidate_paths: list[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for rel in candidate_paths:
        folder = analysis_root_from_rel_path(rel)
        index.setdefault(folder, []).append(rel)
    return index


def _pick_path_for_slot(
    slot: str,
    sem: SlotSemantics,
    folder: str,
    path_index: dict[str, list[str]],
) -> str | None:
    paths = path_index.get(folder) or []
    if not paths:
        return None

    hints = [h.lower() for h in sem.filename_hints]
    kind = sem.result_kind.lower()

    scored: list[tuple[int, str]] = []
    for rel in paths:
        name = Path(rel).name.lower()
        score = 0
        if any(h in name for h in hints):
            score += 10
        if kind in {"deformation", "total_deformation"} and "deformation" in name:
            score += 8
        if kind in {"stress_asm", "vonmises_stress"} and "stress" in name and "flange" not in name:
            score += 8
        if kind in {"stress_flange", "vonmises_flange"} and "flange" in name:
            score += 8
        if kind == "location" and "acceleration" in name:
            score += 8
        if kind == "accel_plot" and ("frequency" in name or "response" in name):
            score += 8
        if score > 0:
            scored.append((score, rel))

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def _is_harmonic_response(names_lower: str, text: str) -> bool:
    if "harmonic response" in names_lower:
        return True
    if "harmonic" in names_lower and "transient" not in names_lower:
        return True
    return "harmonic_response" in text or (
        "harmonic" in text
        and "transient" not in text
        and any(k.startswith("vibration_") for k in text.split())
    )


def _is_transient_shock(names_lower: str, text: str) -> bool:
    if names_lower.startswith("transient") or "transient_" in text:
        return True
    return "transient" in names_lower and "harmonic" not in names_lower


def _detect_axis(text: str) -> str | None:
    for axis, markers in _AXIS_FROM_TEXT:
        if any(marker in text for marker in markers):
            return axis
    return None


def _detect_sign(text: str) -> str | None:
    has_minus = any(token in text for token in _SIGN_MINUS)
    has_plus = any(token in text for token in _SIGN_PLUS)
    if has_minus and not has_plus:
        return "minus"
    if has_plus and not has_minus:
        return "plus"
    return None
