"""Auto-derived semantics for report figure slots (no manual glossary)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_STATIC_FORBIDDEN_PATH_TOKENS = (
    "equivalent_static",
    "vibration_resistance",
    "/harmonic/",
    "/modal/",
    "shock/",
)

_RESULT_FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "earth_gravity": ("standard_earth_gravity", "earth_gravity", "gravity"),
    "fixed_support": ("fixed_support",),
    "pressure": ("pressure",),
    "total_deformation": ("total_deformation",),
    "deformation": ("total_deformation",),
    "vonmises_stress": ("equivalent_stress", "von_mises", "vonmises"),
    "vonmises_flange": ("equivalent_stress_flange", "stress_flange", "flange"),
    "reaction_force": ("reaction_force", "reaction", "force_reaction"),
    "stress_asm": ("equivalent_stress", "von_mises", "vonmises", "maximum_overtime"),
    "stress_flange": ("equivalent_stress_flange", "stress_flange", "flange"),
    "location": ("acceleration",),
    "accel_plot": ("frequency_response", "frequency", "response"),
    "model_orientation_gravity": ("standard_earth_gravity", "earth_gravity", "gravity"),
}

_FORBIDDEN_IMAGE_PREFIXES = (
    "modal/",
    "mesh/",
    "geometry/",
    "connections/",
    "coordinate_systems/",
    "materials/",
)


@dataclass(frozen=True)
class SlotSemantics:
    slot: str
    analysis_type: str  # static | harmonic | shock
    result_kind: str
    axis: str | None = None
    sign: str | None = None  # plus | minus

    @property
    def description(self) -> str:
        return _build_description(self)

    @property
    def filename_hints(self) -> tuple[str, ...]:
        hints = _RESULT_FILENAME_HINTS.get(self.result_kind)
        if hints:
            return hints
        token = self.result_kind.replace("_", " ")
        return (self.result_kind.replace("_", ""), token.replace(" ", "_"))


def is_semantic_scope_slot(slot: str) -> bool:
    """True for static / harmonic / shock slots eligible for semantic fallback."""
    return parse_slot_semantics(slot) is not None


def parse_slot_semantics(slot: str) -> SlotSemantics | None:
    """Parse any report slot name into engineering semantics (pattern-based)."""
    s = slot.lower().strip()
    if not s:
        return None

    if s == "model_orientation_gravity":
        return SlotSemantics(
            slot=slot,
            analysis_type="static",
            result_kind="model_orientation_gravity",
        )

    if s.startswith("static_"):
        tail = s[len("static_") :]
        if tail:
            return SlotSemantics(slot=slot, analysis_type="static", result_kind=tail)

    shock = re.match(r"^shock_(plus|minus)_([xyz])_(.+)$", s)
    if shock:
        sign, axis, tail = shock.groups()
        return SlotSemantics(
            slot=slot,
            analysis_type="shock",
            result_kind=tail,
            axis=axis,
            sign=sign,
        )

    harmonic = re.match(r"^harmonic_([xyz])_(.+)$", s)
    if harmonic:
        axis, tail = harmonic.groups()
        return SlotSemantics(
            slot=slot,
            analysis_type="harmonic",
            result_kind=tail,
            axis=axis,
        )

    return None


def canonical_analysis_folder(slot: str) -> str | None:
    """Map a slot to the canonical export folder name used in section YAML."""
    sem = parse_slot_semantics(slot)
    if sem is None:
        return None

    if sem.analysis_type == "static":
        return "static_structural"

    if sem.analysis_type == "harmonic" and sem.axis:
        return f"vibration_resistance_analysis_{sem.axis}"

    if sem.analysis_type == "shock" and sem.axis and sem.sign:
        from ansys_report.images.component_figures import shock_analysis_folder

        direction_key = f"{sem.sign}_{sem.axis}"
        return shock_analysis_folder(direction_key)

    return None


def analysis_root_from_rel_path(rel_path: str) -> str:
    """Top-level export folder for a relative PNG path."""
    normalized = rel_path.replace("\\", "/").strip("/")
    if not normalized:
        return ""
    return normalized.split("/", 1)[0]


def static_path_allowed(rel_path: str) -> bool:
    p = rel_path.lower().replace("\\", "/")
    return not any(token in p for token in _STATIC_FORBIDDEN_PATH_TOKENS)


def path_forbidden_for_dynamic_slots(rel_path: str) -> bool:
    lower = rel_path.lower().replace("\\", "/")
    return lower.startswith(_FORBIDDEN_IMAGE_PREFIXES)


def slots_may_share_image(slot_a: str, slot_b: str) -> bool:
    """True when two slots may legitimately use the same PNG path."""
    if slot_a == slot_b:
        return True
    sa, sb = parse_slot_semantics(slot_a), parse_slot_semantics(slot_b)
    if not sa or not sb:
        return False
    if sa.analysis_type == sb.analysis_type:
        return sa.result_kind == sb.result_kind
    return _harmonic_shock_plus_may_share(sa, sb) or _harmonic_shock_plus_may_share(sb, sa)


def _harmonic_shock_plus_may_share(harmonic: SlotSemantics, shock: SlotSemantics) -> bool:
    """Harmonic §7.3 and shock + §7.4 may reuse the same Harmonic Response export PNG."""
    if harmonic.analysis_type != "harmonic" or shock.analysis_type != "shock":
        return False
    if shock.sign != "plus":
        return False
    return harmonic.axis == shock.axis and harmonic.result_kind == shock.result_kind


def slot_accepts_folder_role(slot: str, role: str) -> bool:
    """Check whether a Gemini-assigned folder role is compatible with a slot."""
    role_norm = role.lower().strip()
    sem = parse_slot_semantics(slot)
    if not sem:
        return False

    forbidden = ("modal", "mesh", "geometry", "connection", "coordinate", "material")
    if any(token in role_norm for token in forbidden):
        return False

    if sem.axis and _role_axis_conflict(sem.axis, role_norm):
        return False

    if sem.analysis_type == "static":
        if any(token in role_norm for token in ("harmonic", "shock", "transient", "vibration")):
            return False
        return True

    if sem.analysis_type == "harmonic":
        if "transient" in role_norm and "harmonic" not in role_norm:
            return False
        if "shock" in role_norm and "harmonic" not in role_norm and "vibration" not in role_norm:
            return False
        return True

    if sem.analysis_type == "shock":
        if sem.sign == "plus":
            if "transient" in role_norm and "harmonic" not in role_norm:
                return False
            return True
        if "harmonic" in role_norm and "transient" not in role_norm:
            return False
        if "vibration" in role_norm and "transient" not in role_norm:
            return False
        return True

    return True


def _role_axis_conflict(expected_axis: str, role_norm: str) -> bool:
    axis_markers = {
        "x": ("horizontal", " posx", " negx", "+x", "-x", "_x", " x "),
        "y": ("vertical", " posy", " negy", "+y", "-y", "_y", " y "),
        "z": ("longitud", " posz", " negz", "+z", "-z", "_z", " z "),
    }
    for axis, markers in axis_markers.items():
        if axis == expected_axis:
            continue
        if any(marker in role_norm for marker in markers):
            return True
    return False


def _humanize(token: str) -> str:
    return token.replace("_", " ").strip()


def _build_description(sem: SlotSemantics) -> str:
    if sem.analysis_type == "static":
        head = "Static structural analysis"
    elif sem.analysis_type == "harmonic":
        head = f"Vibration resistance / harmonic response, {sem.axis.upper()}-direction"
    elif sem.analysis_type == "shock":
        sign_label = {"plus": "+", "minus": "-"}.get(sem.sign or "", "")
        head = f"Equivalent static shock analysis, {sign_label}{sem.axis.upper()}-direction"
    else:
        head = sem.analysis_type

    result = _humanize(sem.result_kind)
    hints = ", ".join(sem.filename_hints[:3])
    return (
        f"{head}. Figure type: {result}. "
        f"Expected PNG filename tokens: {hints}."
    )
