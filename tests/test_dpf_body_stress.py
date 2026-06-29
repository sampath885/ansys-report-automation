"""Unit tests for DPF per-material stress helpers (no live ANSYS required)."""

from __future__ import annotations

import numpy as np

from ansys_report.extract.dpf_body_stress import (
    _material_ids_for_name,
    _materials_match,
    _max_vm_for_material_ids,
    _normalize_material,
)


def test_materials_match_exact_only():
    assert _materials_match("astma182f321", "astma182f321")
    assert not _materials_match("astma182f321", "astma276s32100")
    assert not _materials_match("nylon", "astma182f321")


def test_material_ids_for_name_exact():
    mat_name_by_id = {
        1: "ASTM A182 F321",
        2: "Nylon",
    }
    ids_steel = _material_ids_for_name("ASTM 182 F 321", mat_name_by_id)
    ids_nylon = _material_ids_for_name("Nylon", mat_name_by_id)
    assert ids_steel == {1}
    assert ids_nylon == {2}


def test_materials_match_astm_variants():
    from ansys_report.extract.dpf_body_stress import _materials_match

    assert _materials_match("astm182f321", "astma182f321")
    assert not _materials_match("astma276s32100", "astma182f321")


def test_max_vm_for_material_ids_scopes_elements():
    vm = np.array([10.0, 200.0, 50.0])
    element_ids = np.array([1, 2, 3])
    mat_ids = np.array([1, 2, 1])
    peak = _max_vm_for_material_ids(vm, element_ids, mat_ids, {2})
    assert peak == 200.0


def test_normalize_material_strips_punctuation():
    assert _normalize_material("ASTM A 276 S32100") == "astma276s32100"
