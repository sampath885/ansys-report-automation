"""Equipment section (§5): mass balance table and model-orientation figure."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "project.ep2741.yaml"


def test_mass_balance_table_one_row_per_body_ep1581():
    from ansys_report.config import load_project_config
    from ansys_report.report.live_table_builders import build_mass_balance_table

    cfg = load_project_config(CONFIG)
    equipment = {
        "bodies": [
            {"name": "1 Body", "material": "ASTM B 367 Gr.5", "mass_kg": 46.87267},
            {"name": "2 Disc", "material": "ASTM B 348 Gr.5", "mass_kg": 5.07028},
        ],
        "assembly": {"mass_kg": 51.94295},
    }
    table = build_mass_balance_table(equipment, cfg)
    assert table is not None
    assert table["caption"] == "Table 5 - Weight Balance Table"
    assert table["headers"] == [
        "Sl. No.",
        "Body Name",
        "Material",
        "Mass (FE Weight) (kg)",
        "Dwg. Weight (kg)",
    ]
    assert len(table["rows"]) == 3
    assert table["rows"][0] == ["1", "1 Body", "ASTM B 367 Gr.5", "46.87", ""]
    assert table["rows"][1][1] == "2 Disc"
    assert table["rows"][2][1] == "Total"


def test_model_orientation_gravity_alias_from_static(tmp_path):
    from ansys_report.images.auto_discover import _apply_image_slot_aliases

    png = tmp_path / "static_structural" / "loading" / "standard_earth_gravity.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"png")
    resolved = {"static_earth_gravity": png.resolve()}
    _apply_image_slot_aliases(resolved)
    assert resolved["model_orientation_gravity"] == png.resolve()


def test_model_orientation_gravity_from_autodiscover_log(tmp_path):
    log = tmp_path / "auto_discover_log.txt"
    exports = tmp_path / "exports"
    png = exports / "static_structural" / "loading" / "standard_earth_gravity.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"png")
    log.write_text(
        f"OK   [Static Structural/loading / Standard Earth Gravity] -> {png}\n",
        encoding="utf-8",
    )
    from ansys_report.images.log_slot_mapper import parse_autodiscover_export_log

    mapping = parse_autodiscover_export_log(log, exports)
    assert mapping["static_earth_gravity"].endswith("standard_earth_gravity.png")
    assert mapping["model_orientation_gravity"].endswith("standard_earth_gravity.png")
