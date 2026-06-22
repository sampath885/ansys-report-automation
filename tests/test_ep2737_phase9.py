"""Phase 9 tests — project init, mesh quality, loads/materials, layout template, DPF timeout."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "project.ep2737.yaml"
LAYOUT = REPO / "templates" / "EP2737_layout_template.docx"


@pytest.fixture
def ep2737_cfg(ep2737_data_root):
    from ansys_report.config import load_project_config

    return load_project_config(CONFIG)


def test_layout_template_exists():
    assert LAYOUT.exists(), "Run scripts/export_ep2737_layout_template.py once to create bundled layout"


def test_project_config_uses_bundled_layout(ep2737_cfg):
    assert ep2737_cfg.reference_layout_path is not None
    assert ep2737_cfg.reference_layout_path.name == "EP2737_layout_template.docx"
    assert ep2737_cfg.reference_layout_path.exists()


def test_mesh_quality_table_from_live_metrics(ep2737_cfg):
    from ansys_report.report.live_table_builders import build_mesh_quality_table

    modelling = {
        "quality_metrics": {
            "aspect_ratio": {"max": 7.43},
            "skewness": {"max": 0.21},
            "jacobian_ratio": {"min": 0.98},
            "element_quality": {"min": 0.81},
            "max_corner_angle_deg": {"max": 95.2},
        }
    }
    table = build_mesh_quality_table(modelling, ep2737_cfg)
    assert table is not None
    assert table["headers"][-1] == "Measured"
    assert table["rows"][0][1] == "Aspect Ratio"
    assert table["rows"][0][3] == "7.43"


def test_loads_summary_table_from_caerep():
    from ansys_report.report.live_table_builders import build_loads_summary_table

    loads = {
        "loads": [
            {"load_type": "pressure", "caption": "Internal Pressure"},
            {"load_type": "bolt_pretension", "caption": "Bolt pretension", "magnitude": 11327.0, "count": 8},
        ],
        "boundary_conditions": [{"caption": "Fixed Support", "bc_type": "fixed_support"}],
    }
    table = build_loads_summary_table(loads)
    assert table is not None
    assert len(table["rows"]) == 3
    assert "11327" in table["rows"][1][3]


def test_loads_section_extracts_caerep(ep2737_cfg, monkeypatch):
    monkeypatch.setenv("ANSYS_AVAILABLE", "0")
    from ansys_report.report.context_builder import build_context
    from ansys_report.scanner import scan_project

    inventory = scan_project(
        ep2737_cfg.project_dir,
        ep2737_cfg.image_folder,
        ep2737_cfg.excel_calcs,
        case_root=ep2737_cfg.case_root,
        excel_bolt_preload=ep2737_cfg.excel_bolt_preload,
    )
    ctx, _ = build_context(ep2737_cfg, inventory=inventory, use_ai=False)
    loads = ctx.get("loads") or {}
    assert loads.get("source") == "caerep"
    assert isinstance(loads.get("loads"), list)
    assert isinstance(loads.get("boundary_conditions"), list)

    materials = ctx.get("materials") or {}
    assert materials.get("source") in {"caerep", "config"}
    assert isinstance(materials.get("materials"), list)


def test_init_project_dry_run(ep2737_cfg):
    from ansys_report.project_init import discover_project_facts

    facts = discover_project_facts(
        ep2737_cfg.project_dir,
        case_root=ep2737_cfg.case_root,
        bom_id="EP 2737",
        title="WELDED PLANE PIPE FLANGE",
        excel_calcs=ep2737_cfg.excel_calcs,
        excel_bolt_preload=ep2737_cfg.excel_bolt_preload,
    )
    assert facts["systems_count"] == 11
    assert facts["node_count"] is not None
    assert facts["primary_material"]


def test_open_model_subprocess_ping(monkeypatch, tmp_path):
    from ansys_report.extract import dpf_base

    dpf_base.clear_dpf_cache()
    rst = tmp_path / "file.rst"
    rst.write_text("stub")

    monkeypatch.setenv("ANSYS_AVAILABLE", "1")
    monkeypatch.setenv("DPF_OPEN_TIMEOUT", "5")

    with patch.object(dpf_base, "_subprocess_ping", return_value=False) as ping:
        assert dpf_base.open_model(rst) is None
        assert ping.call_count == 1

    dpf_base.clear_dpf_cache()
    with patch.object(dpf_base, "_subprocess_ping", return_value=True) as ping:
        with patch("ansys.dpf.core.Model", side_effect=RuntimeError("boom")):
            assert dpf_base.open_model(rst) is None
        assert ping.call_count == 1


def test_open_model_reuses_cache(monkeypatch, tmp_path):
    from ansys_report.extract import dpf_base

    dpf_base.clear_dpf_cache()
    rst = tmp_path / "file.rst"
    rst.write_text("stub")

    monkeypatch.setenv("ANSYS_AVAILABLE", "1")
    sentinel = object()

    with patch.object(dpf_base, "_subprocess_ping", return_value=True) as ping:
        with patch("ansys.dpf.core.Model", return_value=sentinel):
            assert dpf_base.open_model(rst) is sentinel
            assert dpf_base.open_model(rst) is sentinel
        assert ping.call_count == 1


def test_subprocess_ping_first_only(monkeypatch, tmp_path):
    from unittest.mock import patch

    from ansys_report.extract import dpf_base

    dpf_base.clear_dpf_cache()
    rst_a = tmp_path / "a.rst"
    rst_b = tmp_path / "b.rst"
    rst_a.write_text("stub")
    rst_b.write_text("stub")

    monkeypatch.setenv("ANSYS_AVAILABLE", "1")
    monkeypatch.setenv("DPF_SUBPROCESS_PING", "first")
    model_a = object()
    model_b = object()

    with patch.object(dpf_base, "_subprocess_ping", return_value=True) as ping:
        with patch("ansys.dpf.core.Model", side_effect=[model_a, model_b]):
            assert dpf_base.open_model(rst_a) is model_a
            assert dpf_base.open_model(rst_b) is model_b
        assert ping.call_count == 1


def test_mesh_quality_overrides_report_defaults(ep2737_cfg, monkeypatch):
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
    ctx.setdefault("modelling", {})["quality_metrics"] = {
        "aspect_ratio": {"max": 6.5},
        "skewness": {"max": 0.2},
        "jacobian_ratio": {"min": 0.99},
        "element_quality": {"min": 0.8},
        "max_corner_angle_deg": {"max": 92.0},
    }
    enrich_context_tables(ctx, ep2737_cfg)
    mq = ctx["reference_tables"]["mesh_quality"]
    assert mq["headers"][-1] == "Measured"
    assert mq["rows"][0][3] == "6.5"
