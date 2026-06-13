"""Static structural extraction via DPF."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ansys_report.extract.dpf_base import open_model, to_mm, von_mises_max_mpa
from ansys_report.models import StaticResult

logger = logging.getLogger(__name__)


def extract_static(
    rst_path: Path,
    yield_mpa: float | None = None,
    *,
    load_step: int | None = None,
) -> StaticResult:
    """Extract static results. For EP2737 nonlinear pretension+pressure use load_step=3."""
    manual: list[str] = []
    result = StaticResult()

    model = open_model(rst_path)
    if model is None:
        manual.extend(["max_stress_mpa", "max_deformation_mm", "reaction_force_n"])
        return StaticResult(manual_fields=manual)

    time_scoping = load_step if load_step is not None else None

    try:
        stress_fc = (
            model.results.stress(time_scoping=time_scoping).eval()
            if time_scoping
            else model.results.stress().eval()
        )
        if stress_fc:
            result.max_stress_mpa = von_mises_max_mpa(stress_fc[0])
        if result.max_stress_mpa is None:
            manual.append("max_stress_mpa")

        disp_fc = (
            model.results.displacement(time_scoping=time_scoping).eval()
            if time_scoping
            else model.results.displacement().eval()
        )
        if disp_fc:
            field = disp_fc[0]
            mag = float(np.linalg.norm(field.data, axis=1).max())
            result.max_deformation_mm = to_mm(mag, getattr(field, "unit", "mm") or "mm")
        if result.max_deformation_mm is None:
            manual.append("max_deformation_mm")

        force, moment = _reactions(model, time_scoping)
        result.reaction_force_n = force
        result.reaction_moment_nmm = moment
        if force is None:
            manual.append("reaction_force_n")

        if yield_mpa and result.max_stress_mpa and result.max_stress_mpa > 0:
            result.fos = round(yield_mpa / result.max_stress_mpa, 2)
    except Exception as exc:
        logger.warning("Static extraction failed: %s", exc)
        manual.extend(["max_stress_mpa", "max_deformation_mm"])

    result.manual_fields = manual
    return result


def _reactions(model, time_scoping: int | None) -> tuple[float | None, float | None]:
    try:
        reaction = (
            model.results.reaction_force(time_scoping=time_scoping)
            if time_scoping
            else model.results.reaction_force()
        )
        fc = reaction.eval()
        if fc:
            data = fc[0].data
            mag = float(np.linalg.norm(data))
            return mag, None
    except Exception:
        pass
    return None, None
