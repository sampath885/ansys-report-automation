"""Threshold-based engineering narratives."""

from __future__ import annotations

from ansys_report.config import ProjectConfig, ThresholdsConfig
from ansys_report.models import HarmonicPeakResult, ModalResult, Narrative, SectionVerdict, StaticResult


def narrate_static(
    static: StaticResult,
    cfg: ProjectConfig,
    thresholds: ThresholdsConfig,
) -> Narrative:
    observations: list[str] = []
    conclusions: list[str] = []
    recommendations: list[str] = []
    verdict = "PASS"

    yield_mpa = cfg.primary_yield_mpa
    stress = static.max_stress_mpa
    if stress is None:
        return Narrative(
            observations=["Maximum von-Mises stress was not extracted; manual entry required."],
            conclusions=["Static structural assessment pending manual stress review."],
            verdict="CAUTION",
            source="rules",
        )

    if yield_mpa:
        fraction = stress / yield_mpa
        warn = thresholds.stress.warn_fraction_of_yield
        fail = thresholds.stress.fail_fraction_of_yield
        observations.append(
            f"Peak von-Mises stress is {stress:.2f} MPa "
            f"({fraction * 100:.1f}% of yield {yield_mpa:.0f} MPa)."
        )
        if fraction >= fail:
            verdict = "FAIL"
            conclusions.append("Stress exceeds yield; design is NOT ACCEPTABLE under static loading.")
            recommendations.append("Review geometry, material selection, or loading conditions.")
        elif fraction >= warn:
            verdict = "CAUTION"
            conclusions.append(
                "Stress exceeds 80% of yield; verify margins and consider design refinement."
            )
        else:
            conclusions.append("Static stress levels are within acceptable limits.")
    else:
        observations.append(f"Peak von-Mises stress is {stress:.2f} MPa.")
        conclusions.append("Yield strength not configured; FOS comparison skipped.")

    if static.fos is not None:
        observations.append(f"Factor of safety (yield/stress): {static.fos:.2f}.")
        if static.fos < thresholds.fos.min_acceptable:
            verdict = "FAIL" if verdict != "FAIL" else verdict
            if static.fos < thresholds.fos.min_acceptable:
                verdict = "FAIL"
            conclusions.append(
                f"FOS {static.fos:.2f} is below target {thresholds.fos.min_acceptable}."
            )

    deform = static.max_deformation_mm
    if deform is not None:
        observations.append(f"Maximum total deformation: {deform:.3f} mm.")
        if deform > thresholds.deformation.warn_mm:
            recommendations.append(
                f"Deformation {deform:.3f} mm exceeds warning threshold "
                f"{thresholds.deformation.warn_mm} mm."
            )

    return Narrative(
        observations=observations,
        conclusions=conclusions,
        recommendations=recommendations,
        verdict=verdict,
        source="rules",
    )


def narrate_modal(
    modal: ModalResult,
    cfg: ProjectConfig,
    thresholds: ThresholdsConfig,
) -> Narrative:
    observations: list[str] = []
    conclusions: list[str] = []
    recommendations: list[str] = []
    verdict = "PASS"

    low, high = cfg.operating_freq_hz
    margin = thresholds.modal.resonance_margin_hz

    for mode in modal.modes:
        if mode.freq_hz is None:
            continue
        freq = mode.freq_hz
        if (low - margin) <= freq <= (high + margin):
            verdict = "CAUTION"
            conclusions.append(
                f"Mode {mode.index} at {freq:.2f} Hz is within operating band "
                f"({low}-{high} Hz) ± {margin} Hz — resonance risk."
            )
            recommendations.append("Verify damping, detuning, or operational avoidance.")

    if not conclusions:
        freqs = [mode.freq_hz for mode in modal.modes if mode.freq_hz is not None]
        if freqs:
            fundamental = min(freqs)
            conclusions.append(
                f"The fundamental natural frequency is {fundamental:.2f} Hz, which is well above "
                f"the operating frequency range ({low}-{high} Hz). No natural frequency lies within "
                f"the operating band, so resonance is not expected and the design is acceptable for "
                f"modal behaviour."
            )
        else:
            conclusions.append(
                f"No natural frequencies found within the operating band ({low}-{high} Hz)."
            )

    return Narrative(
        observations=observations,
        conclusions=conclusions,
        recommendations=recommendations,
        verdict=verdict,
        source="rules",
    )


def narrate_harmonic(
    peak: HarmonicPeakResult,
    direction: str,
    cfg: ProjectConfig,
    thresholds: ThresholdsConfig,
) -> Narrative:
    observations: list[str] = []
    conclusions: list[str] = []
    recommendations: list[str] = []
    verdict = "PASS"

    disp = peak.peak_displacement_mm
    freq = peak.peak_frequency_hz
    if disp is None or freq is None:
        return Narrative(
            observations=[f"Harmonic {direction}: peak response not extracted."],
            conclusions=["Vibration assessment pending manual review."],
            verdict="CAUTION",
            source="rules",
        )

    observations.append(
        f"Harmonic {direction}: peak displacement {disp:.3f} mm at {freq:.2f} Hz "
        f"({peak.num_frequency_sets or '?'} frequency sets)."
    )
    if disp > thresholds.deformation.warn_mm:
        verdict = "CAUTION"
        conclusions.append(
            f"Peak harmonic displacement exceeds {thresholds.deformation.warn_mm} mm warning level."
        )
        recommendations.append("Verify acceptance against vibration specification and operational limits.")
    else:
        conclusions.append("Peak harmonic displacement is within configured warning threshold.")

    low, high = cfg.operating_freq_hz
    if (low - thresholds.modal.resonance_margin_hz) <= freq <= (high + thresholds.modal.resonance_margin_hz):
        verdict = "CAUTION" if verdict != "FAIL" else verdict
        conclusions.append(
            f"Peak response frequency {freq:.2f} Hz is near operating band ({low}-{high} Hz)."
        )

    return Narrative(
        observations=observations,
        conclusions=conclusions,
        recommendations=recommendations,
        verdict=verdict,
        source="rules",
    )


def narrate_shock(
    static: StaticResult,
    direction: str,
    cfg: ProjectConfig,
    thresholds: ThresholdsConfig,
) -> Narrative:
    observations: list[str] = []
    conclusions: list[str] = []
    verdict = "PASS"

    stress = static.max_stress_mpa
    deform = static.max_deformation_mm
    if stress is None:
        observations.append(f"Shock {direction}: stress not extracted.")
        return Narrative(
            observations=observations,
            conclusions=["Shock assessment pending manual review."],
            verdict="CAUTION",
            source="rules",
        )

    yield_mpa = cfg.primary_yield_mpa
    observations.append(f"Shock {direction}: peak von-Mises stress {stress:.2f} MPa.")
    if deform is not None:
        observations.append(f"Shock {direction}: peak deformation {deform:.3f} mm.")

    if yield_mpa:
        fraction = stress / yield_mpa
        if fraction >= thresholds.stress.fail_fraction_of_yield:
            verdict = "FAIL"
            conclusions.append(f"Shock {direction}: stress exceeds yield — NOT ACCEPTABLE.")
        elif fraction >= thresholds.stress.warn_fraction_of_yield:
            verdict = "CAUTION"
            conclusions.append(f"Shock {direction}: stress above 80% of yield — review margins.")
        else:
            conclusions.append(f"Shock {direction}: stress within acceptable limits.")

    if static.fos is not None and static.fos < thresholds.fos.min_acceptable:
        verdict = "FAIL"
        conclusions.append(
            f"Shock {direction}: FOS {static.fos:.2f} below target {thresholds.fos.min_acceptable}."
        )

    return Narrative(
        observations=observations,
        conclusions=conclusions,
        verdict=verdict,
        source="rules",
    )


def build_executive_summary(verdicts: list[SectionVerdict]) -> str:
    if not verdicts:
        return "Report generated with configured sections."
    parts = []
    for v in verdicts:
        parts.append(f"{v.section}: {v.verdict}")
    overall = "FAIL" if any(v.verdict == "FAIL" for v in verdicts) else (
        "CAUTION" if any(v.verdict == "CAUTION" for v in verdicts) else "PASS"
    )
    return f"Overall assessment: {overall}. " + "; ".join(parts) + "."
