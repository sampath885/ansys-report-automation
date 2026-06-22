"""Tests for Workbench project scanner (Phase 1)."""

import pytest

from ansys_report.config import load_project_config
from ansys_report.ep2737_paths import ep2737_workbench_dir
from ansys_report.scanner import scan_project

EP2737_WB = ep2737_workbench_dir()


@pytest.fixture
def ep2737_scan_inputs(ep2737_data_root):
    wb = EP2737_WB
    if not wb.exists():
        pytest.skip("EP 2737 Workbench project not available")
    return wb, ep2737_data_root


def test_scan_ep2737_finds_eleven_systems(repo_root, ep2737_scan_inputs):
    wb, case = ep2737_scan_inputs
    inv = scan_project(
        wb,
        "exports",
        "OLF Mechanical Calculation of BOM IDs EP2737_1.xlsx",
        case_root=case,
        excel_bolt_preload="Bolt pre load.xlsx",
    )
    assert len(inv.systems) == 11
    assert "static_structural" in inv.systems
    assert "modal" in inv.systems
    assert inv.systems["modal"].folder == "SYS-1"
    assert inv.systems["static_structural"].primary_rst is not None
    assert inv.wbpj_primary is not None
    assert inv.excel_path is not None
    assert inv.cad_step is not None


def test_inventory_json_serializable(repo_root, ep2737_scan_inputs):
    wb, case = ep2737_scan_inputs
    inv = scan_project(wb, "exports", "OLF Mechanical Calculation of BOM IDs EP2737_1.xlsx", case_root=case)
    data = inv.to_json_dict()
    assert data["systems"]["vibration_x"]["folder"] == "SYS-2"
    assert len(data["systems"]) == 11


def test_discover_image_root_under_workbench_files(tmp_path):
    from ansys_report.scanner import _discover_image_root

    project = tmp_path / "EP_2741"
    files_root = project / "EP_2741_files"
    exports = files_root / "exports"
    (files_root / "dp0").mkdir(parents=True)
    exports.mkdir(parents=True)

    root, warnings = _discover_image_root(project, None, "missing/exports")
    assert root == exports.resolve()
    assert warnings == []


def test_ep2737_config_loads(repo_root, ep2737_scan_inputs):
    if not cfg_path.exists():
        pytest.skip("project.ep2737.yaml missing")
    cfg = load_project_config(cfg_path)
    inv = scan_project(
        cfg.project_dir,
        cfg.image_folder,
        cfg.excel_calcs,
        case_root=cfg.case_root,
        excel_bolt_preload=cfg.excel_bolt_preload,
    )
    assert len(inv.systems) == 11
