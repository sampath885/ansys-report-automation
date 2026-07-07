"""Tests for semantic image fallback (static / harmonic / shock only)."""

from __future__ import annotations

from pathlib import Path

from ansys_report.images.auto_discover import resolve_assets_smart, scan_image_folder
from ansys_report.images.folder_aliases import (
    build_folder_aliases_from_resolved,
    resolve_gallery_folder,
)
from ansys_report.images.semantic_image_router import apply_semantic_fallback, semantic_fallback_enabled
from ansys_report.images.semantic_validation import validate_semantic_assignment, validate_semantic_batch
from ansys_report.images.slot_semantics import (
    is_semantic_scope_slot,
    parse_slot_semantics,
    slot_accepts_folder_role,
    slots_may_share_image,
)


def test_is_semantic_scope_slot():
    assert is_semantic_scope_slot("static_total_deformation")
    assert is_semantic_scope_slot("harmonic_x_deformation")
    assert is_semantic_scope_slot("shock_minus_z_stress_flange")
    assert not is_semantic_scope_slot("modal_mode1")
    assert not is_semantic_scope_slot("mesh_global")


def test_parse_slot_auto_description_unknown_tail():
    sem = parse_slot_semantics("static_future_metric")
    assert sem is not None
    assert sem.analysis_type == "static"
    assert sem.result_kind == "future_metric"
    assert "future metric" in sem.description.lower()
    assert "Static structural" in sem.description


def test_parse_harmonic_and_shock_without_manual_glossary():
    h = parse_slot_semantics("harmonic_y_stress_asm")
    assert h.axis == "y"
    assert "Y-direction" in h.description
    s = parse_slot_semantics("shock_plus_x_deformation")
    assert s.sign == "plus"
    assert s.axis == "x"
    assert "+X" in s.description


def test_semantic_validation_rejects_transient_for_harmonic_weird_folder():
    rel = "transient_longitudinal/solution/total_deformation.png"
    err = validate_semantic_assignment("harmonic_x_deformation", rel)
    assert err is not None


def test_semantic_validation_rejects_wrong_axis():
    rel = "vibration_resistance_analysis_y/solution/total_deformation.png"
    err = validate_semantic_assignment("harmonic_x_deformation", rel)
    assert err is not None


def test_semantic_validation_rejects_shock_sign_mismatch():
    rel = "equivalent_static_analysis_negx/solution/total_deformation.png"
    err = validate_semantic_assignment("shock_plus_x_deformation", rel)
    assert err is not None


def test_apply_semantic_fallback_with_mock_router(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    custom = exports / "custom_static_run"
    _write_png(custom / "solution" / "total_deformation.png", tiny_png)
    _write_png(custom / "solution" / "equivalent_stress.png", tiny_png)

    def mock_router(slots, paths, *, export_context=None, already_resolved=None):
        return {
            "static_total_deformation": "custom_static_run/solution/total_deformation.png",
            "static_vonmises_stress": "custom_static_run/solution/equivalent_stress.png",
        }

    indexed = scan_image_folder(exports)
    resolved, sem_slots, aliases, warnings = apply_semantic_fallback(
        exports,
        ["static_total_deformation", "static_vonmises_stress"],
        indexed,
        set(),
        enabled=True,
        router=mock_router,
    )
    assert "static_total_deformation" in resolved
    assert "static_vonmises_stress" in resolved
    assert sem_slots == {"static_total_deformation", "static_vonmises_stress"}
    assert aliases.get("static_structural") == "custom_static_run"
    assert any("Semantic fallback resolved" in w for w in warnings)


def test_resolve_assets_smart_skips_semantic_when_rules_succeed(tmp_path, tiny_png):
    """EP2741-style layout must not need Gemini."""
    exports = tmp_path / "exports"
    base = exports / "equivalent_static_analysis_posx"
    _write_png(base / "solution" / "total_deformation.png", tiny_png)

    assets = resolve_assets_smart(
        exports,
        slots=["shock_plus_x_deformation"],
        mode="auto",
        semantic_image_fallback="on",
        check_quality=False,
    )
    assert "shock_plus_x_deformation" in assets.resolved
    assert not assets.semantic_resolved_slots


def test_resolve_assets_smart_uses_semantic_for_weird_folders(tmp_path, tiny_png, monkeypatch):
    exports = tmp_path / "exports"
    folder = exports / "weird_shock_negx"
    _write_png(folder / "solution" / "total_deformation.png", tiny_png)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def mock_router(slots, paths, *, export_context=None, already_resolved=None):
        return {
            "shock_minus_x_deformation": "weird_shock_negx/solution/total_deformation.png",
        }

    from ansys_report.images import semantic_image_router

    monkeypatch.setattr(semantic_image_router, "_call_gemini_router", mock_router)

    assets = resolve_assets_smart(
        exports,
        slots=["shock_minus_x_deformation"],
        mode="auto",
        semantic_image_fallback="on",
        check_quality=False,
    )
    assert "shock_minus_x_deformation" in assets.resolved
    assert "shock_minus_x_deformation" in assets.semantic_resolved_slots
    assert assets.folder_aliases.get("equivalent_static_analysis_negx") == "weird_shock_negx"


def test_folder_aliases_from_resolved_paths(tmp_path, tiny_png):
    exports = tmp_path / "exports"
    folder = exports / "alt_harmonic_x"
    path = folder / "solution" / "total_deformation.png"
    _write_png(path, tiny_png)

    aliases = build_folder_aliases_from_resolved(
        {"harmonic_x_deformation": path.resolve()},
        exports,
    )
    assert aliases["vibration_resistance_analysis_x"] == "alt_harmonic_x"
    assert resolve_gallery_folder("vibration_resistance_analysis_x", aliases) == "alt_harmonic_x"


def test_semantic_validation_accepts_transient_for_shock_minus():
    rel = "transient_horizontal_-x-/solution/total_deformation.png"
    err = validate_semantic_assignment("shock_minus_x_deformation", rel)
    assert err is None


def test_semantic_validation_accepts_harmonic_for_shock_plus():
    rel = "harmonic_response_x/solution/total_deformation.png"
    err = validate_semantic_assignment("shock_plus_x_deformation", rel)
    assert err is None


def test_semantic_validation_rejects_transient_for_harmonic():
    rel = "transient_horizontal_-x-/solution/total_deformation.png"
    err = validate_semantic_assignment("harmonic_x_deformation", rel)
    assert err is not None


def test_semantic_validation_allows_shared_harmonic_shock_plus_path():
    rel = "harmonic_response_x/solution/total_deformation.png"
    owners = {rel.lower(): "harmonic_x_deformation"}
    accepted, rejections = validate_semantic_batch(
        {
            "harmonic_x_deformation": rel,
            "shock_plus_x_deformation": rel,
        },
        path_owners=owners,
    )
    assert accepted["harmonic_x_deformation"] == rel
    assert accepted["shock_plus_x_deformation"] == rel
    assert not rejections


def test_semantic_validation_rejects_modal_path():
    rel = "modal/solution/total_deformation.png"
    err = validate_semantic_assignment("harmonic_x_deformation", rel)
    assert err is not None


def test_slot_accepts_folder_role_separates_physics():
    assert slot_accepts_folder_role(
        "shock_minus_x_deformation",
        "transient shock -X",
    )
    assert slot_accepts_folder_role(
        "shock_plus_x_deformation",
        "Harmonic Response +X vibration",
    )
    assert not slot_accepts_folder_role(
        "shock_plus_x_deformation",
        "transient shock -X",
    )
    assert not slot_accepts_folder_role(
        "harmonic_x_deformation",
        "transient shock -X",
    )


def test_semantic_fallback_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert semantic_fallback_enabled("auto") is False
    assert semantic_fallback_enabled("off") is False


def test_semantic_fallback_enabled_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert semantic_fallback_enabled("auto") is True
    assert semantic_fallback_enabled("on") is True
    assert semantic_fallback_enabled("off") is False


def _write_png(path: Path, tiny_png: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tiny_png.read_bytes())
