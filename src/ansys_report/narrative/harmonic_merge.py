"""Merge per-axis harmonic narratives into a single vibration conclusion block."""

from __future__ import annotations

from typing import Any

HARMONIC_SECTION_KEYS: tuple[str, ...] = ("harmonic_x", "harmonic_y", "harmonic_z")

_VERDICT_RANK = {"PASS": 0, "CAUTION": 1, "FAIL": 2}


def merge_harmonic_conclusion_narrative(
    context: dict[str, Any],
    *,
    enabled_sections: set[str] | None = None,
) -> dict[str, Any]:
    """Combine harmonic X/Y/Z rule narratives for the vibration conclusion section."""
    observations: list[str] = []
    conclusions: list[str] = []
    recommendations: list[str] = []
    worst_verdict = "PASS"

    for key in HARMONIC_SECTION_KEYS:
        if enabled_sections is not None and key not in enabled_sections:
            continue

        block = context.get(key)
        if not block:
            continue

        direction = str(block.get("direction") or key.rsplit("_", 1)[-1].upper())
        narr = block.get("narrative") or {}
        if not narr:
            continue

        for text in narr.get("observations") or []:
            observations.append(_label_text(str(text), direction))

        for text in narr.get("conclusions") or []:
            conclusions.append(_label_text(str(text), direction))

        for text in narr.get("recommendations") or []:
            recommendations.append(_label_text(str(text), direction))

        verdict = str(narr.get("verdict") or "PASS").upper()
        if _VERDICT_RANK.get(verdict, 0) > _VERDICT_RANK.get(worst_verdict, 0):
            worst_verdict = verdict

    if not conclusions and not observations:
        return {
            "observations": [],
            "conclusions": ["Vibration assessment pending extraction or manual review."],
            "recommendations": [],
            "verdict": "CAUTION",
            "source": "rules",
        }

    return {
        "observations": _dedupe_preserve_order(observations),
        "conclusions": _dedupe_preserve_order(conclusions),
        "recommendations": _dedupe_preserve_order(recommendations),
        "verdict": worst_verdict,
        "source": "rules",
    }


def _label_text(text: str, direction: str) -> str:
    """Ensure each sentence is attributable to an axis when the rules text is generic."""
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    upper = cleaned.upper()
    axis = direction.upper()
    if f"HARMONIC {axis}" in upper:
        return cleaned
    if f" {axis}:" in upper or f" {axis} " in upper:
        return cleaned
    if cleaned.lower().startswith("peak harmonic") or cleaned.lower().startswith("peak response"):
        return f"Harmonic {axis}: {cleaned[0].lower()}{cleaned[1:]}" if len(cleaned) > 1 else cleaned

    return f"Harmonic {axis}: {cleaned}"


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
