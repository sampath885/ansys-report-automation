"""Per-body / per-material von-Mises stress extraction via DPF."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from ansys_report.extract.dpf_base import open_model, von_mises_max_mpa
from ansys_report.extract.dpf_timing import log_dpf_step
from ansys_report.models import BodyMetadata, BodyStressRow

logger = logging.getLogger(__name__)


def extract_per_body_stress(
    rst_path: Path,
    bodies: list[BodyMetadata],
    *,
    load_step: int | None = None,
) -> list[BodyStressRow]:
    """Return one row per CAERep body with peak von-Mises stress (MPa)."""
    if not bodies:
        return []

    with log_dpf_step(f"per-body stress step={load_step or 'all'}", rst_path):
        model = open_model(rst_path)
        if model is None:
            return []

        try:
            rows = _extract_per_body(model, bodies, load_step=load_step)
            if rows and any(row.max_stress_mpa is not None for row in rows):
                return rows
            logger.info("Per-body scoping empty for %s; falling back to per-material peaks", rst_path.name)
            return extract_per_material_stress(model, bodies, load_step=load_step)
        except Exception as exc:
            logger.warning("Per-body stress extraction failed for %s: %s", rst_path.name, exc)
            try:
                return extract_per_material_stress(model, bodies, load_step=load_step)
            except Exception as inner:
                logger.warning("Per-material stress fallback failed for %s: %s", rst_path.name, inner)
                return []


def extract_per_material_stress(
    model,
    bodies: list[BodyMetadata],
    *,
    load_step: int | None = None,
) -> list[BodyStressRow]:
    """One row per unique CAERep material using mesh material property scoping."""
    stress_field, is_nodal = _resolve_stress_field(model, load_step)
    if stress_field is None:
        return []

    vm_values = _von_mises_array(stress_field)
    if vm_values is None or len(vm_values) == 0:
        return []

    mesh = model.metadata.meshed_region
    entity_ids = np.asarray(stress_field.scoping.ids, dtype=np.int64)
    mat_name_by_id = _material_names_by_id(model)
    mat_ids = None if is_nodal else _element_material_ids(mesh, entity_ids)
    if not is_nodal and mat_ids is None:
        return []

    material_to_body: dict[str, str] = {}
    for body in bodies:
        if body.material and body.material not in material_to_body:
            material_to_body[body.material] = body.name

    rows: list[BodyStressRow] = []
    for material, body_name in material_to_body.items():
        target_ids = _material_ids_for_name(material, mat_name_by_id)
        if not target_ids:
            logger.debug("No DPF material id match for CAERep material %r", material)
            continue
        if is_nodal:
            max_stress = _max_vm_for_material_ids_nodal(vm_values, entity_ids, mesh, target_ids)
        else:
            max_stress = _max_vm_for_material_ids(vm_values, entity_ids, mat_ids, target_ids)
        rows.append(
            BodyStressRow(
                body_name=body_name,
                material=material,
                max_stress_mpa=max_stress,
                location=body_name,
            )
        )
    return rows


def _extract_per_body(model, bodies: list[BodyMetadata], *, load_step: int | None) -> list[BodyStressRow]:
    stress_field, is_nodal = _resolve_stress_field(model, load_step)
    if stress_field is None:
        return []

    vm_values = _von_mises_array(stress_field)
    if vm_values is None or len(vm_values) == 0:
        return []

    mesh = model.metadata.meshed_region
    entity_ids = np.asarray(stress_field.scoping.ids, dtype=np.int64)
    mat_ids = None if is_nodal else _element_material_ids(mesh, entity_ids)
    mat_name_by_id = _material_names_by_id(model)

    rows: list[BodyStressRow] = []
    for body in bodies:
        max_stress = _stress_for_body(
            mesh,
            body,
            vm_values=vm_values,
            entity_ids=entity_ids,
            mat_ids=mat_ids,
            mat_name_by_id=mat_name_by_id,
            is_nodal=is_nodal,
        )
        rows.append(
            BodyStressRow(
                body_name=body.name,
                material=body.material,
                max_stress_mpa=max_stress,
                location=body.name,
            )
        )
    return rows


def _resolve_stress_field(model, load_step: int | None) -> tuple[Any, bool]:
    """Return (stress_field, is_nodal). Prefer elemental; fall back to nodal stress."""
    field = _elemental_stress_field(model, load_step)
    if field is not None:
        return field, False
    field = _nodal_stress_field(model, load_step)
    if field is not None:
        logger.info("Elemental stress unavailable; using nodal stress for per-material scoping")
        return field, True
    logger.warning("Could not obtain stress field from DPF (elemental or nodal)")
    return None, False


def _nodal_stress_field(model, load_step: int | None):
    """Nodal stress field; same API path as global max in dpf_static.py."""
    time_scoping = load_step if load_step is not None else None
    try:
        if time_scoping is not None:
            fc = model.results.stress(time_scoping=time_scoping).eval()
        else:
            fc = model.results.stress().eval()
        if fc:
            return fc[0]
    except Exception as exc:
        logger.debug("DPF nodal stress failed: %s", exc)
    return None


def _elemental_stress_field(model, load_step: int | None):
    """Elemental stress field; compatible with DPF builds that reject location= on Result.stress()."""
    from ansys.dpf import core as dpf

    time_scoping = load_step if load_step is not None else None

    try:
        if time_scoping is not None:
            fc = model.results.stress(time_scoping=time_scoping, location=dpf.locations.elemental).eval()
        else:
            fc = model.results.stress(location=dpf.locations.elemental).eval()
        if fc:
            return fc[0]
    except TypeError:
        pass

    try:
        op = dpf.operators.result.stress()
        op.inputs.data_sources(model.metadata.data_sources)
        if time_scoping is not None:
            op.inputs.time_scoping(time_scoping)
        op.inputs.request_location(dpf.locations.elemental)
        fc = op.outputs.fields_container()
        if fc is not None and len(fc) > 0:
            return fc[0]
    except Exception as exc:
        logger.debug("DPF stress operator (elemental) failed: %s", exc)

    try:
        op = dpf.operators.result.elemental_stress()
        op.inputs.data_sources(model.metadata.data_sources)
        if time_scoping is not None:
            op.inputs.time_scoping(time_scoping)
        fc = op.outputs.fields_container()
        if fc is not None and len(fc) > 0:
            return fc[0]
    except Exception as exc:
        logger.debug("DPF elemental_stress operator failed: %s", exc)

    logger.debug("Could not obtain elemental stress field from DPF")
    return None


def _stress_for_body(
    mesh,
    body: BodyMetadata,
    *,
    vm_values: np.ndarray,
    entity_ids: np.ndarray,
    mat_ids: np.ndarray | None,
    mat_name_by_id: dict[int, str],
    is_nodal: bool = False,
) -> float | None:
    scoped = _named_selection_scoping(mesh, body.name)
    if scoped is not None and scoped.size:
        scoped_ids = {int(x) for x in scoped.ids}
        if is_nodal:
            peak = _max_vm_for_node_ids(vm_values, entity_ids, scoped_ids)
            if peak is not None:
                return peak
            target_nodes = _nodes_for_elements(mesh, scoped_ids)
            return _max_vm_for_node_ids(vm_values, entity_ids, target_nodes)
        return _max_vm_for_element_ids(vm_values, entity_ids, scoped_ids)

    if body.material:
        target_ids = _material_ids_for_name(body.material, mat_name_by_id)
        if target_ids:
            if is_nodal:
                return _max_vm_for_material_ids_nodal(vm_values, entity_ids, mesh, target_ids)
            if mat_ids is not None:
                return _max_vm_for_material_ids(vm_values, entity_ids, mat_ids, target_ids)

    return None


def _max_vm_for_element_ids(
    vm_values: np.ndarray,
    element_ids: np.ndarray,
    target_ids: set[int],
) -> float | None:
    if not target_ids:
        return None
    mask = np.isin(element_ids, list(target_ids))
    if not np.any(mask):
        return None
    return float(np.max(vm_values[mask]))


def _max_vm_for_material_ids(
    vm_values: np.ndarray,
    element_ids: np.ndarray,
    mat_ids: np.ndarray,
    target_mat_ids: set[int],
) -> float | None:
    if not target_mat_ids:
        return None
    mask = np.isin(mat_ids, list(target_mat_ids))
    if not np.any(mask):
        return None
    return float(np.max(vm_values[mask]))


def _max_vm_for_node_ids(
    vm_values: np.ndarray,
    node_ids: np.ndarray,
    target_node_ids: set[int],
) -> float | None:
    if not target_node_ids:
        return None
    mask = np.isin(node_ids, list(target_node_ids))
    if not np.any(mask):
        return None
    return float(np.max(vm_values[mask]))


def _max_vm_for_material_ids_nodal(
    vm_values: np.ndarray,
    node_ids: np.ndarray,
    mesh,
    target_mat_ids: set[int],
) -> float | None:
    """Peak nodal von Mises over all nodes belonging to elements of the given materials."""
    if not target_mat_ids:
        return None
    element_ids = _all_mesh_element_ids(mesh)
    mat_ids = _element_material_ids(mesh, element_ids)
    if mat_ids is None:
        return None
    target_elements = {
        int(eid) for eid, mid in zip(element_ids, mat_ids, strict=False) if int(mid) in target_mat_ids
    }
    if not target_elements:
        return None
    target_nodes = _nodes_for_elements(mesh, target_elements)
    return _max_vm_for_node_ids(vm_values, node_ids, target_nodes)


def _all_mesh_element_ids(mesh) -> np.ndarray:
    return np.asarray(mesh.elements.scoping.ids, dtype=np.int64)


def _nodes_for_elements(mesh, target_element_ids: set[int]) -> set[int]:
    if not target_element_ids:
        return set()
    nodes: set[int] = set()
    elements = mesh.elements
    conn = elements.connectivities_field
    for idx, eid in enumerate(elements.scoping.ids):
        if int(eid) not in target_element_ids:
            continue
        try:
            data = conn.get_entity_data_by_index(idx)
        except Exception:
            try:
                data = conn.get_entity_data_by_id(int(eid))
            except Exception:
                continue
        nodes.update(int(n) for n in np.asarray(data).flatten())
    return nodes


def _von_mises_array(stress_field) -> np.ndarray | None:
    data = stress_field.data
    if data is None or len(data) == 0:
        return None
    if data.shape[1] < 6:
        peak = von_mises_max_mpa(stress_field)
        return np.array([peak]) if peak is not None else None
    vm = np.sqrt(
        0.5
        * (
            (data[:, 0] - data[:, 1]) ** 2
            + (data[:, 1] - data[:, 2]) ** 2
            + (data[:, 2] - data[:, 0]) ** 2
            + 6 * (data[:, 3] ** 2 + data[:, 4] ** 2 + data[:, 5] ** 2)
        )
    )
    unit = getattr(stress_field, "unit", "MPa") or "MPa"
    if unit.lower() in ("pa", "n/m^2", "n/m**2"):
        vm = vm / 1e6
    elif unit.lower() == "kpa":
        vm = vm / 1e3
    return vm


def _element_material_ids(mesh, element_ids: np.ndarray) -> np.ndarray | None:
    from ansys.dpf import core as dpf

    for prop in ("mat", "Mat", "Material"):
        try:
            mat_field = mesh.property_field(prop)
            ids = np.asarray(mat_field.scoping.ids, dtype=np.int64)
            data = np.asarray(mat_field.data).flatten()
            lookup = {int(eid): int(data[i]) for i, eid in enumerate(ids)}
            mapped = np.array([lookup.get(int(eid), -1) for eid in element_ids], dtype=np.int64)
            if np.any(mapped >= 0):
                return mapped
        except Exception:
            continue

    try:
        prop = dpf.common.naming.property.mat
        mat_field = mesh.property_field(prop)
        ids = np.asarray(mat_field.scoping.ids, dtype=np.int64)
        data = np.asarray(mat_field.data).flatten()
        lookup = {int(eid): int(data[i]) for i, eid in enumerate(ids)}
        return np.array([lookup.get(int(eid), -1) for eid in element_ids], dtype=np.int64)
    except Exception:
        return None


def _material_names_by_id(model) -> dict[int, str]:
    names: dict[int, str] = {}
    try:
        for mat in model.metadata.materials:
            mat_id = getattr(mat, "id", None)
            if mat_id is None:
                mat_id = getattr(mat, "material_id", None)
            if mat_id is None:
                continue
            label = getattr(mat, "name", None) or getattr(mat, "caption", None) or str(mat)
            names[int(mat_id)] = str(label)
    except Exception:
        pass

    if names:
        return names

    try:
        for idx, mat in enumerate(model.metadata.materials, start=1):
            label = getattr(mat, "name", None) or getattr(mat, "caption", None) or str(mat)
            names[idx] = str(label)
    except Exception:
        pass
    return names


def _material_ids_for_name(material_name: str, mat_name_by_id: dict[int, str]) -> set[int]:
    target = _canonical_material_key(material_name)
    if not target:
        return set()
    matched: set[int] = set()
    for mat_id, name in mat_name_by_id.items():
        if _materials_match(target, _canonical_material_key(name)):
            matched.add(mat_id)
    return matched


def _normalize_material(name: str | None) -> str:
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _canonical_material_key(name: str | None) -> str:
    """Collapse common ASTM spelling variants for CAERep ↔ DPF name matching."""
    key = _normalize_material(name)
    return key.replace("astma", "astm")


def _materials_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return _canonical_material_key(left) == _canonical_material_key(right)


def _named_selection_scoping(mesh, body_name: str):
    for candidate in _body_name_candidates(body_name):
        try:
            scoping = mesh.scoping_by_named_selection(candidate)
            if scoping is not None and scoping.size:
                return scoping
        except Exception:
            continue
    return None


def _body_name_candidates(name: str) -> list[str]:
    candidates = [name, name.strip()]
    stripped = re.sub(r"\s+\d+$", "", name.strip())
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    compact = re.sub(r"\s+", "", name)
    if compact not in candidates:
        candidates.append(compact)
    return candidates


def per_body_to_dicts(rows: list[BodyStressRow]) -> list[dict[str, Any]]:
    return [row.model_dump() for row in rows]
