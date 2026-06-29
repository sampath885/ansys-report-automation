"""Unit tests for DPF per-material stress helpers (no live ANSYS required)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ansys_report.extract.dpf_body_stress import (
    _material_ids_for_name,
    _materials_match,
    _max_vm_for_material_ids,
    _max_vm_for_material_ids_nodal,
    _max_vm_for_node_ids,
    _normalize_material,
    _resolve_stress_field,
)


@dataclass
class _FakeScoping:
    ids: list[int]


@dataclass
class _FakeConnField:
    by_index: dict[int, list[int]] = field(default_factory=dict)

    def get_entity_data_by_index(self, idx: int):
        return self.by_index[idx]

    def get_entity_data_by_id(self, eid: int):
        raise KeyError(eid)


@dataclass
class _FakeElements:
    scoping: _FakeScoping
    connectivities_field: _FakeConnField


@dataclass
class _FakeMatField:
    scoping: _FakeScoping
    data: np.ndarray


@dataclass
class _FakeMesh:
    elements: _FakeElements
    mat_by_element: dict[int, int]

    def property_field(self, prop: str):
        if prop.lower() not in {"mat", "material"}:
            raise KeyError(prop)
        eids = sorted(self.mat_by_element)
        return _FakeMatField(
            scoping=_FakeScoping(ids=eids),
            data=np.array([self.mat_by_element[eid] for eid in eids]),
        )


def _fake_mesh() -> _FakeMesh:
    # Elements 1,3 -> mat 1 (nodes 10,11 and 12,13); element 2 -> mat 2 (nodes 20,21)
    return _FakeMesh(
        elements=_FakeElements(
            scoping=_FakeScoping(ids=[1, 2, 3]),
            connectivities_field=_FakeConnField(
                by_index={0: [10, 11], 1: [20, 21], 2: [12, 13]},
            ),
        ),
        mat_by_element={1: 1, 2: 2, 3: 1},
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


def test_max_vm_for_node_ids_scopes_nodes():
    vm = np.array([30.0, 460.0, 80.0])
    node_ids = np.array([10, 11, 12])
    peak = _max_vm_for_node_ids(vm, node_ids, {11, 12})
    assert peak == 460.0


def test_max_vm_for_material_ids_nodal_maps_elements_to_nodes():
    mesh = _fake_mesh()
    vm = np.array([10.0, 460.0, 80.0, 5.0, 90.0, 45.0])
    node_ids = np.array([10, 11, 12, 13, 20, 21])
    steel_peak = _max_vm_for_material_ids_nodal(vm, node_ids, mesh, {1})
    nylon_peak = _max_vm_for_material_ids_nodal(vm, node_ids, mesh, {2})
    assert steel_peak == 460.0
    assert nylon_peak == 90.0


def test_resolve_stress_field_falls_back_to_nodal():
    class _FakeResults:
        def stress(self, time_scoping=None):
            return self

        def eval(self):
            return [_NodalField()]

    class _NodalField:
        scoping = _FakeScoping(ids=[1, 2])
        data = np.array([[100.0, 0.0, 0.0, 0.0, 0.0, 0.0]])
        unit = "MPa"

    class _FakeModel:
        results = _FakeResults()

        class metadata:
            pass

    field, is_nodal = _resolve_stress_field(_FakeModel(), load_step=3)
    assert field is not None
    assert is_nodal is True


def test_normalize_material_strips_punctuation():
    assert _normalize_material("ASTM A 276 S32100") == "astma276s32100"
