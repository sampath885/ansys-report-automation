"""Modal extraction via DPF."""

from __future__ import annotations

import logging
from pathlib import Path

from ansys_report.extract.dpf_base import open_model
from ansys_report.models import ModalResult, ModeResult

logger = logging.getLogger(__name__)


def extract_modal(rst_path: Path, num_modes: int = 6) -> ModalResult:
    manual: list[str] = []
    modes: list[ModeResult] = []

    model = open_model(rst_path)
    if model is None:
        return ModalResult(
            modes=[ModeResult(index=i + 1, freq_hz=None) for i in range(num_modes)],
            manual_fields=["frequencies"],
        )

    try:
        freq_op = model.results.eigen_frequencies()
        fc = freq_op.eval()
        if fc:
            freqs = fc[0].data
            for i in range(min(num_modes, len(freqs))):
                modes.append(ModeResult(index=i + 1, freq_hz=float(freqs[i])))
        else:
            manual.append("frequencies")
    except Exception as exc:
        logger.warning("Modal extraction failed: %s", exc)
        manual.append("frequencies")

    while len(modes) < num_modes:
        modes.append(ModeResult(index=len(modes) + 1, freq_hz=None))

    return ModalResult(modes=modes[:num_modes], manual_fields=manual)
