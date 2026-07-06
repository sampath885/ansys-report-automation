"""Map report figure slots to Mechanical export folder naming conventions."""

from __future__ import annotations

import re
from pathlib import Path

_STATIC_FOLDERS = (
    "static_structural",
    "/static/",
    "static_structural_analysis",
)

_SHOCK_FOLDER: dict[str, tuple[str, ...]] = {
    "shock_plus_x": (
        "equivalent_static_analysis_posx",
        "equivalent_static_analysis_plus_x",
        "equivalent_static_posx",
        "shock_plus_x",
        "shock/plus_x",
        "plus_x/",
        "posx",
    ),
    "shock_plus_y": (
        "equivalent_static_analysis_posy",
        "equivalent_static_analysis_plus_y",
        "equivalent_static_posy",
        "shock_plus_y",
        "shock/plus_y",
        "plus_y/",
        "posy",
    ),
    "shock_plus_z": (
        "equivalent_static_analysis_posz",
        "equivalent_static_analysis_plus_z",
        "equivalent_static_posz",
        "shock_plus_z",
        "shock/plus_z",
        "plus_z/",
        "posz",
    ),
    "shock_minus_x": (
        "equivalent_static_analysis_negx",
        "equivalent_static_analysis_minus_x",
        "equivalent_static_negx",
        "shock_minus_x",
        "shock/minus_x",
        "minus_x/",
        "negx",
        "transient_horizontal",
        "horizontal_-x",
        "transient_-x",
        "transient/minus_x",
    ),
    "shock_minus_y": (
        "equivalent_static_analysis_negy",
        "equivalent_static_analysis_minus_y",
        "equivalent_static_negy",
        "shock_minus_y",
        "shock/minus_y",
        "minus_y/",
        "negy",
        "transient_vertical",
        "vertical_-y",
        "transient_-y",
        "transient/minus_y",
    ),
    "shock_minus_z": (
        "equivalent_static_analysis_negz",
        "equivalent_static_analysis_minus_z",
        "equivalent_static_negz",
        "shock_minus_z",
        "shock/minus_z",
        "minus_z/",
        "negz",
        "transient_longitudional",
        "transient_longitudinal",
        "longitudional_-z",
        "longitudinal_-z",
        "transient_-z",
        "transient/minus_z",
    ),
}

_HARMONIC_FOLDER: dict[str, tuple[str, ...]] = {
    "harmonic_x": (
        "vibration_resistance_analysis_x",
        "harmonic_response_x",
        "harmonic_response_x_direction",
        "harmonic_x_direction",
        "harmonic/x/",
        "harmonic_x/",
        "x_direction",
    ),
    "harmonic_y": (
        "vibration_resistance_analysis_y",
        "harmonic_response_y",
        "harmonic_response_y_direction",
        "harmonic_y_direction",
        "harmonic/y/",
        "harmonic_y/",
        "y_direction",
    ),
    "harmonic_z": (
        "vibration_resistance_analysis_z",
        "harmonic_response_z",
        "harmonic_response_z_direction",
        "harmonic_z_direction",
        "harmonic/z/",
        "harmonic_z/",
        "z_direction",
    ),
}

_FILE_ALIASES: dict[str, tuple[str, ...]] = {
    "loading/acceleration.png": (
        "loading/displacement.png",
        "loading/loading_conditions_overview.png",
    ),
    "solution/graphs/frequency_response.png": (
        "solution/graphs/frequency_response_structural_steel.png",
    ),
}

_FREQ_GRAPH_PREFER = (
    "frequency_response_structural_steel",
    "frequency_response",
)


def canonical_folder_to_family(name: str) -> str | None:
    """Map a canonical or on-disk export folder name to a slot family key."""
    n = name.lower().replace("\\", "/").strip("/")
    for family, markers in _SHOCK_FOLDER.items():
        for marker in markers:
            token = marker.strip("/").split("/")[0]
            if token and token in n:
                return family
    for family, markers in _HARMONIC_FOLDER.items():
        for marker in markers:
            token = marker.strip("/").split("/")[0]
            if token and token in n:
                return family
    if "static_structural" in n or n in {"static", "static_structural"}:
        return "static"
    if n == "modal" or n.startswith("modal/"):
        return "modal"
    inferred = analysis_name_to_family(name.replace("-", " "))
    if inferred in _SHOCK_FOLDER or inferred in _HARMONIC_FOLDER:
        return inferred
    if inferred == "static":
        return "static"
    if inferred == "modal":
        return "modal"
    return None


def _probe_slot_for_family(family: str) -> str:
    if family.startswith(("harmonic_", "shock_")):
        return f"{family}_deformation"
    return ""


def _folder_match_score(folder_name: str, target_family: str) -> int:
    inferred = analysis_name_to_family(folder_name.replace("-", " "))
    if inferred == target_family:
        return 200
    markers = _SHOCK_FOLDER.get(target_family) or _HARMONIC_FOLDER.get(target_family) or ()
    lower = folder_name.lower()
    score = 0
    for marker in markers:
        token = marker.strip("/").split("/")[0]
        if token and token in lower:
            score += len(token) + 10
    return score


def resolve_export_folder(image_root: Path, canonical_folder: str) -> str:
    """Return the actual export directory name under *image_root* for a canonical folder."""
    if not canonical_folder:
        return canonical_folder
    root = Path(image_root)
    if not root.is_dir():
        return canonical_folder
    if (root / canonical_folder).is_dir():
        return canonical_folder

    target_family = canonical_folder_to_family(canonical_folder)
    if not target_family:
        return canonical_folder

    probe_slot = _probe_slot_for_family(target_family)
    best_name: str | None = None
    best_score = 0
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if probe_slot and not path_allowed_for_slot(
            probe_slot, f"{name}/solution/total_deformation.png"
        ):
            continue
        score = _folder_match_score(name, target_family)
        if score > best_score:
            best_score = score
            best_name = name

    if best_name and best_score > 0:
        return best_name
    return canonical_folder


def rank_frequency_response_graph(path: Path) -> tuple[int, str]:
    """Prefer canonical structural-steel frequency response graphs."""
    stem = path.stem.lower()
    for idx, prefer in enumerate(_FREQ_GRAPH_PREFER):
        if stem == prefer or stem.endswith(f"_{prefer}"):
            return (idx, stem)
    return (len(_FREQ_GRAPH_PREFER), stem)


def resolve_file_variant_in_folder(folder: Path, tail: str) -> Path | None:
    """Resolve *tail* under *folder*, trying known Mechanical export filename aliases."""
    tail_norm = tail.replace("\\", "/")
    direct = folder / tail_norm
    if direct.is_file():
        return direct.resolve()

    for alt_tail in _FILE_ALIASES.get(tail_norm, ()):
        alt = folder / alt_tail
        if alt.is_file():
            return alt.resolve()

    if tail_norm.endswith("solution/graphs/frequency_response.png"):
        graphs = folder / "solution" / "graphs"
        if graphs.is_dir():
            matches = sorted(
                (p for p in graphs.glob("frequency_response*.png") if p.is_file()),
                key=rank_frequency_response_graph,
            )
            if matches:
                return matches[0].resolve()
    return None


_FORBIDDEN_FOR_STATIC = (
    "equivalent_static",
    "vibration_resistance",
    "harmonic_response",
    "/harmonic/",
    "/modal/",
    "transient_",
    "/transient/",
)


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
        return _STATIC_FOLDERS
    if family == "modal":
        return ("modal/",)
    if s == "cad_isometric":
        return ("geometry/",)
    if s == "cad_section":
        return ("connections/", "geometry/cad_section", "cad_section")
    if s == "geometry_model_orientation":
        return ("coordinate_systems/",)
    if s == "model_orientation_gravity":
        return _STATIC_FOLDERS
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
        if not any(token in p for token in ("acceleration", "displacement", "loading/")):
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
    """All folder name tokens that may identify exports for *slot*."""
    markers = folder_markers_for_slot(slot)
    keywords: list[str] = []
    for marker in markers:
        token = marker.strip("/").split("/")[0]
        if token and token not in keywords:
            keywords.append(token)
    return keywords


def expected_folder_markers(slot: str) -> tuple[str, ...]:
    """Markers used by validation (alias for folder_markers_for_slot)."""
    return folder_markers_for_slot(slot)


def alternate_map_paths(slot: str, rel_path: str) -> list[str]:
    """Candidate relative paths when the configured image_map path is missing."""
    rel = rel_path.replace("\\", "/")
    parts = rel.split("/")
    if len(parts) < 2:
        return []
    tail = "/".join(parts[1:])
    alternates: list[str] = []
    for marker in folder_markers_for_slot(slot):
        token = marker.strip("/").split("/")[0]
        if not token:
            continue
        candidate = f"{token}/{tail}"
        if candidate != rel and candidate not in alternates:
            alternates.append(candidate)
    return alternates


def sanitize_analysis_name(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")


def _harmonic_axis_from_name(analysis: str) -> str | None:
    for axis in "xyz":
        if (
            f"vibration_resistance_analysis_{axis}" in analysis
            or f"harmonic_response_{axis}" in analysis
            or f"harmonic_{axis}_direction" in analysis
            or re.search(rf"harmonic.*_{axis}(?:_|$)", analysis)
        ):
            return axis
    return None


def _shock_family_from_transient_name(analysis: str) -> str | None:
    """Map Mechanical transient export folder names (e.g. transient_horizontal_-x-)."""
    if "transient" not in analysis:
        return None
    direction_axes = (
        ("horizontal", "x", "shock_minus_x"),
        ("vertical", "y", "shock_minus_y"),
        ("longitud", "z", "shock_minus_z"),
    )
    for word, axis, family in direction_axes:
        if word not in analysis:
            continue
        if (
            f"_{axis}" in analysis
            or f"{axis}_" in analysis
            or analysis.endswith(axis)
            or f"minus_{axis}" in analysis
            or f"neg{axis}" in analysis
        ):
            return family
    return None


def _shock_family_from_name(analysis: str) -> str | None:
    if not any(k in analysis for k in ("equivalent_static", "equivalent_shock", "shock", "transient")):
        return None
    transient = _shock_family_from_transient_name(analysis)
    if transient:
        return transient
    for axis in "xyz":
        for sign, tokens in (
            ("plus", ("pos", "plus", "+")),
            ("minus", ("neg", "minus", "-")),
        ):
            for token in tokens:
                if f"{token}{axis}" in analysis or f"{token}_{axis}" in analysis:
                    return f"shock_{sign}_{axis}"
    return None


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
    if "static_structural" in a or a in {"static_structural", "static"}:
        return "static"
    if a == "modal":
        return "modal"

    axis = _harmonic_axis_from_name(a)
    if axis:
        return f"harmonic_{axis}"

    shock = _shock_family_from_name(a)
    if shock:
        return shock

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
