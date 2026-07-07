"""Validate semantic (AI or inferred) slot → path assignments."""

from __future__ import annotations

import re
from pathlib import Path

from ansys_report.images.slot_semantics import (
    SlotSemantics,
    analysis_root_from_rel_path,
    parse_slot_semantics,
    path_forbidden_for_dynamic_slots,
    slot_accepts_folder_role,
    slots_may_share_image,
    static_path_allowed,
)

_AXIS_TOKENS: dict[str, tuple[str, ...]] = {
    "x": ("_x_", "_x/", "/x/", "posx", "negx", "plus_x", "minus_x", "x_direction", "_x_"),
    "y": ("_y_", "_y/", "/y/", "posy", "negy", "plus_y", "minus_y", "y_direction", "_y_"),
    "z": ("_z_", "_z/", "/z/", "posz", "negz", "plus_z", "minus_z", "z_direction", "_z_"),
}

_PLUS_TOKENS = ("plus", "posx", "posy", "posz", "positive", "+x", "+y", "+z")
_MINUS_TOKENS = ("minus", "negx", "negy", "negz", "negative", "-x", "-y", "-z")


def validate_semantic_assignment(
    slot: str,
    rel_path: str,
    *,
    used_paths: set[str] | None = None,
    path_owners: dict[str, str] | None = None,
    folder_roles: dict[str, str] | None = None,
) -> str | None:
    """Return an error message if assignment is invalid, else None."""
    sem = parse_slot_semantics(slot)
    if sem is None:
        return f"{slot}: not a semantic-scope slot"

    rel = rel_path.replace("\\", "/")
    rel_lower = rel.lower()
    filename = Path(rel).name.lower()

    if path_forbidden_for_dynamic_slots(rel):
        return f"{slot}: must not use modal/mesh/geometry path ({rel})"

    if used_paths is not None and rel_lower in used_paths:
        owner = (path_owners or {}).get(rel_lower)
        if owner and not slots_may_share_image(slot, owner):
            return f"{slot}: path already assigned to {owner} ({rel})"

    folder = analysis_root_from_rel_path(rel)
    folder_lower = folder.lower()

    cross = _cross_physics_error(sem, folder_lower, rel)
    if cross:
        return cross

    if folder_roles and folder in folder_roles:
        role = folder_roles[folder]
        if not slot_accepts_folder_role(slot, role):
            return f"{slot}: folder '{folder}' role '{role}' incompatible with slot ({rel})"

    if sem.analysis_type == "static" and not static_path_allowed(rel):
        return f"{slot}: path looks like shock/harmonic/modal, not static ({rel})"

    if sem.analysis_type in {"harmonic", "shock"}:
        axis_err = _check_axis(sem, rel_lower)
        if axis_err:
            return axis_err
        if sem.analysis_type == "shock":
            sign_err = _check_sign(sem, rel_lower)
            if sign_err:
                return sign_err

    if sem.result_kind.endswith("_location") or sem.result_kind == "location":
        if "modal_modal" in rel_lower:
            return f"{slot}: must not use modal_modal plot ({rel})"

    if not _filename_matches_kind(sem, filename, rel_lower):
        return f"{slot}: filename does not match result type '{sem.result_kind}' ({rel})"

    return None


def _cross_physics_error(sem: SlotSemantics, folder_lower: str, rel: str) -> str | None:
    """Reject assignments that swap harmonic vs transient export folders."""
    if sem.analysis_type == "harmonic" and "transient" in folder_lower:
        return f"{sem.slot}: transient folder is shock minus, not harmonic ({rel})"
    if sem.analysis_type == "shock" and sem.sign == "minus" and "harmonic" in folder_lower:
        return f"{sem.slot}: harmonic folder is shock plus / harmonic, not shock minus ({rel})"
    if sem.analysis_type == "shock" and sem.sign == "plus" and "transient" in folder_lower:
        return f"{sem.slot}: transient folder is shock minus, not shock plus ({rel})"
    return None


def validate_semantic_batch(
    assignments: dict[str, str],
    *,
    used_paths: set[str] | None = None,
    path_owners: dict[str, str] | None = None,
    folder_roles: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Filter assignments to valid ones; return (accepted, rejection_messages)."""
    accepted: dict[str, str] = {}
    rejections: list[str] = []
    consumed = set(used_paths or [])
    owners = dict(path_owners or {})

    for slot, rel in assignments.items():
        if rel is None or str(rel).lower() in {"null", "none", ""}:
            continue
        rel_str = str(rel).replace("\\", "/")
        err = validate_semantic_assignment(
            slot,
            rel_str,
            used_paths=consumed,
            path_owners=owners,
            folder_roles=folder_roles,
        )
        if err:
            rejections.append(err)
            continue
        accepted[slot] = rel_str
        rel_key = rel_str.lower()
        if rel_key not in consumed:
            consumed.add(rel_key)
        if rel_key not in owners:
            owners[rel_key] = slot

    _check_incompatible_duplicates(accepted, rejections)
    return accepted, rejections


def _check_axis(sem: SlotSemantics, rel_lower: str) -> str | None:
    """Reject only when another axis is clearly indicated (not when axis token is absent)."""
    if not sem.axis:
        return None
    for other in "xyz":
        if other == sem.axis:
            continue
        if any(token in rel_lower for token in _AXIS_TOKENS[other]):
            return f"{sem.slot}: path suggests wrong axis ({rel_lower})"
    return None


def _check_sign(sem: SlotSemantics, rel_lower: str) -> str | None:
    if not sem.sign:
        return None
    has_plus = any(token in rel_lower for token in _PLUS_TOKENS)
    has_minus = any(token in rel_lower for token in _MINUS_TOKENS)
    if sem.sign == "plus":
        if has_minus and not has_plus:
            return f"{sem.slot}: expected + direction, path looks negative ({rel_lower})"
    elif sem.sign == "minus":
        if has_plus and not has_minus:
            return f"{sem.slot}: expected - direction, path looks positive ({rel_lower})"
    return None


def _filename_matches_kind(sem: SlotSemantics, filename: str, rel_lower: str) -> bool:
    hints = sem.filename_hints
    if any(hint in filename or hint in rel_lower for hint in hints):
        return True

    kind = sem.result_kind
    if kind in {"deformation", "total_deformation"}:
        return "deformation" in filename
    if kind in {"stress_asm", "vonmises_stress"}:
        return "stress" in filename and "flange" not in filename
    if kind in {"stress_flange", "vonmises_flange"}:
        return "flange" in filename or "flange" in rel_lower
    if kind == "reaction_force":
        return "reaction" in filename
    if kind in {"earth_gravity", "model_orientation_gravity"}:
        return "gravity" in filename
    if kind == "fixed_support":
        return "fixed" in filename or "support" in filename
    if kind == "pressure":
        return "pressure" in filename
    if kind == "location":
        return "acceleration" in filename or "acceleration" in rel_lower
    if kind == "accel_plot":
        return "frequency" in filename or "response" in filename

    tokens = [token for token in re.split(r"[_\-\s]+", kind) if len(token) > 2]
    return any(token in filename for token in tokens)


def _check_incompatible_duplicates(accepted: dict[str, str], rejections: list[str]) -> None:
    by_path: dict[str, list[str]] = {}
    for slot, rel in accepted.items():
        by_path.setdefault(rel.lower(), []).append(slot)
    for path, slots in by_path.items():
        if len(slots) < 2:
            continue
        first = slots[0]
        for other in slots[1:]:
            if not slots_may_share_image(first, other):
                rejections.append(
                    f"Incompatible slots sharing PNG: {', '.join(sorted(slots))} ({path})"
                )
                for slot in slots[1:]:
                    accepted.pop(slot, None)
                break
