"""Tests for per-body conclusion tables (static, shock, vibration)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "project.ep2737.yaml"


@pytest.fixture
def ep2737_cfg(ep2737_data_root):
    from ansys_report.config import load_project_config

    return load_project_config(CONFIG)


def test_static_conclusion_table_ep1581_collapses_same_material(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    static = {
        "max_stress_mpa": 460.87,
        "per_body": [
            {
                "body_name": r"13-GUIDER-CONNECTOR\Chamfer4",
                "material": "BS970 EN19",
                "max_stress_mpa": 100.0,
                "location": r"13-GUIDER-CONNECTOR\Chamfer4",
            },
            {
                "body_name": r"13-GUIDER-CONNECTOR\Fillet2",
                "material": "BS970 EN19",
                "max_stress_mpa": 460.87,
                "location": r"13-GUIDER-CONNECTOR\Fillet2",
            },
            {
                "body_name": "Gasket",
                "material": "Nylon",
                "max_stress_mpa": 45.0,
                "location": "Gasket",
            },
        ],
    }
    rows = build_static_conclusion_table(static, ep2737_cfg)
    assert len(rows) == 2
    en19 = next(r for r in rows if r["material"] == "BS970 EN19")
    assert en19["stress_mpa"] == pytest.approx(460.87, abs=0.01)
    assert en19["location"] == "13-GUIDER-CONNECTOR"


def test_static_conclusion_table_per_body(ep2737_cfg):
    from ansys_report.config import ProjectConfig
    from ansys_report.report.table_builders import build_static_conclusion_table

    ep2737_cfg.static.conclusion_table_style = "per_body"
    static = {
        "max_stress_mpa": 460.87,
        "per_body": [
            {"body_name": "Body 1", "material": "ASTM 182 F 321", "max_stress_mpa": 120.5, "location": "Body 1"},
            {"body_name": "Body 2", "material": "ASTM 182 F 321", "max_stress_mpa": 460.87, "location": "Body 2"},
            {"body_name": "Gasket", "material": "Nylon", "max_stress_mpa": 45.0, "location": "Gasket"},
        ],
    }
    rows = build_static_conclusion_table(static, ep2737_cfg)
    assert len(rows) == 3
    assert rows[1]["stress_mpa"] == pytest.approx(460.87, abs=0.01)


def test_static_conclusion_table_falls_back_to_per_material(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    static = {
        "max_stress_mpa": 460.87,
        "per_material": {
            "ASTM 182 F 321": 460.87,
            "Nylon": 45.0,
        },
    }
    context = {
        "equipment": {
            "bodies": [
                {"name": "Flange", "material": "ASTM 182 F 321"},
                {"name": "Gasket", "material": "Nylon"},
            ]
        }
    }
    rows = build_static_conclusion_table(static, ep2737_cfg, context=context)
    assert len(rows) == 2
    by_mat = {r["material"]: r for r in rows}
    assert by_mat["ASTM 182 F 321"]["stress_mpa"] == pytest.approx(460.87, abs=0.01)
    assert by_mat["Nylon"]["stress_mpa"] == pytest.approx(45.0, abs=0.01)


def test_static_conclusion_table_fallback_without_per_material_shows_pending(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    static = {"max_stress_mpa": 460.87, "per_material": {}}
    context = {
        "equipment": {
            "bodies": [
                {"name": "Flange", "material": "ASTM 182 F 321"},
                {"name": "Gasket", "material": "Nylon"},
            ]
        }
    }
    rows = build_static_conclusion_table(static, ep2737_cfg, context=context)
    assert len(rows) == 1
    assert rows[0]["stress_mpa"] == pytest.approx(460.87, abs=0.01)


def test_static_conclusion_table_single_row_without_bodies(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    static = {"max_stress_mpa": 239.63}
    rows = build_static_conclusion_table(static, ep2737_cfg)
    assert len(rows) == 1
    assert rows[0]["stress_mpa"] == pytest.approx(239.63, abs=0.01)


def test_shock_conclusion_table_ep1581_one_row_per_material_per_direction(ep2737_cfg):
    from ansys_report.report.table_builders import build_shock_conclusion_table

    shock = {
        "directions": [
            {
                "direction": "+X",
                "max_stress_mpa": 440.65,
                "per_body": [
                    {"body_name": r"A\Chamfer1", "material": "BS970 EN19", "max_stress_mpa": 400.0, "location": r"A\Chamfer1"},
                    {"body_name": r"A\Fillet1", "material": "BS970 EN19", "max_stress_mpa": 440.65, "location": r"A\Fillet1"},
                    {"body_name": "Gasket", "material": "Nylon", "max_stress_mpa": 45.0, "location": "Gasket"},
                ],
            },
        ]
    }
    rows = build_shock_conclusion_table(shock, ep2737_cfg)
    assert len(rows) == 2
    assert rows[0]["direction"] == "+X"
    assert rows[0]["material"] == "BS970 EN19"
    assert rows[0]["stress_mpa"] == pytest.approx(440.65, abs=0.01)


def test_shock_conclusion_table_expands_bodies_from_context(ep2737_cfg):
    from ansys_report.report.table_builders import build_shock_conclusion_table

    shock = {
        "directions": [
            {"direction": "+X", "max_stress_mpa": 100.0},
            {"direction": "-X", "max_stress_mpa": 110.0},
        ]
    }
    context = {
        "equipment": {
            "bodies": [
                {"name": "Part A", "material": "ASTM 182 F 321"},
                {"name": "Part B", "material": "ASTM 182 F 321"},
                {"name": "Gasket", "material": "Nylon"},
            ]
        }
    }
    rows = build_shock_conclusion_table(shock, ep2737_cfg, context=context)
    assert len(rows) == 4
    assert rows[0]["direction"] == "+X"
    assert rows[1]["material"] == "Nylon"


def test_vibration_conclusion_table_ep1581_three_rows(ep2737_cfg):
    from ansys_report.report.table_builders import build_vibration_conclusion_table

    ctx = {
        "title": "VALVE ASSEMBLY",
        "equipment": {
            "bodies": [{"name": f"Part-{i}", "material": "ASTM 182 F 321"} for i in range(20)],
            "material_names": ["ASTM 182 F 321"],
        },
        "harmonic_x": {
            "direction": "X",
            "peak_displacement_mm": 11.38,
            "peak_frequency_hz": 3.91,
            "narrative": {"verdict": "CAUTION"},
        },
        "harmonic_y": {
            "direction": "Y",
            "peak_displacement_mm": 9.0,
            "peak_frequency_hz": 4.0,
            "narrative": {"verdict": "PASS"},
        },
        "harmonic_z": {
            "direction": "Z",
            "peak_displacement_mm": 8.0,
            "peak_frequency_hz": 4.5,
            "narrative": {"verdict": "PASS"},
        },
    }
    rows = build_vibration_conclusion_table(ctx, ep2737_cfg)
    assert len(rows) == 3
    assert rows[0]["component"] == "VALVE ASSEMBLY"
    assert rows[0]["analysis"] == "Harmonic Response X"


def test_static_conclusion_table_all_worksheet_materials(ep2737_cfg):
    from ansys_report.extract.result_summary import load_result_summary, summary_to_static_result
    from ansys_report.report.table_builders import build_static_conclusion_table

    fixture = REPO / "tests" / "fixtures" / "result_summaries" / "static_structural.json"
    summary = load_result_summary(fixture)
    static = summary_to_static_result(summary, bodies=None, yield_mpa=205.0).model_dump()
    context = {
        "title": "VALVE ASSEMBLY",
        "equipment": {
            "bodies": [
                {"name": "1-VALVE-BODY", "material": "ASTM A182 F321"},
                {"name": "36-COVER", "material": "ASTM A240 S32100"},
            ]
        },
    }
    rows = build_static_conclusion_table(static, ep2737_cfg, context=context)
    assert len(rows) == 11
    assert all(r["stress_mpa"] is not None for r in rows)
    assert all("Pending" not in r["remarks"] for r in rows)


def test_vibration_conclusion_table_per_material_from_worksheet(ep2737_cfg):
    from ansys_report.extract.result_summary import load_result_summary, summary_to_harmonic_peak
    from ansys_report.report.table_builders import build_vibration_conclusion_table

    fixture = REPO / "tests" / "fixtures" / "result_summaries" / "vibration_resistance_analysis_x.json"
    summary = load_result_summary(fixture)
    harmonic = summary_to_harmonic_peak(summary).model_dump()
    harmonic["direction"] = "X"
    harmonic["narrative"] = {"verdict": "PASS"}

    ctx = {
        "title": "VALVE ASSEMBLY",
        "equipment": {
            "bodies": [
                {"name": "1-VALVE-BODY", "material": "ASTM A182 F321"},
                {"name": "13-GUIDER-CONNECTOR", "material": "BS970 EN19"},
            ],
            "material_names": ["ASTM A182 F321"],
        },
        "harmonic_x": harmonic,
    }
    rows = build_vibration_conclusion_table(ctx, ep2737_cfg)
    assert len(rows) == 3
    by_mat = {r["material"]: r for r in rows}
    assert by_mat["ASTM A182 F321"]["peak_displacement_mm"] == pytest.approx(0.142, abs=0.001)
    assert by_mat["BS970 EN19"]["peak_displacement_mm"] == pytest.approx(0.1654, abs=0.001)
    assert by_mat["BS970 EN19"]["component"] == "13-GUIDER-CONNECTOR"


def test_vibration_conclusion_table_skips_missing_displacement(ep2737_cfg):
    from ansys_report.report.table_builders import build_vibration_conclusion_table

    ctx = {
        "title": "VALVE ASSEMBLY",
        "harmonic_x": {"direction": "X", "peak_displacement_mm": None, "narrative": {"verdict": "PASS"}},
        "harmonic_y": {"direction": "Y", "peak_displacement_mm": 0.5, "peak_frequency_hz": 4.0, "narrative": {}},
    }
    rows = build_vibration_conclusion_table(ctx, ep2737_cfg)
    assert len(rows) == 1
    assert rows[0]["analysis"] == "Harmonic Response Y"


def test_enrich_context_attaches_all_conclusion_tables(ep2737_cfg):
    from ansys_report.report.table_builders import enrich_context_tables

    ctx = {
        "static": {
            "max_stress_mpa": 100.0,
            "per_body": [
                {"body_name": "A", "material": "ASTM 182 F 321", "max_stress_mpa": 100.0, "location": "A"},
            ],
        },
        "shock": {
            "directions": [
                {
                    "direction": "+X",
                    "max_stress_mpa": 90.0,
                    "per_body": [
                        {"body_name": "A", "material": "ASTM 182 F 321", "max_stress_mpa": 90.0, "location": "A"},
                    ],
                },
            ]
        },
        "harmonic_x": {
            "direction": "X",
            "peak_displacement_mm": 1.0,
            "peak_frequency_hz": 5.0,
            "narrative": {"verdict": "PASS"},
        },
        "equipment": {"bodies": [{"name": "A", "material": "ASTM 182 F 321"}], "material_names": ["ASTM 182 F 321"]},
    }
    enrich_context_tables(ctx, ep2737_cfg)
    assert len(ctx["static"]["conclusion_table"]) == 1
    assert len(ctx["shock"]["conclusion_table"]) == 1
    assert len(ctx["vibration_conclusion"]["rows"]) == 1


def test_modal_conclusion_table_ep1581(ep2737_cfg):
    from ansys_report.report.table_builders import build_modal_conclusion_table

    modal = {
        "modes": [
            {"index": 1, "freq_hz": 36.139},
            {"index": 2, "freq_hz": 145.71},
            {"index": 3, "freq_hz": 188.83},
        ]
    }
    rows = build_modal_conclusion_table(modal, ep2737_cfg, resonance_margin_hz=10.0)
    assert len(rows) == 3
    assert rows[0]["operating_frequency"] == "10 to 200 Hz"
    assert rows[0]["remark"] == "Not in or near operating Frequency"
    assert "resonance" in rows[1]["remark"].lower()


def test_modal_intro_text(ep2737_cfg):
    from ansys_report.report.table_builders import build_modal_intro_text

    modal = {"modes": [{"index": 1, "freq_hz": 36.139}]}
    text = build_modal_intro_text(modal, ep2737_cfg)
    assert "fundamental frequency" in text.lower()
    assert "36.139" in text
    assert "Transient Shock" in text


def test_harmonic_stress_conclusion_table_from_worksheet(ep2737_cfg):
    from ansys_report.extract.result_summary import load_result_summary, summary_to_harmonic_peak
    from ansys_report.report.table_builders import build_harmonic_stress_conclusion_table

    fixture = REPO / "tests" / "fixtures" / "result_summaries" / "vibration_resistance_analysis_x.json"
    summary = load_result_summary(fixture)
    harmonic = summary_to_harmonic_peak(summary).model_dump()
    harmonic["direction"] = "X"

    ctx = {
        "title": "VALVE ASSEMBLY",
        "equipment": {
            "bodies": [
                {"name": "1-VALVE-BODY", "material": "ASTM A182 F321"},
                {"name": "13-GUIDER-CONNECTOR", "material": "BS970 EN19"},
            ]
        },
        "harmonic_x": harmonic,
    }
    rows = build_harmonic_stress_conclusion_table(ctx, ep2737_cfg)
    assert len(rows) == 3
    by_mat = {r["material"]: r for r in rows}
    assert by_mat["ASTM A182 F321"]["direction"] == "Along X Axis"
    assert by_mat["BS970 EN19"]["stress_mpa"] == pytest.approx(12.4, abs=0.01)
    assert by_mat["BS970 EN19"]["remarks"] == "Stresses less than allowable."


def test_enrich_context_attaches_modal_and_stress_tables(ep2737_cfg):
    from ansys_report.report.table_builders import enrich_context_tables

    ctx = {
        "modal": {
            "modes": [{"index": 1, "freq_hz": 184.43}, {"index": 2, "freq_hz": 250.0}],
        },
        "harmonic_x": {
            "direction": "X",
            "per_material_stress": {"ASTM A182 F321": 11.99},
            "peak_displacement_mm": 1.0,
            "narrative": {"verdict": "PASS", "observations": ["Peak displacement 1 mm."]},
        },
    }
    enrich_context_tables(ctx, ep2737_cfg)
    assert len(ctx["modal"]["summary_table"]) == 2
    assert ctx["modal"]["intro_text"]
    assert len(ctx["vibration_conclusion"]["stress_table"]) == 1
    assert ctx["vibration_conclusion"]["narrative"]["observations"] == []
