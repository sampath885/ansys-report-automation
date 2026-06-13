"""DPF bolt pretension force extraction (requires ANSYS)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

logger = logging.getLogger(__name__)

BoltExtractionMode = Literal["envelope", "first", "last", "step"]

@dataclass(frozen=True)
class _BoltSpec:
    pretension_node: int
    beam_element: int
    center_y_mm: float | None = None


def extract_bolt_loads_dpf(
    rst_path: Path,
    *,
    mode: BoltExtractionMode = "envelope",
    load_step: int = 1,
    tensile_area_mm2: float = 115.0,
    shear_area_mm2: float = 100.0,
    yield_mpa: float = 205.0,
    expected_count: int = 8,
    uniform_axial_n: float | None = None,
    sort_by_position: bool = True,
) -> list[dict[str, Any]]:
    """Return per-bolt load rows from pretension beam elements in an RST.

    Table columns are *Maximum* axial/shear forces. Default ``envelope`` takes the
    max over all result sets in the RST. Static reports often show uniform applied
    pretension as axial (pass ``uniform_axial_n`` from CAERep/Excel).
    """
    from ansys_report.extract.dpf_base import open_model

    model = open_model(rst_path)
    if model is None:
        return []

    mech_dir = rst_path.parent
    specs = _parse_bolt_specs(mech_dir / "ds.dat", model=model, limit=expected_count)
    if not specs:
        logger.warning("No bolt pretension definitions found in %s", mech_dir / "ds.dat")
        return []

    steps = _resolve_steps(model, mode, load_step)
    per_bolt: list[dict[str, list[float]]] = [
        {"axial": [], "shear": []} for _ in range(len(specs))
    ]

    for step in steps:
        step_rows = _extract_beam_forces(model, specs, step)
        for index, (axial, shear) in enumerate(step_rows):
            if axial is not None:
                per_bolt[index]["axial"].append(abs(float(axial)))
            if shear is not None:
                per_bolt[index]["shear"].append(float(shear))

    rows: list[dict[str, Any]] = []
    for bolt_no, spec in enumerate(specs, start=1):
        samples = per_bolt[bolt_no - 1]
        if not samples["axial"] and not samples["shear"]:
            continue

        measured_axial = max(samples["axial"]) if samples["axial"] else None
        shear = max(samples["shear"]) if samples["shear"] else 0.0

        if uniform_axial_n is not None:
            axial_abs = float(uniform_axial_n)
        elif measured_axial is not None:
            axial_abs = float(measured_axial)
        else:
            axial = _reaction_axial(model, spec.pretension_node, steps[0])
            if axial is None:
                continue
            axial_abs = abs(float(axial))

        normal_stress = axial_abs / tensile_area_mm2 if tensile_area_mm2 else 0.0
        shear_stress = shear / shear_area_mm2 if shear_area_mm2 else 0.0
        rows.append(
            {
                "bolt_no": bolt_no,
                "pretension_node": spec.pretension_node,
                "beam_element": spec.beam_element,
                "center_y_mm": spec.center_y_mm,
                "axial_force_n": round(axial_abs, 2),
                "shear_force_n": round(shear, 2),
                "tensile_stress_area_mm2": tensile_area_mm2,
                "shear_stress_area_mm2": shear_area_mm2,
                "normal_stress_mpa": round(normal_stress, 6),
                "shear_stress_mpa": round(shear_stress, 4),
                "yield_stress_mpa": yield_mpa,
                "conclusion": "Accepted" if normal_stress <= yield_mpa else "Review",
            }
        )

    if sort_by_position and rows:
        rows = _sort_bolt_rows(rows)

    for index, row in enumerate(rows, start=1):
        row["bolt_no"] = index

    return rows


def parse_pretension_preload_n(mech_dir: Path) -> float | None:
    """Mean applied bolt pretension (N) from CAERep Preload entries."""
    caerep = mech_dir / "CAERep.xml"
    if not caerep.exists():
        return None
    text = caerep.read_text(encoding="utf-8", errors="replace")
    preloads = [
        float(value)
        for value in re.findall(
            r'<Preload PropType="double"[^>]*>([\d.E+-]+)</Preload>',
            text,
        )
    ]
    if not preloads:
        return None
    return round(sum(preloads) / len(preloads), 2)


def _extract_beam_forces(model, specs: list[_BoltSpec], load_step: int) -> list[tuple[float | None, float | None]]:
    from ansys.dpf.core import operators as ops

    try:
        axial_fc = _beam_field(model, ops.result.beam_axial_force, load_step)
        shear_s_fc = _beam_field(model, ops.result.beam_s_shear_force, load_step)
        shear_t_fc = _beam_field(model, ops.result.beam_t_shear_force, load_step)
    except Exception as exc:
        logger.warning("Beam force extraction failed at step %s: %s", load_step, exc)
        return [(None, None) for _ in specs]

    out: list[tuple[float | None, float | None]] = []
    for spec in specs:
        axial = _element_value(axial_fc, spec.beam_element)
        shear_s = _element_value(shear_s_fc, spec.beam_element)
        shear_t = _element_value(shear_t_fc, spec.beam_element)
        shear = None
        if shear_s is not None or shear_t is not None:
            shear = float(np.sqrt((shear_s or 0.0) ** 2 + (shear_t or 0.0) ** 2))
        out.append((axial, shear))
    return out


def _resolve_steps(model, mode: BoltExtractionMode, load_step: int) -> list[int]:
    available = _available_load_steps(model)
    if not available:
        return [load_step]
    if mode == "envelope":
        return available
    if mode == "first":
        return [available[0]]
    if mode == "last":
        return [available[-1]]
    if load_step in available:
        return [load_step]
    return [available[-1]]


def _available_load_steps(model) -> list[int]:
    try:
        count = len(model.metadata.time_freq_support.time_frequencies.data)
        if count > 0:
            return list(range(1, count + 1))
    except Exception:
        pass
    return [1, 2, 3]


def _sort_bolt_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Number bolts top-to-bottom on the flange (descending Y on pretension node)."""
    if all(row.get("center_y_mm") is not None for row in rows):
        return sorted(rows, key=lambda row: row["center_y_mm"], reverse=True)
    return rows


def _beam_field(model, operator_factory, load_step: int):
    op = operator_factory()
    op.inputs.data_sources(model.metadata.data_sources)
    op.inputs.time_scoping(load_step)
    fc = op.outputs.fields_container()
    return fc[0] if fc else None


def _element_value(field, element_id: int) -> float | None:
    if field is None:
        return None
    ids = [int(i) for i in field.scoping.ids]
    try:
        idx = ids.index(element_id)
    except ValueError:
        return None
    return float(field.data[idx])


def _reaction_axial(model, node_id: int, load_step: int) -> float | None:
    try:
        fc = model.results.reaction_force(time_scoping=load_step).eval()
        if not fc:
            return None
        field = fc[0]
        ids = {int(i): j for j, i in enumerate(field.scoping.ids)}
        idx = ids.get(node_id)
        if idx is None:
            return None
        return float(field.data[idx][0])
    except Exception:
        return None


def _parse_bolt_specs(
    ds_dat: Path,
    *,
    model=None,
    limit: int = 8,
) -> list[_BoltSpec]:
    if not ds_dat.exists():
        return []
    text = ds_dat.read_text(encoding="utf-8", errors="replace")
    specs: list[_BoltSpec] = []
    node_coords: dict[int, float] | None = None
    if model is not None:
        try:
            mesh = model.metadata.meshed_region
            coords = mesh.nodes.coordinates_field.data
            id_to_idx = {int(node_id): idx for idx, node_id in enumerate(mesh.nodes.scoping.ids)}
            node_coords = {
                int(node_id): float(coords[id_to_idx[node_id]][1])
                for node_id in mesh.nodes.scoping.ids
                if int(node_id) in id_to_idx
            }
        except Exception:
            node_coords = None

    for block in re.split(r"/com,\*+\s*Create Bolt Pretension", text)[1:]:
        node_match = re.search(r"_nbolt\d+\s*=\s*(\d+)", block)
        beam_match = re.search(r"\*set,_beame1,(\d+)", block)
        if not node_match or not beam_match:
            continue
        pretension_node = int(node_match.group(1))
        center_y = node_coords.get(pretension_node) if node_coords else None
        specs.append(
            _BoltSpec(
                pretension_node=pretension_node,
                beam_element=int(beam_match.group(1)),
                center_y_mm=center_y,
            )
        )
        if len(specs) >= limit:
            break
    return specs
