"""Map report figure slots to Mechanical export folder naming conventions."""

from __future__ import annotations

import re
from pathlib import Path

_SHOCK_FOLDER: dict[str, tuple[str, ...]] = {
    "shock_plus_x": ("equivalent_static_analysis_posx", "shock/plus_x", "plus_x/"),
    "shock_plus_y": ("equivalent_static_analysis_posy", "shock/plus_y", "plus_y/"),
    "shock_plus_z": ("equivalent_static_analysis_posz", "shock/plus_z", "plus_z/"),
    "shock_minus_x": ("equivalent_static_analysis_negx", "shock/minus_x", "minus_x/"),
    "shock_minus_y": ("equivalent_static_analysis_negy", "shock/minus_y", "minus_y/"),
    "shock_minus_z": ("equivalent_static_analysis_negz", "shock/minus_z", "minus_z/"),
}

_HARMONIC_FOLDER: dict[str, tuple[str, ...]] = {
    "harmonic_x": (
        "vibration_resistance_analysis_x",
        "harmonic/x/",
        "harmonic_x/",
        "x_direction",
    ),
    "harmonic_y": (
        "vibration_resistance_analysis_y",
        "harmonic/y/",
        "harmonic_y/",
        "y_direction",
    ),
    "harmonic_z": (
        "vibration_resistance_analysis_z",
        "harmonic/z/",
        "harmonic_z/",
        "z_direction",
    ),
}

_FORBIDDEN_FOR_STATIC = ("equivalent_static", "vibration_resistance", "/harmonic/", "/modal/")


def slot_family(slot: str) -> str | None:
    s = slot.lower()
    if s.startswith("shock_"):
        for key in _SHOCK_FOLDER:
            if s.startswith(key + "_"):
                return key
    if s.startswith("harmonic_"):
        for key in _HARMONIC_FOLDER:
            if s.startswith(key + "_"):
                return key
    if s == "modelling_contacts":
        return "connections"
    if s.startswith("static_"):
        return "static"
    if s == "model_orientation_gravity":
        return "static"
    if s.startswith("modal_"):
        return "modal"
    if s.startswith("mesh_"):
        return "mesh"
    if s.startswith("cad_") or s.startswith("geometry_"):
        return "geometry"
    return None


def folder_markers_for_slot(slot: str) -> tuple[str, ...]:
    s = slot.lower()
    family = slot_family(slot)
    if family in _SHOCK_FOLDER:
        return _SHOCK_FOLDER[family]
    if family in _HARMONIC_FOLDER:
        return _HARMONIC_FOLDER[family]
    if family == "connections" or s == "modelling_contacts":
        return ("connections/",)
    if family == "static":
        return ("static_structural",)
    if family == "modal":
        return ("modal/",)
    if s == "cad_isometric":
        return ("geometry/",)
    if s == "cad_section":
        return ("connections/",)
    if s == "geometry_model_orientation":
        return ("coordinate_systems/",)
    if s == "model_orientation_gravity":
        return ("static_structural",)
    if s.startswith("mesh_"):
        return ("mesh/",)
    return ()


def path_allowed_for_slot(slot: str, rel_path: str) -> bool:
    p = rel_path.lower().replace("\\", "/")
    s = slot.lower()

    markers = folder_markers_for_slot(slot)
    if markers:
        if slot_family(slot) == "modal":
            if not p.startswith("modal/"):
                return False
        elif not any(m in p for m in markers):
            return False

    if s.startswith("static_") or s == "model_orientation_gravity":
        if any(bad in p for bad in _FORBIDDEN_FOR_STATIC):
            return False

    if s == "modelling_contacts":
        return "connections/" in p and Path(p).name.lower() != "pressure.png"

    if s.endswith("_location"):
        if "modal_modal" in p:
            return False
        if "acceleration" not in p:
            return False

    family = slot_family(slot)
    if family and family.startswith("shock_"):
        for other, other_markers in _SHOCK_FOLDER.items():
            if other == family:
                continue
            if any(m in p for m in other_markers):
                return False

    return True


def infer_folder_keywords_for_slot(slot: str) -> list[str]:
    markers = folder_markers_for_slot(slot)
    if not markers:
        return []
    primary = markers[0].strip("/").replace("/", "")
    return [primary] if primary else []


def expected_folder_markers(slot: str) -> tuple[str, ...]:
    """Markers used by validation (alias for folder_markers_for_slot)."""
    return folder_markers_for_slot(slot)


def sanitize_analysis_name(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")


def analysis_name_to_family(analysis: str) -> str | None:
    """Map Mechanical analysis tree name to slot family prefix."""
    a = sanitize_analysis_name(analysis)
    if a in {"geometry"}:
        return "geometry"
    if a == "mesh":
        return "mesh"
    if a == "connections":
        return "connections"
    if a == "coordinate_systems":
        return "coordinate_systems"
    if "static_structural" in a or a == "static_structural":
        return "static"
    if a == "modal":
        return "modal"

    for axis in "xyz":
        if f"vibration_resistance_analysis_{axis}" in a:
            return f"harmonic_{axis}"

    for family, markers in _SHOCK_FOLDER.items():
        for marker in markers:
            token = marker.strip("/").split("/")[0]
            if token and token in a:
                return family

    for family, markers in _HARMONIC_FOLDER.items():
        for marker in markers:
            token = marker.strip("/").split("/")[0]
            if token and token in a:
                return family

    return None
