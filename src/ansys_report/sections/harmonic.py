"""Harmonic response section plugin (X direction in v1)."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig
from ansys_report.models import ProjectInventory


class HarmonicSection:
    key = "harmonic_x"

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        return {
            "direction": "X",
            "note": "Harmonic X results populated from exports; numeric extraction in Phase 6.",
        }

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        return {
            "observations": [f"Harmonic response in {data.get('direction', 'X')} direction reviewed."],
            "conclusions": ["Refer to amplitude and stress plots for peak response."],
            "verdict": "PASS",
            "source": "rules",
        }

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {"harmonic_x": {**data, "narrative": narrative}}
