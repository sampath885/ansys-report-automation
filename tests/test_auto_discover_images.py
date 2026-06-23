"""Auto-discover image matching tests."""

from pathlib import Path

from ansys_report.config import ImageMapConfig
from ansys_report.images.auto_discover import (
    load_image_match_rules,
    resolve_assets_auto_discover,
    resolve_assets_smart,
    scan_image_folder,
)
from ansys_report.images.mapper import resolve_assets
from ansys_report.images.slots import collect_figure_slots
from ansys_report.report.section_spec import load_section_content_spec

REPO = Path(__file__).resolve().parents[1]


def _write_png(path: Path, tiny_png: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_png.read_bytes())


def test_scan_image_folder(tmp_path, tiny_png):
    _write_png(tmp_path / "mesh" / "mesh.png", tiny_png)
    _write_png(tmp_path / "modal" / "solution" / "total_deformation.png", tiny_png)
    rels = scan_image_folder(tmp_path)
    assert "mesh/mesh.png" in rels
    assert "modal/solution/total_deformation.png" in rels


def test_auto_discover_matches_mesh_and_modal(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    _write_png(exports / "mesh" / "mesh.png", tiny_png)
    _write_png(exports / "modal" / "solution" / "total_deformation.png", tiny_png)
    _write_png(exports / "modal" / "solution" / "total_deformation_2.png", tiny_png)

    rules = load_image_match_rules(REPO / "config" / "image_match_rules.yaml")
    assets = resolve_assets_auto_discover(
        exports,
        rules,
        slots=["mesh_global", "modal_mode1", "modal_mode2"],
        check_quality=False,
    )
    assert "mesh_global" in assets.resolved
    assert "modal_mode1" in assets.resolved
    assert "modal_mode2" in assets.resolved


def test_auto_discover_harmonic_axes_are_distinct(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    for axis in ("x", "y", "z"):
        base = exports / f"vibration_resistance_analysis_{axis}_direction"
        _write_png(base / "solution" / "total_deformation.png", tiny_png)

    rules = load_image_match_rules(REPO / "config" / "image_match_rules.yaml")
    assets = resolve_assets_auto_discover(
        exports,
        rules,
        slots=["harmonic_x_deformation", "harmonic_y_deformation", "harmonic_z_deformation"],
        check_quality=False,
    )
    assert assets.resolved["harmonic_x_deformation"].as_posix().endswith(
        "vibration_resistance_analysis_x_direction/solution/total_deformation.png"
    )
    assert assets.resolved["harmonic_y_deformation"].as_posix().endswith(
        "vibration_resistance_analysis_y_direction/solution/total_deformation.png"
    )
    assert assets.resolved["harmonic_z_deformation"].as_posix().endswith(
        "vibration_resistance_analysis_z_direction/solution/total_deformation.png"
    )


def test_auto_discover_harmonic_vibration_layout(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    base = exports / "vibration_resistance_analysis_x_direction"
    _write_png(base / "solution" / "total_deformation.png", tiny_png)
    _write_png(base / "solution" / "equivalent_stress.png", tiny_png)
    _write_png(base / "solution" / "graphs" / "frequency_response.png", tiny_png)

    rules = load_image_match_rules(REPO / "config" / "image_match_rules.yaml")
    assets = resolve_assets_auto_discover(
        exports,
        rules,
        slots=["harmonic_x_deformation", "harmonic_x_stress_asm", "harmonic_x_accel_plot"],
        check_quality=False,
    )
    assert assets.resolved["harmonic_x_deformation"].name == "total_deformation.png"
    assert assets.resolved["harmonic_x_stress_asm"].name == "equivalent_stress.png"
    assert assets.resolved["harmonic_x_accel_plot"].name == "frequency_response.png"


def test_hybrid_prefers_exact_map_then_fills_gaps(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    _write_png(exports / "mesh" / "mesh_global.png", tiny_png)
    _write_png(exports / "modal" / "solution" / "total_deformation.png", tiny_png)

    exact_map = ImageMapConfig.from_mapping({"mesh_global": "mesh/mesh_global.png"})
    rules = load_image_match_rules(REPO / "config" / "image_match_rules.yaml")
    assets = resolve_assets_smart(
        exports,
        slots=["mesh_global", "modal_mode1"],
        image_map=exact_map,
        rules=rules,
        mode="hybrid",
        check_quality=False,
    )
    assert assets.resolved["mesh_global"].name == "mesh_global.png"
    assert assets.resolved["modal_mode1"].name == "total_deformation.png"


def test_collect_figure_slots_includes_shock_templates():
    spec = load_section_content_spec(REPO / "config" / "ep2737_section_content.yaml")
    slots = collect_figure_slots(spec)
    assert "mesh_global" in slots
    assert "shock_plus_x_deformation" in slots
    assert "shock_minus_z_stress_flange" in slots


def test_production_image_folder_absolute(tmp_path):
    from ansys_report.production_flow import ProductionInputs, apply_production_inputs
    from ansys_report.config import load_project_config

    cfg = load_project_config(REPO / "config" / "project.ep2737.production.yaml")
    image_dir = tmp_path / "my_exports"
    image_dir.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    excel = tmp_path / "calcs.xlsx"
    excel.write_text("x")

    inputs = ProductionInputs(
        project_dir=project,
        image_assets=image_dir,
        excel_calcs=excel,
        excel_bolt_preload=None,
        out_dir=tmp_path / "out",
    )
    apply_production_inputs(cfg, inputs)
    assert cfg.image_root == image_dir.resolve()


def test_resolve_exact_map_unchanged(tmp_path, tiny_png):
    slot_dir = tmp_path / "exports" / "static"
    slot_dir.mkdir(parents=True)
    target = slot_dir / "vonmises.png"
    target.write_bytes(tiny_png.read_bytes())

    imap = ImageMapConfig.from_mapping({"static_vonmises_stress": "static/vonmises.png"})
    assets = resolve_assets(tmp_path / "exports", imap, check_quality=False)
    assert "static_vonmises_stress" in assets.resolved
