"""Design calculations section plugin."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig
from ansys_report.excel.reader import read_design_calcs
from ansys_report.models import ProjectInventory


class DesignCalcsSection:
    key = "design_calcs"

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        case_root = inventory.case_root or cfg.case_root or cfg.project_dir
        calcs = read_design_calcs(
            inventory.excel_path or cfg.excel_path,
            excel_map_path=cfg.excel_map_path,
            case_root=case_root,
            fos_target=cfg.static.fos_target,
        )
        if not any([calcs.bolt_load, calcs.flange_moments, calcs.effort, calcs.end_flange]):
            return {
                "bolt_load": [],
                "flange_moments": [],
                "effort": [],
                "end_flange": [],
                "manual_fields": ["design_calcs"],
            }
        return {
            "bolt_load": [r.model_dump() for r in calcs.bolt_load],
            "flange_moments": [r.model_dump() for r in calcs.flange_moments],
            "effort": [r.model_dump() for r in calcs.effort],
            "end_flange": [r.model_dump() for r in calcs.end_flange],
            "manual_fields": [],
        }

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        verdict = "PASS"
        for table in ("bolt_load", "flange_moments", "effort", "end_flange"):
            for row in data.get(table, []):
                v = (row.get("verdict") or "").upper()
                if "NOT" in v:
                    verdict = "FAIL"
                    break
        return {
            "conclusions": ["Design calculation tables reviewed against acceptance criteria."],
            "verdict": verdict,
            "source": "rules",
        }

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {"design_calcs": {**data, "narrative": narrative}}
