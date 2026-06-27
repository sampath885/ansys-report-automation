"""Equivalent shock analysis section (±X/Y/Z)."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig, load_thresholds
from ansys_report.extract.bolt_loads import resolve_shock_bolt_loads
from ansys_report.extract.dpf_static import extract_static
from ansys_report.models import ProjectInventory, StaticResult
from ansys_report.narrative import rules

# section result key → (inventory system key, folder, display label)
SHOCK_DIRECTIONS: list[tuple[str, str, str, str]] = [
    ("plus_x", "shock_plus_x", "SYS-5", "+X"),
    ("plus_y", "shock_plus_y", "SYS-6", "+Y"),
    ("plus_z", "shock_plus_z", "SYS-7", "+Z"),
    ("minus_x", "shock_minus_x", "SYS-8", "-X"),
    ("minus_y", "shock_minus_y", "SYS-9", "-Y"),
    ("minus_z", "shock_minus_z", "SYS-10", "-Z"),
]


class ShockSection:
    key = "shock"

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        from ansys_report.extract.metadata import bodies_from_inventory, dedupe_bodies

        directions: list[dict[str, Any]] = []
        manual: list[str] = []
        yield_mpa = cfg.primary_yield_mpa
        bodies = dedupe_bodies(bodies_from_inventory(inventory))

        allow_golden = cfg.use_word_table_data or cfg.use_dpf_golden_fallback

        for result_key, system_key, folder, label in SHOCK_DIRECTIONS:
            rst = _pick_rst(inventory, system_key, folder)
            if not rst:
                directions.append(
                    {
                        "key": result_key,
                        "system_key": system_key,
                        "direction": label,
                        "bolt_loads": resolve_shock_bolt_loads(
                            result_key,
                            None,
                            cfg=cfg,
                            allow_word_golden=allow_golden,
                        ),
                        "manual_fields": ["max_stress_mpa", "max_deformation_mm"],
                    }
                )
                manual.extend([f"{result_key}.stress", f"{result_key}.deformation"])
                continue

            static = extract_static(rst, yield_mpa, load_step=1, bodies=bodies)
            bolt_loads = resolve_shock_bolt_loads(
                result_key,
                rst,
                cfg=cfg,
                allow_word_golden=allow_golden,
            )
            directions.append(
                {
                    "key": result_key,
                    "system_key": system_key,
                    "direction": label,
                    "workbench_folder": folder,
                    "bolt_loads": bolt_loads,
                    **static.model_dump(),
                }
            )
            manual.extend(static.manual_fields)

        return {"directions": directions, "manual_fields": manual}

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        thresholds = load_thresholds(cfg.thresholds_path)
        observations: list[str] = []
        conclusions: list[str] = []
        verdict = "PASS"

        for item in data.get("directions", []):
            static = StaticResult(
                max_stress_mpa=item.get("max_stress_mpa"),
                max_deformation_mm=item.get("max_deformation_mm"),
                fos=item.get("fos"),
            )
            part = rules.narrate_shock(static, item.get("direction", "?"), cfg, thresholds)
            observations.extend(part.observations)
            conclusions.extend(part.conclusions)
            if part.verdict == "FAIL":
                verdict = "FAIL"
            elif part.verdict == "CAUTION" and verdict != "FAIL":
                verdict = "CAUTION"

        if not conclusions:
            conclusions.append("Shock assessment pending extraction or manual review.")

        return {
            "observations": observations,
            "conclusions": conclusions,
            "verdict": verdict,
            "source": "rules",
        }

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {"shock": {**data, "narrative": narrative}}


def _pick_rst(inventory: ProjectInventory, system_key: str, folder: str):
    if system_key in inventory.systems:
        return inventory.systems[system_key].primary_rst
    for sys in inventory.systems.values():
        if sys.folder == folder:
            return sys.primary_rst
    return inventory.rst_files.get(system_key)
