"""Dominant-direction labels for modal summary tables (EP1581 Table 14)."""

from __future__ import annotations

_DIRECTION_LABELS: tuple[tuple[str, str], ...] = (
    ("rot_x", "Rotation about X"),
    ("rot_y", "Rotation about Y"),
    ("rot_z", "Rotation about Z"),
    ("x", "X Direction"),
    ("y", "Y Direction"),
    ("z", "Z Direction"),
)

_SIGNIFICANT_RATIO = 0.10
_MIN_RATIO = 0.01


def dominant_direction_from_ratios(ratios: dict[str, float] | None) -> str | None:
    """Label dominant motion direction(s) from effective-mass ratios (Mechanical-style)."""
    if not ratios:
        return None

    ordered = [(key, ratios.get(key) or 0.0) for key, _ in _DIRECTION_LABELS]
    max_ratio = max(value for _, value in ordered)
    if max_ratio <= 0:
        return None

    significant = [
        label
        for key, label in _DIRECTION_LABELS
        if (ratios.get(key) or 0.0) >= _SIGNIFICANT_RATIO
    ]
    if not significant:
        for key, label in _DIRECTION_LABELS:
            if (ratios.get(key) or 0.0) >= _MIN_RATIO and (ratios.get(key) or 0.0) >= max_ratio - 1e-9:
                return label
        for key, label in _DIRECTION_LABELS:
            if (ratios.get(key) or 0.0) >= max_ratio - 1e-9:
                return label
        return None

    return " & ".join(significant)
