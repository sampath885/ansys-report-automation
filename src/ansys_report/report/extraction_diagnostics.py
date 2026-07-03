"""Log warnings when multi-direction result blocks are incomplete or suspicious."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HARMONIC_KEYS = ("harmonic_x", "harmonic_y", "harmonic_z")


def check_harmonic_extraction(
    context: dict[str, Any],
    *,
    enabled_sections: set[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    enabled = enabled_sections or set(HARMONIC_KEYS)

    for key in HARMONIC_KEYS:
        if key not in enabled:
            continue
        block = context.get(key) or {}
        direction = block.get("direction") or key.split("_")[-1].upper()
        peak = block.get("peak_displacement_mm")
        freq = block.get("peak_frequency_hz")
        source = block.get("source") or block.get("extraction_source") or "unknown"
        rst = block.get("workbench_folder") or block.get("system_key") or "unknown"

        if peak is None and freq is None:
            manual = block.get("manual_fields") or []
            reason = f"manual fields: {', '.join(manual)}" if manual else f"no peak extracted (source={source})"
            msg = f"harmonic_{direction.lower()}: missing peak displacement/frequency ({reason})"
            warnings.append(msg)
            logger.warning(msg)
            continue

        narr = (block.get("narrative") or {}).get("conclusions") or []
        if not narr:
            warnings.append(f"harmonic_{direction.lower()}: no narrative conclusions generated")

    vib = context.get("vibration_conclusion") or {}
    merged = (vib.get("narrative") or {}).get("conclusions") or []
    expected = sum(1 for k in HARMONIC_KEYS if k in enabled and context.get(k))
    if expected and len(merged) < expected:
        warnings.append(
            f"vibration_conclusion: {len(merged)} merged conclusion(s) for {expected} harmonic axis/axes "
            f"(expected one conclusion block per axis with data)"
        )

    return warnings


def check_shock_extraction(context: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    shock = context.get("shock") or {}
    directions = shock.get("directions") or []
    if not directions:
        warnings.append("shock: no direction results in context")
        return warnings

    stresses: list[float] = []
    missing: list[str] = []

    for item in directions:
        label = item.get("direction") or item.get("key") or "?"
        stress = item.get("max_stress_mpa")
        deform = item.get("max_deformation_mm")
        source = item.get("source") or item.get("extraction_source") or "?"
        folder = item.get("workbench_folder") or item.get("system_key") or "?"
        rst_note = f" [{folder}, source={source}]"

        if stress is None:
            manual = item.get("manual_fields") or []
            reason = ", ".join(manual) if manual else "summary/RST missing or extract failed"
            msg = f"shock {label}: missing max_stress_mpa ({reason}){rst_note}"
            warnings.append(msg)
            missing.append(label)
            logger.warning(msg)
        else:
            stresses.append(float(stress))

        if deform is None:
            warnings.append(f"shock {label}: missing max_deformation_mm{rst_note}")

        narr = (shock.get("narrative") or {}).get("conclusions") or []
        dir_conclusions = [c for c in narr if label.replace("+", "+").replace("-", "-") in c or label in c]
        if stress is not None and not dir_conclusions:
            # narrate_shock always prefixes direction in observations; conclusions may be generic
            pass

    narr = shock.get("narrative") or {}
    obs_count = len(narr.get("observations") or [])
    con_count = len(narr.get("conclusions") or [])
    filled = len(directions) - len(missing)
    if filled and obs_count < filled:
        warnings.append(
            f"shock narrative: {obs_count} observation(s) for {filled} direction(s) with data "
            f"(expected ~{filled * 2} lines)"
        )

    if len(stresses) >= 2 and len(set(round(s, 2) for s in stresses)) == 1:
        val = stresses[0]
        msg = (
            f"shock: all {len(stresses)} directions report identical max_stress_mpa={val:.2f} "
            "(common when extract uses load step 1 only; verify per-direction RST and load step)"
        )
        warnings.append(msg)
        logger.warning(msg)

    if missing:
        logger.warning("shock: %d/%d directions missing stress data", len(missing), len(directions))

    return warnings


def log_extraction_summary(context: dict[str, Any], *, enabled_sections: set[str] | None = None) -> None:
    """Print human-readable extraction summary to the log."""
    enabled = enabled_sections or set()

    for key in HARMONIC_KEYS:
        if enabled and key not in enabled:
            continue
        block = context.get(key) or {}
        if not block:
            continue
        logger.info(
            "%s: peak=%s mm @ %s Hz (source=%s)",
            key,
            block.get("peak_displacement_mm"),
            block.get("peak_frequency_hz"),
            block.get("source") or block.get("extraction_source") or "?",
        )

    shock = context.get("shock") or {}
    for item in shock.get("directions") or []:
        logger.info(
            "shock %s: stress=%s MPa, deform=%s mm, folder=%s, source=%s",
            item.get("direction"),
            item.get("max_stress_mpa"),
            item.get("max_deformation_mm"),
            item.get("workbench_folder") or item.get("system_key"),
            item.get("source") or item.get("extraction_source") or "?",
        )

    vib = context.get("vibration_conclusion") or {}
    n_con = len((vib.get("narrative") or {}).get("conclusions") or [])
    n_rows = len(vib.get("rows") or [])
    if n_rows or n_con:
        logger.info("vibration_conclusion: %d table row(s), %d merged conclusion line(s)", n_rows, n_con)
