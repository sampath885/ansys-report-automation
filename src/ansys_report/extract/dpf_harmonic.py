"""Harmonic / vibration response extraction via DPF."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ansys_report.extract.dpf_base import open_model, to_mm
from ansys_report.extract.dpf_timing import log_dpf_step
from ansys_report.models import HarmonicPeakResult

logger = logging.getLogger(__name__)


def _peak_from_displacement_fields(
    disp_fc,
    freqs: list[float],
) -> tuple[float, float | None, int]:
    """Find peak displacement magnitude and its frequency from a fields container."""
    max_amp = 0.0
    peak_freq: float | None = None
    n_sets = len(disp_fc)

    for idx, field in enumerate(disp_fc):
        data = field.data
        if data is None or len(data) == 0:
            continue
        mag = float(np.linalg.norm(data, axis=1).max())
        amp_mm = to_mm(mag, getattr(field, "unit", "mm") or "mm")
        if amp_mm is not None and amp_mm > max_amp:
            max_amp = amp_mm
            peak_freq = float(freqs[idx]) if idx < len(freqs) else None

    return max_amp, peak_freq, n_sets


def _peak_via_dpf_operators(model, freqs: list[float]) -> tuple[float, float | None, int] | None:
    """Single-pass peak via DPF norm + min_max operators (preferred when available)."""
    try:
        from ansys.dpf.core import operators as ops

        disp_fc = model.results.displacement().eval()
        if not disp_fc:
            return None

        norm_fc = ops.math.norm_fc(disp_fc).outputs.fields_container()
        min_max = ops.min_max.min_max_fc(norm_fc).eval()

        max_field = min_max.max()
        if max_field is None or max_field.data is None or len(max_field.data) == 0:
            return _peak_from_displacement_fields(disp_fc, freqs)

        global_max = float(np.asarray(max_field.data).max())
        max_amp = to_mm(global_max, getattr(max_field, "unit", "mm") or "mm") or 0.0

        # Identify which frequency step produced the peak.
        peak_freq: float | None = None
        step_max = 0.0
        for idx, field in enumerate(norm_fc):
            if field.data is None or len(field.data) == 0:
                continue
            step_peak = float(np.asarray(field.data).max())
            if step_peak > step_max:
                step_max = step_peak
                peak_freq = float(freqs[idx]) if idx < len(freqs) else None

        return max_amp, peak_freq, len(disp_fc)
    except Exception as exc:
        logger.debug("DPF operator harmonic peak fallback: %s", exc)
        return None


def extract_harmonic_peak(rst_path: Path) -> HarmonicPeakResult:
    """Peak displacement magnitude and frequency across harmonic result sets."""
    manual: list[str] = []

    with log_dpf_step("harmonic", rst_path):
        model = open_model(rst_path)
        if model is None:
            return HarmonicPeakResult(manual_fields=["peak_displacement_mm", "peak_frequency_hz"])

        try:
            freqs = list(model.metadata.time_freq_support.time_frequencies.data)
            n_results = model.metadata.result_info.n_results

            result = _peak_via_dpf_operators(model, freqs)
            if result is None:
                disp_fc = model.results.displacement().eval()
                max_amp, peak_freq, n_sets = _peak_from_displacement_fields(disp_fc, freqs)
            else:
                max_amp, peak_freq, n_sets = result

            if n_sets == 0 and n_results:
                n_sets = n_results

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
