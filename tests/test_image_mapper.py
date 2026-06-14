"""Image mapper tests."""

from pathlib import Path

from ansys_report.config import ImageMapConfig, load_image_map
from ansys_report.images.mapper import resolve_assets

REPO = Path(__file__).resolve().parents[1]


def test_load_ep2737_image_map():
    imap = load_image_map(REPO / "config" / "ep2737_image_map.yaml")
    assert imap.slots["modal_mode1"] == "modal/mode_01.png"
    assert imap.slots["harmonic_x_stress_asm"] == "harmonic/x/vonmises_assembly.png"


def test_resolve_present_image(tmp_path, tiny_png):
    slot_dir = tmp_path / "exports" / "static"
    slot_dir.mkdir(parents=True)
    target = slot_dir / "vonmises.png"
    target.write_bytes(tiny_png.read_bytes())

    imap = ImageMapConfig.from_mapping({"static_vonmises_stress": "static/vonmises.png"})
    assets = resolve_assets(tmp_path / "exports", imap)
    assert "static_vonmises_stress" in assets.resolved
    assert not assets.has_missing


def test_resolve_missing_image(tmp_path):
    imap = ImageMapConfig.from_mapping({"modal_mode1": "modal/mode1.png"})
    assets = resolve_assets(tmp_path / "exports", imap, check_quality=False)
    assert assets.has_missing
    assert "modal_mode1" in assets.missing_slots
