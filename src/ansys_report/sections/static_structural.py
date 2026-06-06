"""Static structural section plugin."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig, load_thresholds
from ansys_report.extract.dpf_static import extract_static
from ansys_report.models import ProjectInventory, StaticResult
from ansys_report.narrative import rules


class StaticStructuralSection:
    key = "static"

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        rst = _pick_rst(inventory, ("static", "SYS-1", "struct"))
        static = (
            extract_static(rst, cfg.primary_yield_mpa) if rst else StaticResult(manual_fields=["all"])
        )
        return static.model_dump()

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        thresholds = load_thresholds(cfg.thresholds_path)
        static = StaticResult(**data)
        narrative = rules.narrate_static(static, cfg, thresholds)
        return narrative.model_dump()

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {"static": {**data, "narrative": narrative}}


def _pick_rst(inventory: ProjectInventory, prefer: tuple[str, ...]):
    for name in prefer:
        for key, path in inventory.rst_files.items():
            if name.lower() in key.lower():
                return path
    return next(iter(inventory.rst_files.values()), None)
