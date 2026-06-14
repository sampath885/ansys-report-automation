"""Phase 3 metadata tests — no ANSYS/DPF required."""

import json
from pathlib import Path

import pytest

from ansys_report.ep2737_paths import ep2737_dp0

REPO = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "ep2737_golden"
CONFIG = REPO / "config" / "project.ep2737.yaml"
WB = ep2737_dp0()


@pytest.fixture
def ep2737_case(ep2737_data_root):
    if not (WB / "SYS" / "MECH" / "CAERep.xml").exists():
        pytest.skip("EP2737 CAERep not available")


@pytest.fixture
def inventory(ep2737_case):
    from ansys_report.config import load_project_config
    from ansys_report.scanner import scan_project

    cfg = load_project_config(CONFIG)
    return scan_project(
        cfg.project_dir,
        cfg.image_folder,
        cfg.excel_calcs,
        case_root=cfg.case_root,
        excel_bolt_preload=cfg.excel_bolt_preload,
    )


def test_metadata_golden(inventory):
    from ansys_report.config import load_project_config
    from ansys_report.extract.metadata import extract_project_metadata

    golden = json.loads((GOLDEN / "3_metadata.json").read_text(encoding="utf-8"))
    cfg = load_project_config(CONFIG)
    meta = extract_project_metadata(inventory, cfg.bom_id, cfg.title)
    payload = meta.to_json_dict()

    assert payload["modelling"]["node_count"] == golden["modelling"]["node_count"]
    assert payload["modelling"]["element_count"] == golden["modelling"]["element_count"]
    assert payload["equipment"]["assembly"]["mass_kg"] == pytest.approx(
        golden["equipment"]["assembly"]["mass_kg"], abs=0.01
    )

    pret = next(l for l in payload["modelling"]["loads"] if l["load_type"] == "bolt_pretension")
    gpret = next(l for l in golden["modelling"]["loads"] if l["load_type"] == "bolt_pretension")
    assert pret["count"] == gpret["count"] == 8
    assert pret["magnitude"] == pytest.approx(gpret["magnitude"], abs=0.01)

    steel = next(m for m in payload["modelling"]["materials"] if m["name"] == "ASTM 182 F 321")
    gsteel = next(m for m in golden["modelling"]["materials"] if m["name"] == "ASTM 182 F 321")
    assert steel["youngs_modulus_gpa"] == gsteel["youngs_modulus_gpa"] == 195.0
    assert steel["density_kg_m3"] == gsteel["density_kg_m3"] == 8030


def test_caerep_bodies_distinct_materials(inventory):
    from ansys_report.extract.metadata import extract_equipment_metadata

    cfg_bom = "EP 2737"
    eq = extract_equipment_metadata(inventory, cfg_bom, "Test")
    materials = {b.material for b in eq.bodies if b.material}
    assert "ASTM 182 F 321" in materials
    assert "Nylon" in materials
    assert eq.assembly is not None
    assert eq.assembly.mass_kg == pytest.approx(17.1824, abs=0.01)


def test_metadata_runner():
    import importlib.util

    script = REPO / "scripts" / "spikes" / "run_ep2737_metadata.py"
    spec = importlib.util.spec_from_file_location("run_ep2737_metadata", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.run_metadata(compare=True) == 0
