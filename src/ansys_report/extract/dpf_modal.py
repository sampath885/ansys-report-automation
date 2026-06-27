"""Modal extraction via DPF."""

from __future__ import annotations

import logging
from pathlib import Path

from ansys_report.extract.dpf_base import open_model, read_modal_frequencies_hz
from ansys_report.extract.dpf_timing import log_dpf_step
from ansys_report.models import ModalResult, ModeResult

logger = logging.getLogger(__name__)


def extract_modal(rst_path: Path, num_modes: int = 6) -> ModalResult:
    manual: list[str] = []
    modes: list[ModeResult] = []

    with log_dpf_step("modal", rst_path):
        model = open_model(rst_path)
        if model is None:
            return ModalResult(
                modes=[ModeResult(index=i + 1, freq_hz=None) for i in range(num_modes)],
                manual_fields=["frequencies"],
            )

        try:
            freqs = read_modal_frequencies_hz(model, num_modes)
            for i, hz in enumerate(freqs):
                modes.append(ModeResult(index=i + 1, freq_hz=hz))
            if not freqs:
                manual.append("frequencies")
        except Exception as exc:
            logger.warning("Modal extraction failed: %s", exc)
            manual.append("frequencies")

    while len(modes) < num_modes:
        modes.append(ModeResult(index=len(modes) + 1, freq_hz=None))

    return ModalResult(modes=modes[:num_modes], manual_fields=manual)
