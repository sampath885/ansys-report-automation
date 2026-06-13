"""Harmonic / vibration response extraction via DPF."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ansys_report.extract.dpf_base import open_model, to_mm
from ansys_report.models import HarmonicPeakResult

logger = logging.getLogger(__name__)


def extract_harmonic_peak(rst_path: Path) -> HarmonicPeakResult:
    """Peak displacement magnitude and frequency across harmonic result sets."""
    manual: list[str] = []
    model = open_model(rst_path)
    if model is None:
        return HarmonicPeakResult(manual_fields=["peak_displacement_mm", "peak_frequency_hz"])

    try:
        n_sets = model.metadata.result_info.n_results
        freqs = list(model.metadata.time_freq_support.time_frequencies.data)
        max_amp = 0.0
        peak_freq: float | None = None

        for ts in range(1, n_sets + 1):
            fc = model.results.displacement(time_scoping=ts).eval()
            field = fc[0]
            mag = float(np.linalg.norm(field.data, axis=1).max())
            amp_mm = to_mm(mag, getattr(field, "unit", "mm") or "mm")
            if amp_mm is not None and amp_mm > max_amp:
                max_amp = amp_mm
                idx = ts - 1
                peak_freq = float(freqs[idx]) if idx < len(freqs) else None

        if max_amp == 0.0:
            manual.append("peak_displacement_mm")
        return HarmonicPeakResult(
            peak_displacement_mm=max_amp or None,
            peak_frequency_hz=peak_freq,
            num_frequency_sets=n_sets,
            manual_fields=manual,
        )
    except Exception as exc:
        logger.warning("Harmonic extraction failed: %s", exc)
        return HarmonicPeakResult(manual_fields=["peak_displacement_mm", "peak_frequency_hz"])
