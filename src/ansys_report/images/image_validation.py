"""Validate resolved figure slot → PNG path assignments."""

from __future__ import annotations

from pathlib import Path

from ansys_report.images.analysis_registry import expected_folder_markers, path_allowed_for_slot


def validate_resolved_images(
    resolved: dict[str, Path], image_root: Path | None = None
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for suspicious slot assignments."""
    errors: list[str] = []
    warnings: list[str] = []
    by_path: dict[str, list[str]] = {}

    for slot, path in resolved.items():
        rel = _relative_path(path, image_root)
        by_path.setdefault(str(path.resolve()).lower(), []).append(slot)

        if not path_allowed_for_slot(slot, rel):
            markers = expected_folder_markers(slot)
            hint = markers[0] if markers else "expected analysis folder"
            msg = f"{slot}: path '{rel}' does not match required folder ({hint})"
            if slot.startswith("shock_") or slot == "static_pressure":
                errors.append(msg)
            else:
                warnings.append(msg)

        if slot == "static_pressure" and "static_structural" not in rel.replace("\\", "/").lower():
            errors.append(f"{slot}: must be under static_structural/, got '{rel}'")

        if slot == "modelling_contacts" and "connections/" not in rel.replace("\\", "/").lower():
            warnings.append(f"{slot}: must be under connections/, got '{rel}'")

        if slot.endswith("_location") and "acceleration" not in rel.lower():
            warnings.append(f"{slot}: expected loading/acceleration.png, got '{rel}'")

    for path_key, slots in by_path.items():
        if len(slots) < 2:
            continue
        shock_slots = [s for s in slots if s.startswith("shock_")]
        if len(shock_slots) >= 2:
            errors.append(
                f"Same PNG used for multiple shock slots: {', '.join(sorted(shock_slots))}"
            )
        elif len(slots) >= 2:
            warnings.append(f"Duplicate PNG shared by slots: {', '.join(sorted(slots))}")

    _check_shock_cross_assignment(resolved, errors, image_root)
    return _dedupe(errors), _dedupe(warnings)


def _check_shock_cross_assignment(
    resolved: dict[str, Path],
    errors: list[str],
    image_root: Path | None,
) -> None:
    """Warn when shock +X/+Y slots point at the wrong posx/posy folder."""
    checks = {
        "shock_plus_x_deformation": "equivalent_static_analysis_posx",
        "shock_plus_y_deformation": "equivalent_static_analysis_posy",
        "shock_plus_z_deformation": "equivalent_static_analysis_posz",
        "shock_minus_x_deformation": "equivalent_static_analysis_negx",
        "shock_minus_y_deformation": "equivalent_static_analysis_negy",
        "shock_minus_z_deformation": "equivalent_static_analysis_negz",
    }
    for slot, required in checks.items():
        path = resolved.get(slot)
        if path is None:
            continue
        rel = _relative_path(path, image_root).lower()
        if required not in rel:
            errors.append(f"{slot}: expected folder containing '{required}', got '{rel}'")


def _relative_path(path: Path, image_root: Path | None) -> str:
    if image_root is not None:
        try:
            return path.relative_to(image_root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
