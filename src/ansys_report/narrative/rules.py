"""Threshold-based engineering narratives."""

from __future__ import annotations

from ansys_report.config import ProjectConfig, ThresholdsConfig
from ansys_report.models import ModalResult, Narrative, SectionVerdict, StaticResult


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
        observations.append(f"Mode {mode.index}: {freq:.2f} Hz.")
        if (low - margin) <= freq <= (high + margin):
            verdict = "CAUTION"
            conclusions.append(
                f"Mode {mode.index} at {freq:.2f} Hz is within operating band "
                f"({low}-{high} Hz) ± {margin} Hz — resonance risk."
            )
            recommendations.append("Verify damping, detuning, or operational avoidance.")

    if not conclusions:
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
