"""Tests for per-material component figure discovery and EP1581 galleries."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXPORTS = Path(r"C:\Users\HP\AppData\Local\Temp\exports")
CONFIG = REPO / "config" / "project.ep2741.yaml"


def test_discover_static_material_figures(tmp_path):
    from ansys_report.images.component_figures import discover_gallery_figures, filename_to_material_label

    root = tmp_path / "exports"
    solution = root / "static_structural" / "solution"
    solution.mkdir(parents=True)
    (solution / "total_deformation.png").write_bytes(b"x")
    (solution / "equivalent_stress.png").write_bytes(b"x")
    (solution / "bs970_en19.png").write_bytes(b"x")
    (solution / "astm_a182_f321.png").write_bytes(b"x")

    figures = discover_gallery_figures(root, "static_structural", category="material_stress")
    labels = [f.label for f in figures]
    stems = [f.stem for f in figures]

    assert stems == ["astm_a182_f321", "bs970_en19"]
    assert filename_to_material_label("bs970_en19") == "MAT_BS970_EN19"
    assert "MAT_ASTM_A182_F321" in labels


def test_discover_gallery_with_folder_alias(tmp_path):
    from ansys_report.images.component_figures import discover_gallery_figures

    root = tmp_path / "exports"
    solution = root / "custom_static_valve" / "solution"
    solution.mkdir(parents=True)
    (solution / "bs970_en19.png").write_bytes(b"x")

    figures = discover_gallery_figures(
        root,
        "static_structural",
        category="material_stress",
        folder_aliases={"static_structural": "custom_static_valve"},
    )
    assert len(figures) == 1
    assert figures[0].stem == "bs970_en19"


def test_discover_frequency_response_figures(tmp_path):
    from ansys_report.images.component_figures import discover_gallery_figures

    root = tmp_path / "exports"
    graphs = root / "vibration_resistance_analysis_x" / "solution" / "graphs"
    graphs.mkdir(parents=True)
    (graphs / "frequency_response.png").write_bytes(b"x")
    (graphs / "other_plot.png").write_bytes(b"x")

    figures = discover_gallery_figures(
        root, "vibration_resistance_analysis_x", category="frequency_response"
    )
    assert len(figures) == 1
    assert figures[0].stem == "frequency_response"


def test_discover_frequency_response_empty_graphs_dir(tmp_path):
    from ansys_report.images.component_figures import discover_gallery_figures

    root = tmp_path / "exports"
    (root / "vibration_resistance_analysis_x" / "solution").mkdir(parents=True)

    assert discover_gallery_figures(
        root, "vibration_resistance_analysis_x", category="frequency_response"
    ) == []


def test_figure_gallery_blocks_in_static_section(tmp_path):
    from ansys_report.config import load_project_config
    from ansys_report.report.block_assembler import assemble_ep2737_document

    root = tmp_path / "exports"
    loading = root / "static_structural" / "loading"
    solution = root / "static_structural" / "solution"
    loading.mkdir(parents=True)
    solution.mkdir(parents=True)
    (loading / "loading_conditions_overview.png").write_bytes(b"png")
    (solution / "total_deformation.png").write_bytes(b"png")
    (solution / "equivalent_stress.png").write_bytes(b"png")
    (solution / "equivalent_stress_flange.png").write_bytes(b"png")
    (solution / "nes_747_part_ii.png").write_bytes(b"png")
    (solution / "structural_steel.png").write_bytes(b"png")

    cfg = load_project_config(CONFIG)
    cfg.sections_enabled = ["static"]
    ctx = {
        "image_root": str(root),
        "static": {
            "max_stress_mpa": 574.25,
            "max_deformation_mm": 1.13,
            "conclusion_table": [],
            "narrative": {"conclusions": ["OK"]},
        },
        "images": {
            "static_total_deformation": solution / "total_deformation.png",
            "static_vonmises_stress": solution / "equivalent_stress.png",
            "static_vonmises_flange": solution / "equivalent_stress_flange.png",
        },
    }

    doc = assemble_ep2737_document(ctx, cfg)
    static = next(s for s in doc.sections if s.key == "static")
    figure_blocks = [b for b in static.blocks if b.kind == "figure"]
    captions = [b.caption or "" for b in figure_blocks]

    assert any("Boundary Conditions" in c for c in captions)
    assert any("MAT_NES_747_PART_II" in c for c in captions)
    assert any("MAT_STRUCTURAL_STEEL" in c for c in captions)
    assert len(figure_blocks) >= 5


@pytest.mark.skipif(not EXPORTS.is_dir(), reason="Local Mechanical exports not present")
def test_live_exports_have_material_figures():
    from ansys_report.images.component_figures import discover_gallery_figures

    figures = discover_gallery_figures(EXPORTS, "static_structural", category="material_stress")
    assert len(figures) >= 10
    assert all(f.path.exists() for f in figures)
