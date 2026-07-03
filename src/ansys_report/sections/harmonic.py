"""Harmonic / vibration resistance section plugins (X, Y, Z)."""

from __future__ import annotations

import re
from typing import Any

from ansys_report.config import ProjectConfig, load_thresholds
from ansys_report.extract.dpf_harmonic import extract_harmonic_peak
from ansys_report.extract.result_summary import (
    merge_harmonic_results,
    pick_result_summary,
    summary_to_harmonic_peak,
)
from ansys_report.models import HarmonicPeakResult, ProjectInventory
from ansys_report.narrative import rules

# section key → (inventory system key, Workbench folder, direction label)
HARMONIC_SYSTEMS: dict[str, tuple[str, str, str]] = {
    "harmonic_x": ("vibration_x", "SYS-2", "X"),
    "harmonic_y": ("vibration_y", "SYS-3", "Y"),
    "harmonic_z": ("vibration_z", "SYS-4", "Z"),
}

_AXIS_FOLDER_MARKERS: dict[str, tuple[str, ...]] = {
    "x": (
        "vibration_resistance_analysis_x",
        "harmonic/x",
        "harmonic_x",
        "x_direction",
        " x",
        " x-",
    ),
    "y": (
        "vibration_resistance_analysis_y",
        "harmonic/y",
        "harmonic_y",
        "y_direction",
        " y",
        " y-",
    ),
    "z": (
        "vibration_resistance_analysis_z",
        "harmonic/z",
        "harmonic_z",
        "z_direction",
        " z",
        " z-",
    ),
}


class HarmonicSection:
    def __init__(self, key: str) -> None:
        if key not in HARMONIC_SYSTEMS:
            raise ValueError(f"Unknown harmonic section: {key}")
        self.key = key
        self._system_key, self._folder, self._direction = HARMONIC_SYSTEMS[key]

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        rst = _pick_rst(inventory, self._system_key, self._folder, self._direction)
        summary = pick_result_summary(inventory, self._system_key)

        if summary:
            result = summary_to_harmonic_peak(summary)
        else:
            result = HarmonicPeakResult(manual_fields=["peak_displacement_mm", "peak_frequency_hz"])

        if rst:
            dpf_result = extract_harmonic_peak(rst)
            if summary:
                result = merge_harmonic_results(result, dpf_result)
            else:
                result = dpf_result
                result.extraction_source = "dpf"
        elif not summary:
            return {
                "direction": self._direction,
                "system_key": self._system_key,
                "workbench_folder": self._folder,
                "manual_fields": ["peak_displacement_mm", "peak_frequency_hz"],
                "source": "missing",
            }

        payload = result.model_dump()
        payload.update(
            {
                "direction": self._direction,
                "system_key": self._system_key,
                "workbench_folder": self._folder,
                "source": result.extraction_source or ("dpf" if rst else "worksheet_summary"),
            }
        )
        return payload

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        thresholds = load_thresholds(cfg.thresholds_path)
        peak = HarmonicPeakResult(
            peak_displacement_mm=data.get("peak_displacement_mm"),
            peak_frequency_hz=data.get("peak_frequency_hz"),
            num_frequency_sets=data.get("num_frequency_sets"),
        )
        narrative = rules.narrate_harmonic(peak, data.get("direction", "X"), cfg, thresholds)
        return narrative.model_dump()

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        block = {**data, "narrative": narrative}
        if data.get("peak_displacement_mm") is not None and "source" not in block:
            block["source"] = data.get("extraction_source") or data.get("source") or "dpf"
        elif "source" not in block:
            block["source"] = "missing"
        return {self.key: block}


def harmonic_sections() -> list[HarmonicSection]:
    return [HarmonicSection(k) for k in HARMONIC_SYSTEMS]


def _pick_rst(
    inventory: ProjectInventory,
    system_key: str,
    folder: str,
    direction: str,
):
    if system_key in inventory.systems:
        rst = inventory.systems[system_key].primary_rst
        if rst is not None:
            return rst
    for sys in inventory.systems.values():
        if sys.folder == folder and sys.primary_rst is not None:
            return sys.primary_rst
    path = inventory.rst_files.get(system_key) or inventory.rst_files.get(folder)
    if path is not None:
        return path

    axis = direction.lower()
    return _pick_rst_by_axis(inventory, axis)


def _pick_rst_by_axis(inventory: ProjectInventory, axis: str) -> Any:
    """Resolve harmonic RST when Workbench SYS numbering differs from EP2737."""
    markers = _AXIS_FOLDER_MARKERS.get(axis, ())
    other_axes = [a for a in "xyz" if a != axis]

    best_score = -1
    best_rst = None

    for sys in inventory.systems.values():
        if sys.primary_rst is None:
            continue
        if sys.antype in ("modal", "static"):
            continue

        blob = " ".join(
            part
            for part in (sys.key, sys.folder, sys.display_name, sys.project_name or "")
            if part
        ).lower()

        if not any(token in blob for token in ("harmonic", "vibration")):
            continue
        if any(f"vibration_resistance_analysis_{other}" in blob for other in other_axes):
            continue
        if any(f"harmonic/{other}" in blob or f"harmonic_{other}" in blob for other in other_axes):
            continue

        score = 0
        if sys.antype == "harmonic":
            score += 4
        for marker in markers:
            if marker in blob:
                score += 10
        if re.search(rf"\b{axis}\b", blob):
            score += 6
        if f"_{axis}_" in blob or blob.endswith(axis):
            score += 4

        if score > best_score:
            best_score = score
            best_rst = sys.primary_rst

    return best_rst
