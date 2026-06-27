"""Tests for multi-direction extraction diagnostics."""

from __future__ import annotations

from ansys_report.report.extraction_diagnostics import (
    check_harmonic_extraction,
    check_shock_extraction,
)


def test_shock_warns_on_missing_direction():
    ctx = {
        "shock": {
            "directions": [
                {"direction": "+X", "max_stress_mpa": 100.0, "max_deformation_mm": 0.1},
                {"direction": "+Y", "manual_fields": ["max_stress_mpa"]},
            ],
            "narrative": {"observations": ["a"], "conclusions": ["b"]},
        }
    }
    warnings = check_shock_extraction(ctx)
    assert any("+Y" in w and "missing" in w for w in warnings)


def test_shock_warns_when_all_stresses_identical():
    ctx = {
        "shock": {
            "directions": [
                {"direction": "+X", "max_stress_mpa": 440.65, "max_deformation_mm": 0.15},
                {"direction": "+Y", "max_stress_mpa": 440.65, "max_deformation_mm": 0.15},
            ],
            "narrative": {},
        }
    }
    warnings = check_shock_extraction(ctx)
    assert any("identical max_stress_mpa" in w for w in warnings)


def test_harmonic_warns_on_missing_peak():
    ctx = {"harmonic_x": {"direction": "X", "manual_fields": ["peak_displacement_mm"]}}
    warnings = check_harmonic_extraction(ctx, enabled_sections={"harmonic_x"})
    assert any("harmonic_x" in w for w in warnings)
