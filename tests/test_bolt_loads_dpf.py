"""Bolt load extraction — validates live DPF against reference Word golden."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ansys_report.ep2737_paths import ep2737_dp0, ep2737_workbench_dir

REPO = Path(__file__).resolve().parents[1]
STATIC_RST = ep2737_dp0() / "SYS" / "MECH" / "file.rst"
SHOCK_RST = {
    "plus_x": ep2737_dp0() / "SYS-5" / "MECH" / "file.rst",
    "plus_y": ep2737_dp0() / "SYS-6" / "MECH" / "file.rst",
    "plus_z": ep2737_dp0() / "SYS-7" / "MECH" / "file.rst",
}
STATIC_GOLDEN = REPO / "tests" / "fixtures" / "ep2737_golden" / "7_static_bolt_loads.json"
SHOCK_GOLDEN = REPO / "tests" / "fixtures" / "ep2737_golden" / "8_shock_bolt_loads.json"


@pytest.fixture
def static_golden():
    return json.loads(STATIC_GOLDEN.read_text(encoding="utf-8"))["bolt_loads"]


@pytest.fixture
def shock_golden():
    return json.loads(SHOCK_GOLDEN.read_text(encoding="utf-8"))["directions"]


def test_parse_pretension_preload_from_caerep():
    if not ep2737_workbench_dir().exists():
        pytest.skip("EP2737 not available")
    from ansys_report.extract.dpf_bolt import parse_pretension_preload_n

    preload = parse_pretension_preload_n(STATIC_RST.parent)
    assert preload is not None
    assert 11_800 < preload < 11_900


def test_old_load_step3_axial_is_wrong_for_static(static_golden):
    if os.getenv("ANSYS_AVAILABLE") != "1" or not STATIC_RST.exists():
        pytest.skip("ANSYS DPF required")
    from ansys_report.extract.dpf_bolt import extract_bolt_loads_dpf

    wrong = extract_bolt_loads_dpf(STATIC_RST, mode="step", load_step=3)
    assert wrong
    assert wrong[0]["axial_force_n"] < static_golden[0]["axial_force_n"] - 400


def test_static_bolt_envelope_matches_reference_axial(static_golden):
    if os.getenv("ANSYS_AVAILABLE") != "1" or not STATIC_RST.exists():
        pytest.skip("ANSYS DPF required")
    from ansys_report.config import BoltConfig
    from ansys_report.extract.bolt_loads import resolve_static_bolt_loads

    class _Cfg:
        bolts = BoltConfig()

    rows = resolve_static_bolt_loads(STATIC_RST, cfg=_Cfg())
    assert len(rows) == 8
    for row, golden in zip(rows, static_golden):
        assert row["axial_force_n"] == pytest.approx(golden["axial_force_n"], abs=1.0)


def test_shock_first_mode_produces_identical_pretension_across_directions():
    """Regression: step-1 ('first') reads pretension only — all shock tables looked the same."""
    if os.getenv("ANSYS_AVAILABLE") != "1":
        pytest.skip("ANSYS DPF required")
    if not all(p.exists() for p in SHOCK_RST.values()):
        pytest.skip("EP2737 shock RST not in workspace")
    from ansys_report.extract.dpf_bolt import extract_bolt_loads_dpf

    first_rows = {
        key: extract_bolt_loads_dpf(path, mode="first", sort_by_position=False)
        for key, path in SHOCK_RST.items()
    }
    assert first_rows["plus_x"] and first_rows["plus_y"]
    # Same pretension step → nearly identical bolt 1 axial across +X and +Y
    assert (
        abs(first_rows["plus_x"][0]["axial_force_n"] - first_rows["plus_y"][0]["axial_force_n"]) < 1.0
    )


def test_shock_envelope_differs_by_direction():
    if os.getenv("ANSYS_AVAILABLE") != "1":
        pytest.skip("ANSYS DPF required")
    if not all(p.exists() for p in SHOCK_RST.values()):
        pytest.skip("EP2737 shock RST not in workspace")
    from ansys_report.config import BoltConfig
    from ansys_report.extract.bolt_loads import resolve_shock_bolt_loads

    class _Cfg:
        bolts = BoltConfig()

    plus_x = resolve_shock_bolt_loads("plus_x", SHOCK_RST["plus_x"], cfg=_Cfg())
    plus_y = resolve_shock_bolt_loads("plus_y", SHOCK_RST["plus_y"], cfg=_Cfg())
    assert plus_x[0]["axial_force_n"] != pytest.approx(plus_y[0]["axial_force_n"], abs=500)


def test_shock_envelope_matches_word_golden_plus_x(shock_golden):
    if os.getenv("ANSYS_AVAILABLE") != "1" or not SHOCK_RST["plus_x"].exists():
        pytest.skip("ANSYS DPF required")
    from ansys_report.config import BoltConfig
    from ansys_report.extract.bolt_loads import resolve_shock_bolt_loads

    class _Cfg:
        bolts = BoltConfig()

    rows = resolve_shock_bolt_loads("plus_x", SHOCK_RST["plus_x"], cfg=_Cfg())
    golden = shock_golden["plus_x"]
    assert len(rows) == 8
    for row, ref in zip(rows, golden):
        assert row["axial_force_n"] == pytest.approx(ref["axial_force_n"], abs=1.0)
        assert row["shear_force_n"] == pytest.approx(ref["shear_force_n"], abs=15.0)


def test_production_config_uses_shock_envelope():
    from ansys_report.config import load_project_config

    cfg = load_project_config(REPO / "config" / "project.ep2737.production.yaml")
    assert cfg.bolts.shock_extraction_mode == "envelope"


def test_phase8_does_not_assert_bolt_numbers():
    """Phase 8 only checks bolt_load key exists, not Table 15–22 numerics."""
    text = (REPO / "tests" / "test_ep2737_phase8.py").read_text(encoding="utf-8")
    assert "axial_force_n" not in text
