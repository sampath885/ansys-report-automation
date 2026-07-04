"""Tests for Mechanical worksheet Result Summary loading and conversion."""

from __future__ import annotations

from pathlib import Path

import pytest

from ansys_report.extract.result_summary import (
    discover_result_summaries,
    load_result_summary,
    merge_static_results,
    pick_result_summary,
    summary_to_static_result,
)
from ansys_report.models import BodyMetadata, ProjectInventory, StaticResult

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "result_summaries" / "static_structural.json"
CONFIG = REPO / "config" / "project.ep2737.yaml"


@pytest.fixture
def ep2737_cfg(ep2737_data_root):
    from ansys_report.config import load_project_config

    return load_project_config(CONFIG)


def test_load_result_summary_fixture():
    summary = load_result_summary(FIXTURE)
    assert summary is not None
    assert summary.system_key == "static_structural"
    assert len(summary.rows) >= 12
    assert summary.rows[0].result == "Total Deformation"
    assert summary.rows[0].maximum == pytest.approx(1.1324)


def test_summary_to_static_result_per_material():
    summary = load_result_summary(FIXTURE)
    bodies = [
        BodyMetadata(name="1-VALVE-BODY", material="ASTM A182 F321"),
        BodyMetadata(name="36-COVER", material="ASTM A240 S32100"),
        BodyMetadata(name="19-SPINDLE-CASING-ASSEMBLY", material="ASTM A351 CF8M"),
    ]
    static = summary_to_static_result(summary, bodies, yield_mpa=205.0)

    assert static.max_stress_mpa == pytest.approx(574.25)
    assert static.max_deformation_mm == pytest.approx(1.1324)
    assert static.fos == pytest.approx(0.36, abs=0.01)
    assert static.extraction_source == "worksheet_summary"
    assert static.per_material["ASTM A351 CF8M"] == pytest.approx(574.25)
    assert len(static.per_body) == 3
    stresses = {row.material: row.max_stress_mpa for row in static.per_body}
    assert stresses["ASTM A182 F321"] == pytest.approx(326.84)
    assert stresses["ASTM A240 S32100"] == pytest.approx(140.04)


def test_merge_static_prefers_worksheet_per_material():
    summary = load_result_summary(FIXTURE)
    primary = summary_to_static_result(summary, yield_mpa=205.0)
    fallback = StaticResult(
        max_stress_mpa=460.87,
        max_deformation_mm=0.278,
        reaction_force_n=171.7,
        per_body=[],
        extraction_source="dpf",
    )
    merged = merge_static_results(primary, fallback)

    assert merged.max_stress_mpa == pytest.approx(574.25)
    assert merged.max_deformation_mm == pytest.approx(1.1324)
    assert merged.reaction_force_n == pytest.approx(171.7)
    assert merged.extraction_source == "worksheet_summary"


def test_summary_to_harmonic_peak_per_material():
    from ansys_report.extract.result_summary import load_result_summary, summary_to_harmonic_peak

    path = REPO / "tests" / "fixtures" / "result_summaries" / "vibration_resistance_analysis_x.json"
    summary = load_result_summary(path)
    peak = summary_to_harmonic_peak(summary)

    assert peak.peak_displacement_mm == pytest.approx(0.1654, abs=0.001)
    assert peak.per_material["ASTM A182 F321"] == pytest.approx(0.142, abs=0.001)
    assert peak.per_material_stress["BS970 EN19"] == pytest.approx(12.4, abs=0.01)
    assert peak.max_stress_mpa == pytest.approx(120.5, abs=0.01)
    assert peak.extraction_source == "worksheet_summary"


def test_discover_result_summaries_from_fixture_dir(tmp_path):
    dest = tmp_path / "exports" / "result_summaries"
    dest.mkdir(parents=True)
    (dest / "static_structural.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    mapped = discover_result_summaries(tmp_path / "exports")
    assert mapped["static_structural"] == (dest / "static_structural.json").resolve()

    inventory = ProjectInventory(
        project_dir=tmp_path,
        image_root=tmp_path / "exports",
        result_summaries=mapped,
    )
    picked = pick_result_summary(inventory, "static_structural")
    assert picked is not None
    assert len(picked.rows) >= 12


def test_summary_populates_static_conclusion_table(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    summary = load_result_summary(FIXTURE)
    bodies = [
        BodyMetadata(name="1-VALVE-BODY", material="ASTM A182 F321"),
        BodyMetadata(name="36-COVER", material="ASTM A240 S32100"),
        BodyMetadata(name="13-GUIDER-CONNECTOR", material="BS970 EN19"),
    ]
    static = summary_to_static_result(summary, bodies, yield_mpa=205.0).model_dump()
    context = {"equipment": {"bodies": [b.model_dump() for b in bodies]}, "title": "VALVE ASSEMBLY"}
    rows = build_static_conclusion_table(static, ep2737_cfg, context=context)

    assert len(rows) == 3
    by_mat = {r["material"]: r for r in rows}
    assert by_mat["ASTM A182 F321"]["stress_mpa"] == pytest.approx(326.84, abs=0.01)
    assert by_mat["ASTM A240 S32100"]["stress_mpa"] == pytest.approx(140.04, abs=0.01)
    assert by_mat["BS970 EN19"]["stress_mpa"] == pytest.approx(199.94, abs=0.01)
    assert all("Pending" not in r["remarks"] for r in rows)
