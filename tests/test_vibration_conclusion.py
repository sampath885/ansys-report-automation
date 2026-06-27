"""Tests for multi-direction vibration conclusion narratives."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "project.ep2737.yaml"


def _harmonic_ctx() -> dict:
    def block(direction: str, verdict: str = "PASS") -> dict:
        return {
            "direction": direction,
            "peak_displacement_mm": 0.5,
            "peak_frequency_hz": 10.0,
            "narrative": {
                "observations": [f"Harmonic {direction}: peak displacement 0.500 mm at 10.00 Hz."],
                "conclusions": ["Peak harmonic displacement is within configured warning threshold."],
                "recommendations": [],
                "verdict": verdict,
            },
        }

    return {
        "harmonic_x": block("X"),
        "harmonic_y": block("Y", "CAUTION"),
        "harmonic_z": block("Z"),
    }


def test_merge_harmonic_conclusion_narrative_all_directions():
    from ansys_report.narrative.harmonic_merge import merge_harmonic_conclusion_narrative

    merged = merge_harmonic_conclusion_narrative(
        _harmonic_ctx(),
        enabled_sections={"harmonic_x", "harmonic_y", "harmonic_z"},
    )
    assert len(merged["conclusions"]) == 3
    assert merged["verdict"] == "CAUTION"


def test_enrich_context_tables_attaches_merged_vibration_narrative():
    from ansys_report.config import load_project_config
    from ansys_report.report.table_builders import enrich_context_tables

    cfg = load_project_config(CONFIG)
    ctx = _harmonic_ctx()
    enrich_context_tables(ctx, cfg)

    conclusion = ctx["vibration_conclusion"]
    assert len(conclusion["rows"]) == 3
    assert len(conclusion["narrative"]["conclusions"]) == 3


def test_assembled_harmonic_conclusion_renders_three_conclusions(tmp_path):
    from docx import Document

    from ansys_report.config import load_project_config
    from ansys_report.report.block_assembler import assemble_ep2737_document
    from ansys_report.report.block_render import render_blocks_document
    from ansys_report.report.table_builders import enrich_context_tables

    cfg = load_project_config(CONFIG)
    cfg.sections_enabled = ["harmonic_x", "harmonic_y", "harmonic_z"]
    ctx = {
        "bom_id": "EP 2741",
        "title": "VALVE",
        "customer": "Test",
        "prepared_by": {"name": "A", "role": "B"},
        "checked_by": {"name": "C", "role": "D"},
        "approved_by": {"name": "E", "role": "F"},
        **_harmonic_ctx(),
    }
    enrich_context_tables(ctx, cfg)
    doc_model = assemble_ep2737_document(ctx, cfg)
    conclusion = next(s for s in doc_model.sections if s.key == "harmonic_conclusion")
    narrative_blocks = [b for b in conclusion.blocks if b.kind == "narrative"]
    assert len(narrative_blocks) == 1
    assert len(narrative_blocks[0].conclusions) == 3

    out = tmp_path / "vibration_conclusion.docx"
    render_blocks_document(doc_model, ctx, out)
    text = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "Harmonic X:" in text
    assert "Harmonic Y:" in text
    assert "Harmonic Z:" in text


def test_harmonic_pick_rst_by_axis_name():
    from ansys_report.models import AnalysisSystem, ProjectInventory
    from ansys_report.sections.harmonic import _pick_rst_by_axis

    inventory = ProjectInventory(
        project_dir=Path("."),
        systems={
            "sys_12": AnalysisSystem(
                key="sys_12",
                folder="SYS-12",
                display_name="Vibration Resistance Analysis Y",
                mech_dir=Path("."),
                primary_rst=Path("y.rst"),
                antype="harmonic",
            ),
            "static_structural": AnalysisSystem(
                key="static_structural",
                folder="SYS",
                display_name="Static Structural",
                mech_dir=Path("."),
                primary_rst=Path("static.rst"),
                antype="static",
            ),
        },
        rst_files={},
        image_root=Path("."),
    )
    assert _pick_rst_by_axis(inventory, "y") == Path("y.rst")
