"""Static structural extraction via DPF."""

from __future__ import annotations

import logging
from pathlib import Path

from ansys_report.extract.dpf_base import open_model, to_mm, to_mpa
from ansys_report.models import StaticResult

logger = logging.getLogger(__name__)


def extract_static(rst_path: Path, yield_mpa: float | None = None) -> StaticResult:
    manual: list[str] = []
    result = StaticResult()

    model = open_model(rst_path)
    if model is None:
        manual.extend(["max_stress_mpa", "max_deformation_mm", "reaction_force_n"])
        return StaticResult(manual_fields=manual)

    try:
        stress_field = _max_equivalent_stress(model)
        result.max_stress_mpa = to_mpa(stress_field)
        if result.max_stress_mpa is None:
            manual.append("max_stress_mpa")

        deform = _max_total_deformation(model)
        result.max_deformation_mm = to_mm(deform)
        if result.max_deformation_mm is None:
            manual.append("max_deformation_mm")

        force, moment = _reactions(model)
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


def _max_equivalent_stress(model) -> float | None:
    try:
        from ansys.dpf import core as dpf

        stress = model.results.stress()
        eqv = stress.von_mises()
        fc = eqv.eval()
        if fc:
            return float(fc[0].max().data[0])
    except Exception:
        pass
    try:
        stress = model.results.stress()
        fc = stress.eval()
        if fc:
            data = fc[0].data
            import numpy as np

            vm = np.sqrt(
                0.5
                * (
                    (data[:, 0] - data[:, 1]) ** 2
                    + (data[:, 1] - data[:, 2]) ** 2
                    + (data[:, 2] - data[:, 0]) ** 2
                    + 6 * (data[:, 3] ** 2 + data[:, 4] ** 2 + data[:, 5] ** 2)
                )
            )
            return float(vm.max())
    except Exception:
        return None
    return None


def _max_total_deformation(model) -> float | None:
    try:
        disp = model.results.displacement()
        fc = disp.eval()
        if fc:
            import numpy as np

            data = fc[0].data
            mag = np.linalg.norm(data, axis=1)
            return float(mag.max())
    except Exception:
        return None
    return None


def _reactions(model) -> tuple[float | None, float | None]:
    try:
        reaction = model.results.reaction_force()
        fc = reaction.eval()
        if fc:
            import numpy as np

            data = fc[0].data
            mag = float(np.linalg.norm(data))
            return mag, None
    except Exception:
        pass
    return None, None
