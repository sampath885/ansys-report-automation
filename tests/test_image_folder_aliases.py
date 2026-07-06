"""Tests for flexible Mechanical export folder naming."""

from pathlib import Path

from ansys_report.config import ImageMapConfig
from ansys_report.images.analysis_registry import path_allowed_for_slot, resolve_export_folder
from ansys_report.images.auto_discover import resolve_assets_smart
from ansys_report.images.component_figures import discover_gallery_figures
from ansys_report.images.image_validation import validate_resolved_images
from ansys_report.images.mapper import resolve_assets


def _write_png(path: Path, tiny_png: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_png.read_bytes())


def test_harmonic_response_x_allowed_for_harmonic_x_slot():
    rel = "harmonic_response_x/solution/total_deformation.png"
    assert path_allowed_for_slot("harmonic_x_deformation", rel)


def test_image_map_alias_resolves_harmonic_response_folder(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    actual = "harmonic_response_x/solution/total_deformation.png"
    _write_png(exports / actual, tiny_png)

    image_map = ImageMapConfig.from_mapping(
        {"harmonic_x_deformation": "vibration_resistance_analysis_x/solution/total_deformation.png"}
    )
    assets = resolve_assets(exports, image_map, check_quality=False)
    assert "harmonic_x_deformation" in assets.resolved
    assert "harmonic_response_x" in assets.resolved["harmonic_x_deformation"].as_posix()


def test_hybrid_resolves_harmonic_y_and_z_with_response_folders(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    _write_png(exports / "harmonic_response_y/solution/total_deformation.png", tiny_png)
    _write_png(exports / "harmonic_response_z/solution/total_deformation.png", tiny_png)

    image_map = ImageMapConfig.from_mapping(
        {
            "harmonic_y_deformation": "vibration_resistance_analysis_y/solution/total_deformation.png",
            "harmonic_z_deformation": "vibration_resistance_analysis_z/solution/total_deformation.png",
        }
    )
    assets = resolve_assets_smart(
        exports,
        slots=["harmonic_y_deformation", "harmonic_z_deformation"],
        image_map=image_map,
        mode="hybrid",
        check_quality=False,
    )
    assert "harmonic_y_deformation" in assets.resolved
    assert "harmonic_z_deformation" in assets.resolved
    errors, warnings = validate_resolved_images(assets.resolved, exports)
    assert not any("does not match required folder" in msg for msg in warnings)


def test_resolve_export_folder_maps_harmonic_and_shock_aliases(tmp_path):
    root = tmp_path / "exports"
    root.mkdir()
    (root / "harmonic_response_x").mkdir()
    (root / "transient_horizontal_-x-").mkdir()

    assert resolve_export_folder(root, "vibration_resistance_analysis_x") == "harmonic_response_x"
    assert resolve_export_folder(root, "equivalent_static_analysis_negx") == "transient_horizontal_-x-"


def test_gallery_finds_harmonic_bc_with_canonical_folder(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    rel = "harmonic_response_x/loading/loading_conditions_overview.png"
    path = exports / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(tiny_png.read_bytes())

    figs = discover_gallery_figures(
        exports,
        "vibration_resistance_analysis_x",
        subfolder="loading",
        filename="loading_conditions_overview.png",
    )
    assert len(figs) == 1
    assert "harmonic_response_x" in figs[0].rel_path


def test_hybrid_resolves_transient_shock_minus_x(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    folder = "transient_horizontal_-x-"
    rel = f"{folder}/solution/total_deformation.png"
    path = exports / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(tiny_png.read_bytes())

    image_map = ImageMapConfig.from_mapping(
        {"shock_minus_x_deformation": "equivalent_static_analysis_negx/solution/total_deformation.png"}
    )
    assets = resolve_assets_smart(
        exports,
        slots=["shock_minus_x_deformation"],
        image_map=image_map,
        mode="hybrid",
        check_quality=False,
    )
    assert "shock_minus_x_deformation" in assets.resolved
    assert folder in assets.resolved["shock_minus_x_deformation"].as_posix()


def test_harmonic_location_accepts_displacement_export(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    rel = "harmonic_response_x/loading/displacement.png"
    path = exports / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(tiny_png.read_bytes())

    image_map = ImageMapConfig.from_mapping(
        {"harmonic_x_location": "vibration_resistance_analysis_x/loading/acceleration.png"}
    )
    assets = resolve_assets(exports, image_map, check_quality=False)
    assert "harmonic_x_location" in assets.resolved
    assert assets.resolved["harmonic_x_location"].name == "displacement.png"
