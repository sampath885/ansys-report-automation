"""Phase 8 tests — section content validation (live-data policy)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "project.ep2737.yaml"


@pytest.fixture
def ep2737_cfg(ep2737_data_root):
    from ansys_report.config import load_project_config

    return load_project_config(CONFIG)


def test_static_conclusion_table_uses_live_stress(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    static = {"max_stress_mpa": 239.63, "max_deformation_mm": 0.066, "fos": 0.71}
    rows = build_static_conclusion_table(static, ep2737_cfg)
    assert len(rows) == 1
    assert rows[0]["stress_mpa"] == pytest.approx(239.63, abs=0.01)
    assert rows[0]["allowable_mpa"] == pytest.approx(136.67, abs=0.01)


def test_vibration_conclusion_table(ep2737_cfg):
    from ansys_report.report.table_builders import build_vibration_conclusion_table

    ctx = {
        "harmonic_x": {
            "direction": "X",
            "peak_displacement_mm": 11.38,
            "peak_frequency_hz": 3.91,
            "narrative": {"verdict": "CAUTION"},
        },
        "harmonic_y": {
            "direction": "Y",
            "peak_displacement_mm": 11.38,
            "peak_frequency_hz": 3.91,
            "narrative": {"verdict": "CAUTION"},
        },
        "harmonic_z": {
            "direction": "Z",
            "peak_displacement_mm": 9.2,
            "peak_frequency_hz": 4.1,
            "narrative": {"verdict": "PASS"},
        },
    }
    rows = build_vibration_conclusion_table(ctx, ep2737_cfg)
    assert len(rows) == 3
    assert rows[0]["analysis"] == "Harmonic Response X"
    assert rows[2]["analysis"] == "Harmonic Response Z"


def test_dpf_golden_fallback_disabled_by_default(ep2737_cfg):
    assert ep2737_cfg.use_dpf_golden_fallback is False


def test_word_table_data_disabled_by_default(ep2737_cfg):
    assert ep2737_cfg.use_word_table_data is False


def test_data_sources_report_flags_golden(ep2737_cfg):
    from ansys_report.report.data_sources import summarize_data_sources

    ctx = {
        "modal": {"modes": [{"freq_hz": 100}], "source": "golden"},
        "static": {"max_stress_mpa": 200.0, "source": "dpf"},
    }
    rows = {r["block"]: r for r in summarize_data_sources(ctx, ep2737_cfg)}
    assert rows["modal"]["status"] == "fallback"
    assert rows["static"]["status"] == "live"

    from ansys_report.report.live_table_builders import build_centre_of_gravity_table

    equipment = {
        "assembly": {
            "cog_mm": {"x_mm": 7.98, "y_mm": 0.0, "z_mm": 0.0},
        }
    }
    table = build_centre_of_gravity_table(equipment)
    assert table is not None
    assert "7.98" in table["headers"][0]


def test_enrich_loads_report_defaults_not_word_yaml(ep2737_cfg):
    from ansys_report.report.table_builders import enrich_context_tables

    ctx = {"static": {"max_stress_mpa": 100.0}}
    enrich_context_tables(ctx, ep2737_cfg)
    refs = ctx["reference_tables"]
    assert "surface_finish_factors" in refs
    assert "revision_log" in refs
    assert "design_changes" in refs
    assert refs["revision_log"]["rows"][0][0] == "R00"


def test_section_validate_runs(ep2737_cfg, monkeypatch):
    monkeypatch.setenv("ANSYS_AVAILABLE", "0")
    from ansys_report.report.context_builder import build_context
    from ansys_report.report.section_validate import validate_section_content
    from ansys_report.report.table_builders import enrich_context_tables
    from ansys_report.scanner import scan_project

    inventory = scan_project(
        ep2737_cfg.project_dir,
        ep2737_cfg.image_folder,
        ep2737_cfg.excel_calcs,
        case_root=ep2737_cfg.case_root,
        excel_bolt_preload=ep2737_cfg.excel_bolt_preload,
    )
    ctx, _ = build_context(ep2737_cfg, inventory=inventory, use_ai=False)
    enrich_context_tables(ctx, ep2737_cfg)
    report = validate_section_content(ctx, ep2737_cfg)
    assert isinstance(report.issues, list)


def test_report_context_has_live_excel_and_standards(ep2737_cfg, monkeypatch):
    monkeypatch.setenv("ANSYS_AVAILABLE", "0")
    from ansys_report.report.context_builder import build_context
    from ansys_report.report.table_builders import enrich_context_tables
    from ansys_report.scanner import scan_project

    inventory = scan_project(
        ep2737_cfg.project_dir,
        ep2737_cfg.image_folder,
        ep2737_cfg.excel_calcs,
        case_root=ep2737_cfg.case_root,
        excel_bolt_preload=ep2737_cfg.excel_bolt_preload,
    )
    ctx, _ = build_context(ep2737_cfg, inventory=inventory, use_ai=False)
    enrich_context_tables(ctx, ep2737_cfg)
    assert ctx.get("design_calcs", {}).get("bolt_load")
    assert "surface_finish_factors" in ctx.get("reference_tables", {})
    assert "revision_log" in ctx.get("reference_tables", {})
