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
        from ansys_report.extract.bolt_loads import resolve_static_bolt_loads
        from ansys_report.extract.metadata import bodies_from_inventory, dedupe_bodies

        rst = _pick_rst(inventory, ("static_structural", "static", "SYS"))
        bodies = dedupe_bodies(bodies_from_inventory(inventory))
        static = (
            extract_static(rst, cfg.primary_yield_mpa, load_step=3, bodies=bodies)
            if rst
            else StaticResult(manual_fields=["all"])
        )
        payload = static.model_dump()
        allow_golden = cfg.use_word_table_data or cfg.use_dpf_golden_fallback
        payload["bolt_loads"] = resolve_static_bolt_loads(rst, cfg=cfg, allow_word_golden=allow_golden)
        return payload

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        block = {**data, "narrative": narrative}
        if data.get("max_stress_mpa") is not None and "source" not in block:
            block["source"] = "dpf"
        elif data.get("max_stress_mpa") is None and "source" not in block:
            block["source"] = "missing"
        if data.get("bolt_loads"):
            block["bolt_loads_source"] = block.get("source", "dpf")
        else:
            block["bolt_loads_source"] = "missing"
        return {"static": block}

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        thresholds = load_thresholds(cfg.thresholds_path)
        static = StaticResult(**data)
        narrative = rules.narrate_static(static, cfg, thresholds)
        return narrative.model_dump()


def _pick_rst(inventory: ProjectInventory, prefer: tuple[str, ...]):
    for name in prefer:
        for key, sys in inventory.systems.items():
            if name.lower() in key.lower() or name.lower() in sys.folder.lower():
                return sys.primary_rst
        for key, path in inventory.rst_files.items():
            if name.lower() in key.lower():
                return path
    return next(iter(inventory.rst_files.values()), None)
