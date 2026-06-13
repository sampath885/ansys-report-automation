"""Bolt load table extraction for static/shock analyses."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ansys_report.extract.dpf_bolt import BoltExtractionMode, parse_pretension_preload_n

logger = logging.getLogger(__name__)

GOLDEN_NAME = "8_shock_bolt_loads.json"
STATIC_GOLDEN_NAME = "7_static_bolt_loads.json"
SHOCK_TABLE_NUMBERS = {
    "plus_x": 17,
    "plus_y": 18,
    "plus_z": 19,
    "minus_x": 20,
    "minus_y": 21,
    "minus_z": 22,
}


def load_static_bolt_golden(golden_dir: Path | None = None) -> list[dict[str, Any]]:
    root = golden_dir or Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ep2737_golden"
    path = root / STATIC_GOLDEN_NAME
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("bolt_loads", []))


def load_shock_bolt_golden(
    direction_key: str,
    golden_dir: Path | None = None,
) -> list[dict[str, Any]]:
    root = golden_dir or Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ep2737_golden"
    path = root / GOLDEN_NAME
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("directions", {}).get(direction_key, []))


def _bolt_kwargs(cfg: Any | None) -> dict[str, Any]:
    if cfg is None:
        return {}
    bolts = getattr(cfg, "bolts", None)
    if bolts is None:
        return {}
    return {
        "tensile_area_mm2": bolts.tensile_stress_area_mm2,
        "shear_area_mm2": bolts.shear_stress_area_mm2,
        "yield_mpa": bolts.report_yield_mpa,
        "expected_count": bolts.count,
        "load_step": bolts.load_step,
    }


def extract_bolt_loads_from_rst(
    rst_path: Path | None,
    cfg: Any | None = None,
    *,
    mode: BoltExtractionMode = "envelope",
    uniform_axial_n: float | None = None,
) -> list[dict[str, Any]]:
    """Extract per-bolt axial/shear from pretension beam results via DPF."""
    if rst_path is None or not rst_path.exists():
        return []
    try:
        from ansys_report.extract.dpf_bolt import extract_bolt_loads_dpf

        kwargs = _bolt_kwargs(cfg)
        return extract_bolt_loads_dpf(
            rst_path,
            mode=mode,
            uniform_axial_n=uniform_axial_n,
            **kwargs,
        )
    except ImportError:
        return []
    except Exception as exc:
        logger.debug("Bolt DPF extraction unavailable: %s", exc)
        return []


def resolve_static_bolt_loads(
    rst_path: Path | None,
    *,
    cfg: Any | None = None,
    golden_dir: Path | None = None,
    allow_word_golden: bool = False,
) -> list[dict[str, Any]]:
    if os.getenv("ANSYS_AVAILABLE") == "1":
        mode: BoltExtractionMode = "envelope"
        uniform_axial = None
        if cfg is not None:
            bolts = getattr(cfg, "bolts", None)
            if bolts is not None:
                mode = getattr(bolts, "static_extraction_mode", None) or getattr(
                    bolts, "extraction_mode", "envelope"
                )
                if getattr(bolts, "uniform_axial_from_preload", True):
                    uniform_axial = parse_pretension_preload_n(rst_path.parent) if rst_path else None
                    if uniform_axial is not None:
                        uniform_axial = float(round(uniform_axial))

        live = extract_bolt_loads_from_rst(
            rst_path,
            cfg=cfg,
            mode=mode,
            uniform_axial_n=uniform_axial,
        )
        if live:
            return live
    if allow_word_golden:
        return load_static_bolt_golden(golden_dir)
    return []


def resolve_shock_bolt_loads(
    direction_key: str,
    rst_path: Path | None,
    *,
    cfg: Any | None = None,
    golden_dir: Path | None = None,
    allow_word_golden: bool = False,
) -> list[dict[str, Any]]:
    if os.getenv("ANSYS_AVAILABLE") == "1":
        mode: BoltExtractionMode = "first"
        if cfg is not None:
            bolts = getattr(cfg, "bolts", None)
            if bolts is not None:
                mode = getattr(bolts, "shock_extraction_mode", None) or "first"

        live = extract_bolt_loads_from_rst(rst_path, cfg=cfg, mode=mode)
        if live:
            return live
    if allow_word_golden:
        return load_shock_bolt_golden(direction_key, golden_dir)
    return []


def shock_bolt_table_caption(direction_key: str, direction_label: str) -> str:
    num = SHOCK_TABLE_NUMBERS.get(direction_key)
    if num:
        return f"Table {num}: Bolt Loads: Shock in {direction_label} direction"
    return f"Bolt Loads: Shock in {direction_label} direction"
