"""Harmonic / vibration resistance section plugins (X, Y, Z)."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig, load_thresholds
from ansys_report.extract.dpf_harmonic import extract_harmonic_peak
from ansys_report.models import HarmonicPeakResult, ProjectInventory
from ansys_report.narrative import rules

# section key → (inventory system key, Workbench folder, direction label)
HARMONIC_SYSTEMS: dict[str, tuple[str, str, str]] = {
    "harmonic_x": ("vibration_x", "SYS-2", "X"),
    "harmonic_y": ("vibration_y", "SYS-3", "Y"),
    "harmonic_z": ("vibration_z", "SYS-4", "Z"),
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
        rst = _pick_rst(inventory, self._system_key, self._folder)
        result = extract_harmonic_peak(rst) if rst else None
        if not result:
            return {
                "direction": self._direction,
                "system_key": self._system_key,
                "workbench_folder": self._folder,
                "manual_fields": ["peak_displacement_mm", "peak_frequency_hz"],
            }
        return {
            "direction": self._direction,
            "system_key": self._system_key,
            "workbench_folder": self._folder,
            **result.model_dump(),
        }

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
            block["source"] = "dpf"
        elif "source" not in block:
            block["source"] = "missing"
        return {self.key: block}


def harmonic_sections() -> list[HarmonicSection]:
    return [HarmonicSection(k) for k in HARMONIC_SYSTEMS]


def _pick_rst(inventory: ProjectInventory, system_key: str, folder: str):
    if system_key in inventory.systems:
        return inventory.systems[system_key].primary_rst
    for sys in inventory.systems.values():
        if sys.folder == folder:
            return sys.primary_rst
    return inventory.rst_files.get(system_key)
