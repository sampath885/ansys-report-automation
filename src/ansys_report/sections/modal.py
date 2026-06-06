"""Modal analysis section plugin."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig, load_thresholds
from ansys_report.extract.dpf_modal import extract_modal
from ansys_report.models import ProjectInventory
from ansys_report.narrative import rules


class ModalSection:
    key = "modal"

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        rst = _pick_rst(inventory, ("modal", "SYS-3", "SYS-2"))
        modal = extract_modal(rst, cfg.modal.num_modes) if rst else None
        modes = []
        if modal:
            modes = [m.model_dump() for m in modal.modes]
        return {
            "modes": modes,
            "manual_fields": modal.manual_fields if modal else ["frequencies"],
        }

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        from ansys_report.models import ModalResult, ModeResult

        thresholds = load_thresholds(cfg.thresholds_path)
        modes = [ModeResult(**m) for m in data.get("modes", [])]
        narrative = rules.narrate_modal(ModalResult(modes=modes), cfg, thresholds)
        return narrative.model_dump()

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {"modal": {**data, "narrative": narrative}}


def _pick_rst(inventory: ProjectInventory, prefer: tuple[str, ...]):
    for name in prefer:
        for key, path in inventory.rst_files.items():
            if name.lower() in key.lower():
                return path
    return next(iter(inventory.rst_files.values()), None)
