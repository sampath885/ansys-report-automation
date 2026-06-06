"""Optional DPF integration tests — skipped unless ANSYS is available."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("ANSYS_AVAILABLE") != "1",
    reason="Set ANSYS_AVAILABLE=1 and RST_PATH to run DPF tests",
)


@pytest.mark.ansys
def test_dpf_static_extraction():
    rst_path = os.getenv("RST_PATH")
    if not rst_path:
        pytest.skip("RST_PATH not set")
    from pathlib import Path

    from ansys_report.extract.dpf_static import extract_static

    result = extract_static(Path(rst_path), yield_mpa=350.0)
    assert result.max_stress_mpa is not None or result.manual_fields
