"""Overlay EP2737 golden DPF values when live extraction is unavailable."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ansys_report.config import ProjectConfig, load_thresholds
from ansys_report.models import HarmonicPeakResult, ModalResult, ModeResult, StaticResult
from ansys_report.narrative import rules
from ansys_report.sections.harmonic import HARMONIC_SYSTEMS

logger = logging.getLogger(__name__)

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ep2737_golden"

_HARMONIC_GOLDEN = {
    "harmonic_x": "2c_harmonic_x.json",
    "harmonic_y": "2e_harmonic_y.json",
    "harmonic_z": "2f_harmonic_z.json",
}


def needs_golden_overlay(ctx: dict[str, Any]) -> bool:
    modal = ctx.get("modal", {})
    static = ctx.get("static", {})
    return not modal.get("modes") or static.get("max_stress_mpa") is None


def apply_golden_dpf_overlay(
    ctx: dict[str, Any],
    cfg: ProjectConfig,
    golden_dir: Path | None = None,
    *,
    force: bool = False,
) -> bool:
    """Fill modal/static/harmonic/shock from golden JSON when DPF results are missing. Returns True if patched."""
    if not force and not needs_golden_overlay(ctx):
        _apply_bolt_fixture_fallback(ctx, cfg, golden_dir)
        return False

    root = golden_dir or GOLDEN_DIR
    thresholds = load_thresholds(cfg.thresholds_path)
    patched = False

    modal = ctx.get("modal", {})
    if force or not modal.get("modes"):
        path = root / "2a_modal.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            modes = [ModeResult(**m) for m in data["modes"]]
            narrative = rules.narrate_modal(ModalResult(modes=modes), cfg, thresholds)
            ctx["modal"] = {
                "modes": [m.model_dump() for m in modes],
                "manual_fields": [],
                "narrative": narrative.model_dump(),
                "source": "golden",
            }
            patched = True
            logger.info("Modal frequencies filled from golden fixture")

    static = ctx.get("static", {})
    if force or static.get("max_stress_mpa") is None:
        path = root / "2b_static_step3.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            static_result = StaticResult(
                max_stress_mpa=data.get("max_stress_mpa"),
                max_deformation_mm=data.get("max_deformation_mm"),
                reaction_force_n=data.get("reaction_force_n"),
                reaction_moment_nmm=data.get("reaction_moment_nmm"),
                fos=data.get("fos"),
                per_material=data.get("per_material", {}),
                manual_fields=[],
            )
            narrative = rules.narrate_static(static_result, cfg, thresholds)
            ctx["static"] = {
                **static_result.model_dump(),
                "load_step": data.get("load_step", 3),
                "narrative": narrative.model_dump(),
                "source": "golden",
            }
            patched = True
            logger.info("Static results filled from golden fixture")

    for section_key, golden_name in _HARMONIC_GOLDEN.items():
        block = ctx.get(section_key, {})
        if not force and block.get("peak_displacement_mm") is not None:
            continue
        path = root / golden_name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        direction = HARMONIC_SYSTEMS[section_key][2]
        peak = HarmonicPeakResult(
            peak_displacement_mm=data.get("peak_displacement_mm"),
            peak_frequency_hz=data.get("peak_frequency_hz"),
            num_frequency_sets=data.get("num_frequency_sets"),
            manual_fields=[],
        )
        narrative = rules.narrate_harmonic(peak, direction, cfg, thresholds)
        ctx[section_key] = {
            "direction": direction,
            **peak.model_dump(),
            "narrative": narrative.model_dump(),
            "source": "golden",
        }
        patched = True
        logger.info("Harmonic %s filled from golden fixture", direction)

    shock = ctx.get("shock", {})
    shock_needs = force or any(
        d.get("max_stress_mpa") is None for d in shock.get("directions", [])
    )
    if shock_needs:
        path = root / "7_shock_all.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            directions = []
            for item in data["directions"]:
                static = StaticResult(
                    max_stress_mpa=item.get("max_stress_mpa"),
                    max_deformation_mm=item.get("max_deformation_mm"),
                    fos=item.get("fos"),
                    manual_fields=[],
                )
                directions.append({**item, **static.model_dump()})
            shock_data = {"directions": directions, "manual_fields": []}
            if cfg.use_word_table_data or cfg.use_dpf_golden_fallback:
                _attach_shock_bolt_loads(shock_data["directions"], root)
            from ansys_report.sections.shock import ShockSection

            narrative = ShockSection().narrate(shock_data, cfg)
            ctx["shock"] = {**shock_data, "narrative": narrative, "source": "golden"}
            patched = True
            logger.info("Shock results filled from golden fixture")

    _apply_bolt_fixture_fallback(ctx, cfg, golden_dir)
    return patched


def _apply_bolt_fixture_fallback(
    ctx: dict[str, Any],
    cfg: ProjectConfig,
    golden_dir: Path | None = None,
) -> None:
    """Fill bolt load tables from RST regression fixtures when DPF extraction is unavailable."""
    if not cfg.use_dpf_golden_fallback and not cfg.use_word_table_data:
        return
    from ansys_report.extract.bolt_loads import load_static_bolt_golden, load_shock_bolt_golden

    root = golden_dir or GOLDEN_DIR
    static = ctx.get("static") or {}
    if not static.get("bolt_loads"):
        bolts = load_static_bolt_golden(root)
        if bolts:
            static["bolt_loads"] = bolts
            ctx["static"] = static
            logger.info("Static bolt loads filled from RST regression fixture")

    shock = ctx.get("shock") or {}
    for item in shock.get("directions", []):
        if item.get("bolt_loads"):
            continue
        key = item.get("key")
        if not key:
            continue
        bolts = load_shock_bolt_golden(key, root)
        if bolts:
            item["bolt_loads"] = bolts
            logger.info("Shock bolt loads filled for %s from RST regression fixture", key)


def _attach_shock_bolt_loads(directions: list[dict[str, Any]], golden_dir: Path) -> None:
    from ansys_report.extract.bolt_loads import load_shock_bolt_golden

    for item in directions:
        if item.get("bolt_loads"):
            continue
        key = item.get("key")
        if key:
            item["bolt_loads"] = load_shock_bolt_golden(key, golden_dir)
