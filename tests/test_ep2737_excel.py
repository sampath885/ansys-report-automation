"""Phase 4 Excel tests — no ANSYS/DPF required."""

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "ep2737_golden"
CONFIG = REPO / "config" / "project.ep2737.yaml"
MAP = REPO / "config" / "ep2737_excel_map.yaml"
CASE = REPO / "EP 2737"


@pytest.fixture
def ep2737_excel():
    if not (CASE / "OLF Mechanical Calculation of BOM IDs EP2737_1.xlsx").exists():
        pytest.skip("EP2737 Excel files not in workspace")


@pytest.fixture
def ep2737_cfg(ep2737_excel):
    from ansys_report.config import load_project_config

    return load_project_config(CONFIG)


def test_excel_golden(ep2737_cfg):
    from ansys_report.excel.reader import read_design_calcs
    from ansys_report.excel.ep2737 import summarize_for_golden

    golden = json.loads((GOLDEN / "4_excel.json").read_text(encoding="utf-8"))
    case_root = ep2737_cfg.case_root or ep2737_cfg.project_dir
    result = read_design_calcs(
        ep2737_cfg.excel_path,
        excel_map_path=ep2737_cfg.excel_map_path or MAP,
        case_root=case_root,
        fos_target=ep2737_cfg.static.fos_target,
    )
    summary = summarize_for_golden(result)

    assert summary["end_flange"]["fos"] == pytest.approx(golden["end_flange"]["fos"], abs=0.001)
    assert summary["effort"]["preload_n"] == pytest.approx(golden["effort"]["preload_n"], abs=0.01)
    assert summary["effort"]["preload_n"] == pytest.approx(11832.54, abs=0.01)
    assert summary["bolt_load"]["bolt_count"] == 8
    assert summary["end_flange"]["stress_verdict"] == "ACCEPTED"


def test_preload_matches_ansys_metadata(ep2737_cfg):
    """Excel preload must match Phase 3 CAERep pretension (11832.54 N)."""
    from ansys_report.excel.ep2737 import read_ep2737_design_calcs, summarize_for_golden

    case_root = ep2737_cfg.case_root or ep2737_cfg.project_dir
    result = read_ep2737_design_calcs(case_root, MAP, fos_target=1.5)
    summary = summarize_for_golden(result)
    assert summary["effort"]["preload_n"] == pytest.approx(11832.5394311494, abs=0.001)


def test_fos_verdict(ep2737_cfg):
    from ansys_report.excel.reader import read_design_calcs

    case_root = ep2737_cfg.case_root or ep2737_cfg.project_dir
    result = read_design_calcs(
        ep2737_cfg.excel_path,
        excel_map_path=MAP,
        case_root=case_root,
        fos_target=1.5,
    )
    fos_rows = [r for r in result.end_flange if "FACTOR OF SAFETY" in r.label.upper()]
    assert fos_rows
    assert fos_rows[0].verdict == "ACCEPTABLE"


def test_excel_runner():
    import importlib.util

    script = REPO / "scripts" / "spikes" / "run_ep2737_excel.py"
    spec = importlib.util.spec_from_file_location("run_ep2737_excel", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.run_excel(compare=True) == 0
