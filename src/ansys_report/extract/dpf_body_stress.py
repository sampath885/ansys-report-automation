"""Per-body von-Mises stress extraction via DPF."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from ansys_report.extract.dpf_base import open_model, to_mpa, von_mises_max_mpa
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
            return _extract_per_body(model, bodies, load_step=load_step)
        except Exception as exc:
            logger.warning("Per-body stress extraction failed for %s: %s", rst_path.name, exc)
            return []


def _extract_per_body(model, bodies: list[BodyMetadata], *, load_step: int | None) -> list[BodyStressRow]:
    from ansys.dpf import core as dpf

    mesh = model.metadata.meshed_region
    time_scoping = load_step if load_step is not None else None

    stress_fc = (
        model.results.stress(time_scoping=time_scoping, location=dpf.locations.elemental).eval()
        if time_scoping
        else model.results.stress(location=dpf.locations.elemental).eval()
    )
    if not stress_fc:
        stress_fc = (
            model.results.stress(time_scoping=time_scoping).eval()
            if time_scoping
            else model.results.stress().eval()
        )
    if not stress_fc:
        return []

    stress_field = stress_fc[0]
    vm_values = _von_mises_array(stress_field)
    if vm_values is None or len(vm_values) == 0:
        return []

    element_ids = np.asarray(stress_field.scoping.ids, dtype=np.int64)
    mat_ids = _element_material_ids(mesh, element_ids)
    mat_name_by_id = _material_names_by_id(model)

    rows: list[BodyStressRow] = []
    for body in bodies:
        max_stress = _stress_for_body(
            mesh,
            body,
            vm_values=vm_values,
            element_ids=element_ids,
            mat_ids=mat_ids,
            mat_name_by_id=mat_name_by_id,
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


def _stress_for_body(
    mesh,
    body: BodyMetadata,
    *,
    vm_values: np.ndarray,
    element_ids: np.ndarray,
    mat_ids: np.ndarray | None,
    mat_name_by_id: dict[int, str],
) -> float | None:
    scoped = _named_selection_scoping(mesh, body.name)
    if scoped is not None and scoped.size:
        return _max_vm_for_element_ids(vm_values, element_ids, set(scoped.ids))

    if mat_ids is not None and body.material:
        target_ids = _material_ids_for_name(body.material, mat_name_by_id)
        if target_ids:
            return _max_vm_for_material_ids(vm_values, element_ids, mat_ids, target_ids)

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
        materials = model.metadata.materials
        for idx, mat in enumerate(materials, start=1):
            label = getattr(mat, "name", None) or getattr(mat, "caption", None) or str(mat)
            names[idx] = str(label)
    except Exception:
        pass
    return names


def _material_ids_for_name(material_name: str, mat_name_by_id: dict[int, str]) -> set[int]:
    target = _normalize_material(material_name)
    if not target:
        return set()
    matched: set[int] = set()
    for mat_id, name in mat_name_by_id.items():
        if _materials_match(target, _normalize_material(name)):
            matched.add(mat_id)
    return matched


def _normalize_material(name: str | None) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", "", name.lower())
    return cleaned


def _materials_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return left in right or right in left


def _named_selection_scoping(mesh, body_name: str):
    for candidate in _body_name_candidates(body_name):
        try:
            scoping = mesh.scoping_by_named_selection(candidate)
            if scoping is not None and scoping.size:
                return scoping
        except Exception:
            continue

    try:
        available = list(mesh.available_named_selections)
    except Exception:
        available = []

    body_lower = body_name.lower()
    for ns in available:
        ns_lower = ns.lower()
        if body_lower in ns_lower or ns_lower in body_lower:
            try:
                scoping = mesh.scoping_by_named_selection(ns)
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
