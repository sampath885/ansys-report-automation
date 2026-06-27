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


def test_static_conclusion_table_per_body(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

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
    assert rows[1]["allowable_mpa"] == pytest.approx(136.67, abs=0.01)
    assert rows[2]["remarks"] == "Stresses less than allowable."


def test_static_conclusion_table_falls_back_to_bodies(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    static = {"max_stress_mpa": 200.0}
    context = {
        "equipment": {
            "bodies": [
                {"name": "Flange", "material": "ASTM 182 F 321"},
                {"name": "Pipe", "material": "ASTM 182 F 321"},
            ]
        }
    }
    rows = build_static_conclusion_table(static, ep2737_cfg, context=context)
    assert len(rows) == 2
    assert rows[0]["location"] == "Flange"
    assert rows[0]["stress_mpa"] == pytest.approx(200.0)


def test_static_conclusion_table_single_row_without_bodies(ep2737_cfg):
    from ansys_report.report.table_builders import build_static_conclusion_table

    static = {"max_stress_mpa": 239.63}
    rows = build_static_conclusion_table(static, ep2737_cfg)
    assert len(rows) == 1
    assert rows[0]["stress_mpa"] == pytest.approx(239.63, abs=0.01)


def test_shock_conclusion_table_per_direction_per_body(ep2737_cfg):
    from ansys_report.report.table_builders import build_shock_conclusion_table

    shock = {
        "directions": [
            {
                "direction": "+X",
                "max_stress_mpa": 440.65,
                "per_body": [
                    {"body_name": "Body A", "material": "ASTM 182 F 321", "max_stress_mpa": 400.0, "location": "Body A"},
                    {"body_name": "Body B", "material": "ASTM 182 F 321", "max_stress_mpa": 440.65, "location": "Body B"},
                ],
            },
            {
                "direction": "+Y",
                "max_stress_mpa": 430.0,
                "per_body": [
                    {"body_name": "Body A", "material": "ASTM 182 F 321", "max_stress_mpa": 430.0, "location": "Body A"},
                ],
            },
        ]
    }
    rows = build_shock_conclusion_table(shock, ep2737_cfg)
    assert len(rows) == 3
    assert rows[0]["direction"] == "+X"
    assert rows[0]["location"] == "Body A"
    assert rows[2]["direction"] == "+Y"


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
            ]
        }
    }
    rows = build_shock_conclusion_table(shock, ep2737_cfg, context=context)
    assert len(rows) == 4
    assert rows[0]["direction"] == "+X"
    assert rows[0]["location"] == "Part A"
    assert rows[3]["location"] == "Part B"


def test_vibration_conclusion_table_per_body():
    from ansys_report.report.table_builders import build_vibration_conclusion_table

    ctx = {
        "equipment": {
            "bodies": [
                {"name": "Flange", "material": "ASTM 182 F 321"},
                {"name": "Bonnet", "material": "ASTM 182 F 321"},
            ],
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
    }
    rows = build_vibration_conclusion_table(ctx)
    assert len(rows) == 4
    assert rows[0]["component"] == "Flange"
    assert rows[0]["analysis"] == "Harmonic Response X"
    assert rows[2]["component"] == "Flange"
    assert rows[2]["analysis"] == "Harmonic Response Y"


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
