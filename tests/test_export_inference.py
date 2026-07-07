"""Tests for manifest-driven export inference."""

from __future__ import annotations

from ansys_report.images.export_context import build_export_context
from ansys_report.images.export_inference import (
    build_folder_aliases_from_export_context,
    classify_export_folder,
    infer_semantic_mappings_from_context,
)


def test_classify_harmonic_and_transient_folders():
    harmonic = classify_export_folder(
        {
            "folder": "harmonic_response_x",
            "analysis_names": ["Harmonic Response_X"],
            "manifest_keys": ["vibration_x"],
        }
    )
    assert harmonic["physics"] == "harmonic_vibration"
    assert harmonic["axis"] == "x"
    assert harmonic["canonical_gallery_folder"] == "vibration_resistance_analysis_x"
    assert harmonic["shock_plus_gallery_folder"] == "equivalent_static_analysis_posx"

    transient = classify_export_folder(
        {
            "folder": "transient_horizontal_-x-",
            "analysis_names": ["Transient_Horizontal -X-"],
            "manifest_keys": [],
        }
    )
    assert transient["physics"] == "shock_transient"
    assert transient["axis"] == "x"
    assert transient["sign"] == "minus"
    assert transient["canonical_gallery_folder"] == "equivalent_static_analysis_negx"


def test_infer_mappings_from_export_layout(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    _write(exports / "harmonic_response_x/solution/total_deformation.png", tiny_png)
    _write(exports / "harmonic_response_y/solution/total_deformation.png", tiny_png)
    _write(exports / "transient_horizontal_-x-/solution/total_deformation.png", tiny_png)
    _write(exports / "transient_vertical_-y-/solution/total_deformation.png", tiny_png)
    _write_manifest(exports)

    context = build_export_context(exports)
    candidates = [
        "harmonic_response_x/solution/total_deformation.png",
        "harmonic_response_y/solution/total_deformation.png",
        "transient_horizontal_-x-/solution/total_deformation.png",
        "transient_vertical_-y-/solution/total_deformation.png",
    ]
    mapping = infer_semantic_mappings_from_context(
        context,
        [
            "harmonic_x_deformation",
            "harmonic_y_deformation",
            "shock_plus_x_deformation",
            "shock_plus_y_deformation",
            "shock_minus_x_deformation",
            "shock_minus_y_deformation",
        ],
        candidates,
    )
    assert mapping["harmonic_x_deformation"] == "harmonic_response_x/solution/total_deformation.png"
    assert mapping["harmonic_y_deformation"] == "harmonic_response_y/solution/total_deformation.png"
    assert mapping["shock_plus_x_deformation"] == "harmonic_response_x/solution/total_deformation.png"
    assert mapping["shock_plus_y_deformation"] == "harmonic_response_y/solution/total_deformation.png"
    assert mapping["shock_minus_x_deformation"] == "transient_horizontal_-x-/solution/total_deformation.png"
    assert mapping["shock_minus_y_deformation"] == "transient_vertical_-y-/solution/total_deformation.png"

    aliases = build_folder_aliases_from_export_context(context)
    assert aliases["vibration_resistance_analysis_x"] == "harmonic_response_x"
    assert aliases["equivalent_static_analysis_posx"] == "harmonic_response_x"
    assert aliases["equivalent_static_analysis_negx"] == "transient_horizontal_-x-"
    assert aliases["equivalent_static_analysis_posy"] == "harmonic_response_y"
    assert aliases["equivalent_static_analysis_negy"] == "transient_vertical_-y-"


def _write_manifest(exports):
    manifest = exports / "result_summaries"
    manifest.mkdir(parents=True)
    (manifest / "manifest.json").write_text(
        """
{
  "summaries": [
    {"file": "harmonic_response_x.json", "system_key": "vibration_x", "analysis_name": "Harmonic Response_X"},
    {"file": "harmonic_response_y.json", "system_key": "vibration_y", "analysis_name": "Harmonic Response_Y"},
    {"file": "transient_horizontal_-x-.json", "analysis_name": "Transient_Horizontal -X-"},
    {"file": "transient_vertical_-y-.json", "analysis_name": "Transient_Vertical -Y-"}
  ]
}
""".strip(),
        encoding="utf-8",
    )


def _write(path, tiny_png):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_png.read_bytes())
