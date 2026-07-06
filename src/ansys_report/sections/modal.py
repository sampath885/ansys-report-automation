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
        rst = _pick_rst(inventory, ("modal", "SYS-1"))
        modal = extract_modal(rst, cfg.modal.num_modes) if rst else None
        modes = []
        if modal:
            modes = [m.model_dump() for m in modal.modes]

        boundary_conditions: list[dict[str, Any]] = []
        loads: list[dict[str, Any]] = []
        mech_dir = _modal_mech_dir(inventory)
        if mech_dir is not None:
            from ansys_report.extract.metadata import extract_analysis_metadata

            analysis = extract_analysis_metadata(mech_dir)
            boundary_conditions = [bc.model_dump(mode="json") for bc in analysis.boundary_conditions]
            loads = [load.model_dump(mode="json") for load in analysis.loads]

        return {
            "modes": modes,
            "boundary_conditions": boundary_conditions,
            "loads": loads,
            "manual_fields": modal.manual_fields if modal else ["frequencies"],
        }

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        from ansys_report.models import ModalResult, ModeResult

        thresholds = load_thresholds(cfg.thresholds_path)
        modes = [ModeResult(**m) for m in data.get("modes", [])]
        narrative = rules.narrate_modal(ModalResult(modes=modes), cfg, thresholds)
        return narrative.model_dump()

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        block = {**data, "narrative": narrative}
        has_freq = any(m.get("freq_hz") is not None for m in data.get("modes", []))
        if "source" not in block:
            block["source"] = "dpf" if has_freq else "missing"
        return {"modal": block}


def _pick_rst(inventory: ProjectInventory, prefer: tuple[str, ...]):
    for name in prefer:
        for key, sys in inventory.systems.items():
            if name.lower() in key.lower() or name.lower() in sys.folder.lower():
                return sys.primary_rst
        for key, path in inventory.rst_files.items():
            if name.lower() in key.lower():
                return path
    return next(iter(inventory.rst_files.values()), None)


def _modal_mech_dir(inventory: ProjectInventory):
    for name in ("modal", "SYS-1", "sys-1"):
        for key, sys in inventory.systems.items():
            if name.lower() in key.lower() or name.lower() in sys.folder.lower():
                return sys.mech_dir
    return None
