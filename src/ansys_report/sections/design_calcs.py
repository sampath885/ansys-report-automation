"""Design calculations section plugin."""

from __future__ import annotations

from pathlib import Path
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
        excel_path = inventory.excel_path or cfg.excel_path
        bolt_preload = inventory.excel_bolt_preload
        if bolt_preload is None and cfg.excel_bolt_preload:
            bolt_preload = Path(cfg.excel_bolt_preload)
            if not bolt_preload.is_absolute():
                root = case_root or cfg.project_dir
                bolt_preload = root / bolt_preload

        export_dir = None
        if inventory.image_root:
            export_dir = inventory.image_root / "design_calcs"

        calcs = read_design_calcs(
            excel_path,
            excel_map_path=cfg.excel_map_path,
            case_root=case_root,
            excel_bolt_preload=bolt_preload,
            export_image_dir=export_dir,
            fos_target=cfg.static.fos_target,
            excel_mode=cfg.excel_mode,
        )
        discovered = [s.model_dump() for s in calcs.discovered_sections]
        legacy_populated = any(
            [calcs.bolt_load, calcs.flange_moments, calcs.effort, calcs.end_flange]
        )
        if not discovered and not legacy_populated:
            return {
                "bolt_load": [],
                "flange_moments": [],
                "effort": [],
                "end_flange": [],
                "discovered_sections": [],
                "extraction_source": calcs.extraction_source or "missing",
                "manual_fields": ["design_calcs"],
            }
        return {
            "bolt_load": [r.model_dump() for r in calcs.bolt_load],
            "flange_moments": [r.model_dump() for r in calcs.flange_moments],
            "effort": [r.model_dump() for r in calcs.effort],
            "end_flange": [r.model_dump() for r in calcs.end_flange],
            "discovered_sections": discovered,
            "extraction_source": calcs.extraction_source,
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
        for section in data.get("discovered_sections") or []:
            for row in section.get("raw_rows") or section.get("rows") or []:
                if isinstance(row, dict):
                    cells = [str(row.get("verdict") or "")]
                else:
                    cells = [str(c) for c in row]
                if any("NOT" in c.upper() and "ACCEPT" in c.upper() for c in cells):
                    verdict = "FAIL"
                    break
        return {
            "conclusions": ["Design calculation tables reviewed against acceptance criteria."],
            "verdict": verdict,
            "source": "rules",
        }

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {"design_calcs": {**data, "narrative": narrative}}
