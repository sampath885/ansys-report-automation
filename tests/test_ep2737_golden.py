"""Phase 2 golden-file tests — require ANSYS/DPF (ANSYS_AVAILABLE=1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("ANSYS_AVAILABLE") != "1",
    reason="Set ANSYS_AVAILABLE=1 to run EP2737 DPF golden tests",
)

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "ep2737_golden"
REPO = Path(__file__).resolve().parents[1]
WB = REPO / "EP 2737" / "Structural Analysis_EP2737" / "EP2737_files" / "dp0"


@pytest.fixture
def ep2737_rst():
    if not (WB / "SYS-1" / "MECH" / "file.rst").exists():
        pytest.skip("EP2737 RST files not in workspace")


def test_modal_golden(ep2737_rst):
    from ansys_report.extract.dpf_modal import extract_modal

    golden = json.loads((GOLDEN / "2a_modal.json").read_text(encoding="utf-8"))
    result = extract_modal(WB / "SYS-1" / "MECH" / "file.rst", 6)
    for got, exp in zip(result.modes, golden["modes"], strict=True):
        assert got.freq_hz is not None
        assert abs(got.freq_hz - exp["freq_hz"]) < 0.01


def test_static_step3_golden(ep2737_rst):
    from ansys_report.extract.dpf_static import extract_static

    golden = json.loads((GOLDEN / "2b_static_step3.json").read_text(encoding="utf-8"))
    result = extract_static(WB / "SYS" / "MECH" / "file.rst", 170.0, load_step=3)
    assert result.max_stress_mpa is not None
    assert abs(result.max_stress_mpa - golden["max_stress_mpa"]) < 0.5
    assert result.max_deformation_mm is not None
    assert abs(result.max_deformation_mm - golden["max_deformation_mm"]) < 0.01


def test_harmonic_x_golden(ep2737_rst):
    from ansys_report.extract.dpf_harmonic import extract_harmonic_peak

    golden = json.loads((GOLDEN / "2c_harmonic_x.json").read_text(encoding="utf-8"))
    result = extract_harmonic_peak(WB / "SYS-2" / "MECH" / "file.rst")
    assert result.peak_displacement_mm is not None
    assert abs(result.peak_displacement_mm - golden["peak_displacement_mm"]) < 0.05


def test_shock_plus_x_golden(ep2737_rst):
    from ansys_report.extract.dpf_static import extract_static

    golden = json.loads((GOLDEN / "2d_shock_plus_x.json").read_text(encoding="utf-8"))
    result = extract_static(WB / "SYS-5" / "MECH" / "file.rst", load_step=1)
    assert result.max_stress_mpa is not None
    assert abs(result.max_stress_mpa - golden["max_stress_mpa"]) < 0.5


def test_spike_runner():
    import importlib.util

    script = REPO / "scripts" / "spikes" / "run_ep2737_spikes.py"
    spec = importlib.util.spec_from_file_location("run_ep2737_spikes", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.run_all(compare=True) == 0
