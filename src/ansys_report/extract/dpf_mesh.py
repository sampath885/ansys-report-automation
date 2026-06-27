"""Mesh statistics and quality metrics via DPF."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from ansys_report.extract.dpf_base import dpf_available, open_model, run_dpf_subprocess
from ansys_report.extract.dpf_timing import log_dpf_step
from ansys_report.models import MeshResult

logger = logging.getLogger(__name__)

_TET_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
_TET_FACES = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))


def extract_mesh(rst_path: Path) -> MeshResult:
    manual: list[str] = []
    result = MeshResult()

    with log_dpf_step("mesh_stats", rst_path):
        model = open_model(rst_path)
        if model is None:
            return MeshResult(manual_fields=["node_count", "element_count"])

        try:
            mesh = model.metadata.meshed_region
            result.node_count = mesh.nodes.n_nodes
            result.element_count = mesh.elements.n_elements
        except Exception as exc:
            logger.warning("Mesh extraction failed: %s", exc)
            manual.extend(["node_count", "element_count"])

    result.manual_fields = manual
    return result


def extract_mesh_quality(rst_path: Path, *, timeout_s: float | None = None) -> dict[str, dict[str, float | None]]:
    """Live mesh quality metrics; in-process by default (reuses cached DPF model)."""
    if not dpf_available():
        return {}
    if os.getenv("DPF_SKIP_MESH_QUALITY", "").strip().lower() in ("1", "true", "yes"):
        logger.info("Skipping mesh quality (DPF_SKIP_MESH_QUALITY is set)")
        return {}

    use_subprocess = os.getenv("DPF_MESH_QUALITY_SUBPROCESS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if use_subprocess:
        payload = run_dpf_subprocess("mesh_quality", rst_path, timeout_s=timeout_s)
        if payload and payload.get("ok"):
            return payload.get("metrics") or {}
        if payload is None:
            logger.warning("Mesh quality subprocess failed; skipping in-process fallback")
            return {}

    with log_dpf_step("mesh_quality", rst_path):
        return _compute_mesh_quality_inprocess(rst_path)


def compute_mesh_quality_metrics(rst_path: Path, *, use_subprocess: bool = False) -> dict[str, dict[str, float | None]]:
    """Compute mesh quality; subprocess entrypoint sets use_subprocess=False."""
    if use_subprocess:
        return extract_mesh_quality(rst_path)
    return _compute_mesh_quality_inprocess(rst_path)


def _gather_tet_corners(coords: np.ndarray, conn, n_elements: int) -> np.ndarray | None:
    """Stack all 4-node tet corner coordinates into shape (N, 4, 3)."""
    blocks: list[np.ndarray] = []
    for index in range(n_elements):
        nodes = conn.get_entity_data(index)
        if len(nodes) < 4:
            continue
        blocks.append(coords[nodes[:4]])
    if not blocks:
        return None
    return np.stack(blocks, axis=0)


def _tet_quality_metrics_batch(corners: np.ndarray) -> dict[str, np.ndarray]:
    """Vectorized tet quality metrics; corners shape (N, 4, 3)."""
    p0, p1, p2, p3 = corners[:, 0], corners[:, 1], corners[:, 2], corners[:, 3]
    edge_vecs = np.stack(
        (p1 - p0, p2 - p0, p3 - p0, p2 - p1, p3 - p1, p3 - p2),
        axis=1,
    )
    lengths = np.linalg.norm(edge_vecs, axis=2)
    min_len = np.maximum(lengths.min(axis=1), 1e-12)
    max_len = lengths.max(axis=1)
    aspect_ratio = max_len / min_len

    cross = np.cross(edge_vecs[:, 1], edge_vecs[:, 2])
    volume = np.abs(np.einsum("ij,ij->i", edge_vecs[:, 0], cross)) / 6.0
    ideal = (max_len**3) / (6.0 * (2.0**0.5))
    quality = np.minimum(1.0, np.where(ideal > 0, 3.0 * volume / ideal, 0.0))
    skewness = np.maximum(0.0, 1.0 - quality)

    face_areas = []
    for a, b, c in _TET_FACES:
        va = corners[:, b] - corners[:, a]
        vb = corners[:, c] - corners[:, a]
        face_areas.append(0.5 * np.linalg.norm(np.cross(va, vb), axis=1))
    sum_area = np.maximum(np.sum(face_areas, axis=0), 1e-12)
    jacobian_ratio = np.minimum(
        1.0,
        np.where(max_len > 0, 12.0 * (3.0**0.5) * volume / (sum_area * max_len), 0.0),
    )

    max_angle = np.zeros(len(corners))
    for vertex in range(4):
        others = [idx for idx in range(4) if idx != vertex]
        vectors = np.stack([corners[:, other] - corners[:, vertex] for other in others], axis=1)
        for left in range(3):
            for right in range(left + 1, 3):
                v1, v2 = vectors[:, left], vectors[:, right]
                denom = np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1)
                cosine = np.einsum("ij,ij->i", v1, v2) / np.maximum(denom, 1e-12)
                angle = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
                max_angle = np.maximum(max_angle, angle)

    return {
        "aspect_ratio": aspect_ratio,
        "skewness": skewness,
        "jacobian_ratio": jacobian_ratio,
        "element_quality": quality,
        "max_corner_angle_deg": max_angle,
    }


def _compute_mesh_quality_inprocess(rst_path: Path) -> dict[str, dict[str, float | None]]:
    model = open_model(rst_path, timeout_s=0)
    if model is None:
        return {}

    try:
        mesh = model.metadata.meshed_region
        coords = mesh.nodes.coordinates_field.data
        conn = mesh.elements.connectivities_field
        n_elements = mesh.elements.n_elements

        corners = _gather_tet_corners(coords, conn, n_elements)
        if corners is None:
            return {}

        metrics = _tet_quality_metrics_batch(corners)
        return {
            "aspect_ratio": {"max": float(metrics["aspect_ratio"].max()), "source": "dpf"},
            "skewness": {"max": float(metrics["skewness"].max()), "source": "dpf"},
            "jacobian_ratio": {"min": float(metrics["jacobian_ratio"].min()), "source": "dpf"},
            "element_quality": {"min": float(metrics["element_quality"].min()), "source": "dpf"},
            "max_corner_angle_deg": {"max": float(metrics["max_corner_angle_deg"].max()), "source": "dpf"},
        }
    except Exception as exc:
        logger.warning("Mesh quality extraction failed for %s: %s", rst_path, exc)
        return {}


def _tet_quality_metrics(corners) -> dict[str, float]:
    """Scalar fallback for single-element quality (tests / subprocess parity)."""
    batch = _tet_quality_metrics_batch(np.asarray(corners)[np.newaxis, ...])
    return {key: float(arr[0]) for key, arr in batch.items()}


def merge_mesh_quality_into_result(result: MeshResult, metrics: dict[str, Any]) -> MeshResult:
    if not metrics:
        return result
    result.quality_metrics = metrics
    return result
