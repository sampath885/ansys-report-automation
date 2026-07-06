"""Modal analysis Table 11 — boundary conditions from modal CAERep."""

from __future__ import annotations

from pathlib import Path

from ansys_report.report.live_table_builders import build_modal_boundary_conditions_table

REPO = Path(__file__).resolve().parents[1]


def test_modal_boundary_table_from_caerep_data():
    modal = {
        "loads": [
            {"load_type": "acceleration", "caption": "Standard Earth Gravity", "magnitude": None},
        ],
        "boundary_conditions": [
            {"caption": "Fixed Support", "bc_type": "fixed_support"},
            {"caption": "Remote Displacement", "bc_type": "remote_displacement"},
        ],
    }
    table = build_modal_boundary_conditions_table(modal)
    assert table is not None
    assert table["caption"] == "Table 11 – Modal Analysis Boundary Conditions"
    assert table["headers"] == ["Sl. No.", "Loading or BC", "Location", "Value"]
    assert len(table["rows"]) == 3
    assert table["rows"][0][0] == "A"
    assert table["rows"][0][1] == "Standard Earth Gravity"
    assert table["rows"][1][1] == "Fixed Support"
    assert table["rows"][1][3] == "Ux=Uy=Uz=Rx=Ry=Rz=0"


def test_modal_boundary_table_omitted_when_empty():
    assert build_modal_boundary_conditions_table({"loads": [], "boundary_conditions": []}) is None
    assert build_modal_boundary_conditions_table({}) is None


def test_modal_boundary_table_assembled_in_modal_section():
    from ansys_report.config import load_project_config
    from ansys_report.report.block_assembler import assemble_report_document
    from ansys_report.report.table_builders import enrich_context_tables

    cfg = load_project_config(REPO / "config" / "project.ep2741.yaml")
    cfg.sections_enabled = ["modal"]
    ctx = {
        "modal": {
            "modes": [{"index": 1, "freq_hz": 100.0}],
            "loads": [{"load_type": "acceleration", "caption": "Standard Earth Gravity"}],
            "boundary_conditions": [{"caption": "Fixed Support", "bc_type": "fixed_support"}],
            "narrative": {"conclusions": ["OK"]},
        },
        "methodology": {"modal_methodology": "Modal method."},
    }
    enrich_context_tables(ctx, cfg)
    doc = assemble_report_document(ctx, cfg)
    modal = next(s for s in doc.sections if s.key == "modal")
    kinds = [b.kind for b in modal.blocks]
    bc_heading = next(i for i, b in enumerate(modal.blocks) if b.kind == "heading" and b.text == "Modal Analysis Boundary Conditions")
    table_idx = next(i for i, b in enumerate(modal.blocks) if b.kind == "table" and b.caption and "Table 11" in b.caption)
    results_idx = next(i for i, b in enumerate(modal.blocks) if b.kind == "heading" and b.text == "Modal Analysis Results")
    assert bc_heading < table_idx < results_idx
    assert "table" in kinds
