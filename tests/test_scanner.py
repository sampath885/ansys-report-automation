"""Tests for Workbench project scanner (Phase 1)."""

from pathlib import Path

import pytest

from ansys_report.config import load_project_config
from ansys_report.scanner import scan_project

EP2737_WB = Path("EP 2737/Structural Analysis_EP2737")
EP2737_CASE = Path("EP 2737")


@pytest.fixture
def ep2737_available(repo_root):
    wb = repo_root / EP2737_WB
    if not wb.exists():
        pytest.skip("EP 2737 Workbench project not in workspace")
    return wb, repo_root / EP2737_CASE


def test_scan_ep2737_finds_eleven_systems(repo_root, ep2737_available):
    wb, case = ep2737_available
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


def test_inventory_json_serializable(repo_root, ep2737_available):
    wb, case = ep2737_available
    inv = scan_project(wb, "exports", "OLF Mechanical Calculation of BOM IDs EP2737_1.xlsx", case_root=case)
    data = inv.to_json_dict()
    assert data["systems"]["vibration_x"]["folder"] == "SYS-2"
    assert len(data["systems"]) == 11


def test_ep2737_config_loads(repo_root, ep2737_available):
    cfg_path = repo_root / "config" / "project.ep2737.yaml"
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
