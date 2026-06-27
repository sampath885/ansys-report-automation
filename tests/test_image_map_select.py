"""Tests for export-layout image map selection."""

from __future__ import annotations

from pathlib import Path

from ansys_report.config import load_project_config
from ansys_report.images.map_select import (
    detect_export_layout,
    resolve_image_map_for_exports,
)

REPO = Path(__file__).resolve().parents[1]


def test_detect_ep2741_layout(tmp_path):
    root = tmp_path / "exports"
    (root / "static_structural").mkdir(parents=True)
    assert detect_export_layout(root) == "ep2741"


def test_skip_ep2737_map_when_zero_hits(tmp_path):
    exports = tmp_path / "exports"
    (exports / "static_structural" / "loading").mkdir(parents=True)
    (exports / "static_structural" / "loading" / "pressure.png").write_bytes(b"x")
    log = exports / "auto_discover_log.txt"
    log.write_text(
        "OK [Static_Structural/loading / Pressure] -> "
        f"C:/Temp/exports/static_structural/loading/pressure.png\n",
        encoding="utf-8",
    )

    cfg = load_project_config(REPO / "config" / "project.ep2741.yaml")
    cfg.image_map_path = REPO / "config" / "ep2737_image_map.yaml"
    image_map, mode = resolve_image_map_for_exports(cfg, exports, repo_root=REPO)
    assert mode == "hybrid"
    assert image_map is not None
    assert image_map.slots.get("static_pressure") == "static_structural/loading/pressure.png"
