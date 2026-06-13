"""Bolt load extraction — validates live DPF against reference Word golden (optional)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STATIC_RST = REPO / "EP 2737" / "Structural Analysis_EP2737" / "EP2737_files" / "dp0" / "SYS" / "MECH" / "file.rst"
SHOCK_RST = REPO / "EP 2737" / "Structural Analysis_EP2737" / "EP2737_files" / "dp0" / "SYS-5" / "MECH" / "file.rst"
STATIC_GOLDEN = REPO / "tests" / "fixtures" / "ep2737_golden" / "7_static_bolt_loads.json"


@pytest.fixture
def static_golden():
    return json.loads(STATIC_GOLDEN.read_text(encoding="utf-8"))["bolt_loads"]


def test_parse_pretension_preload_from_caerep():
    if not STATIC_RST.parent.exists():
        pytest.skip("EP2737 not in workspace")
    from ansys_report.extract.dpf_bolt import parse_pretension_preload_n

    preload = parse_pretension_preload_n(STATIC_RST.parent)
    assert preload is not None
    assert 11_800 < preload < 11_900


def test_old_load_step3_axial_is_wrong_for_static(static_golden):
    """Regression: load step 3 understates pretension axial (~11.3 kN vs ~11.8 kN)."""
    if os.getenv("ANSYS_AVAILABLE") != "1" or not STATIC_RST.exists():
        pytest.skip("ANSYS DPF required")
    from ansys_report.extract.dpf_bolt import extract_bolt_loads_dpf

    wrong = extract_bolt_loads_dpf(STATIC_RST, mode="step", load_step=3)
    assert wrong
    assert wrong[0]["axial_force_n"] < static_golden[0]["axial_force_n"] - 400


def test_static_bolt_envelope_matches_reference_axial(static_golden):
    if os.getenv("ANSYS_AVAILABLE") != "1" or not STATIC_RST.exists():
        pytest.skip("ANSYS DPF required")
    from ansys_report.extract.bolt_loads import resolve_static_bolt_loads
    from ansys_report.config import BoltConfig, ProjectConfig

    class _Cfg:
        bolts = BoltConfig()

    rows = resolve_static_bolt_loads(STATIC_RST, cfg=_Cfg())
    assert len(rows) == 8
    for row, golden in zip(rows, static_golden):
        assert row["axial_force_n"] == pytest.approx(golden["axial_force_n"], abs=1.0)


def test_shock_bolt_first_step_axial_not_step3(static_golden):
    if os.getenv("ANSYS_AVAILABLE") != "1" or not SHOCK_RST.exists():
        pytest.skip("ANSYS DPF required")
    from ansys_report.extract.dpf_bolt import extract_bolt_loads_dpf

    first = extract_bolt_loads_dpf(SHOCK_RST, mode="first")
    third = extract_bolt_loads_dpf(SHOCK_RST, mode="step", load_step=3)
    assert first[0]["axial_force_n"] > third[0]["axial_force_n"] + 400


def test_phase8_does_not_assert_bolt_numbers():
    """Document: phase 8 only checks bolt_load key exists, not Table 15 values."""
    path = REPO / "tests" / "test_ep2737_phase8.py"
    text = path.read_text(encoding="utf-8")
    assert "bolt_loads" not in text or "axial_force_n" not in text
