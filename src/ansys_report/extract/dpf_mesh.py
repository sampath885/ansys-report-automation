"""Mesh statistics and quality metrics via DPF."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ansys_report.extract.dpf_base import dpf_available, open_model, run_dpf_subprocess
from ansys_report.models import MeshResult

logger = logging.getLogger(__name__)

_TET_EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


def extract_mesh(rst_path: Path) -> MeshResult:
    manual: list[str] = []
    result = MeshResult()

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
    """Live mesh quality metrics; prefers subprocess when DPF is available."""
    if not dpf_available():
        return {}
    if os.getenv("DPF_MESH_QUALITY_SUBPROCESS", "1") == "1":
        payload = run_dpf_subprocess("mesh_quality", rst_path, timeout_s=timeout_s)
        if payload and payload.get("ok"):
            return payload.get("metrics") or {}
    return _compute_mesh_quality_inprocess(rst_path)


def compute_mesh_quality_metrics(rst_path: Path, *, use_subprocess: bool = False) -> dict[str, dict[str, float | None]]:
    """Compute mesh quality; subprocess entrypoint sets use_subprocess=False."""
    if use_subprocess:
        return extract_mesh_quality(rst_path)
    return _compute_mesh_quality_inprocess(rst_path)


def _compute_mesh_quality_inprocess(rst_path: Path) -> dict[str, dict[str, float | None]]:
    model = open_model(rst_path, timeout_s=0)
    if model is None:
        return {}

    try:
        import numpy as np

        mesh = model.metadata.meshed_region
        coords = mesh.nodes.coordinates_field.data
        conn = mesh.elements.connectivities_field
        n_elements = mesh.elements.n_elements

        max_aspect = 0.0
        max_skew = 0.0
        min_jacobian = 1.0
        min_quality = 1.0
        max_corner_angle = 0.0
        processed = 0

        for index in range(n_elements):
            nodes = conn.get_entity_data(index)
            if len(nodes) < 4:
                continue
            corners = coords[nodes[:4]]
            metrics = _tet_quality_metrics(corners)
            max_aspect = max(max_aspect, metrics["aspect_ratio"])
            max_skew = max(max_skew, metrics["skewness"])
            min_jacobian = min(min_jacobian, metrics["jacobian_ratio"])
            min_quality = min(min_quality, metrics["element_quality"])
            max_corner_angle = max(max_corner_angle, metrics["max_corner_angle_deg"])
            processed += 1

        if processed == 0:
            return {}

        return {
            "aspect_ratio": {"max": float(max_aspect), "source": "dpf"},
            "skewness": {"max": float(max_skew), "source": "dpf"},
            "jacobian_ratio": {"min": float(min_jacobian), "source": "dpf"},
            "element_quality": {"min": float(min_quality), "source": "dpf"},
            "max_corner_angle_deg": {"max": float(max_corner_angle), "source": "dpf"},
        }
    except Exception as exc:
        logger.warning("Mesh quality extraction failed for %s: %s", rst_path, exc)
        return {}


def _tet_quality_metrics(corners) -> dict[str, float]:
    import numpy as np

    edges = [corners[i] - corners[j] for i, j in _TET_EDGES]
    lengths = np.array([float(np.linalg.norm(edge)) for edge in edges])
    min_len = max(float(lengths.min()), 1e-12)
    max_len = float(lengths.max())
    aspect_ratio = max_len / min_len

    volume = abs(float(np.dot(edges[0], np.cross(edges[1], edges[2])))) / 6.0
    ideal = (max_len**3) / (6.0 * (2.0**0.5))
    quality = float(min(1.0, (3.0 * volume / ideal) if ideal > 0 else 0.0))
    skewness = float(max(0.0, 1.0 - quality))

    face_areas = []
    faces = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))
    for a, b, c in faces:
        area = 0.5 * float(np.linalg.norm(np.cross(corners[b] - corners[a], corners[c] - corners[a])))
        face_areas.append(area)
    sum_area = max(sum(face_areas), 1e-12)
    jacobian_ratio = float(min(1.0, (12.0 * (3.0**0.5) * volume / (sum_area * max_len)) if max_len > 0 else 0.0))

    max_angle = 0.0
    for vertex in range(4):
        others = [idx for idx in range(4) if idx != vertex]
        vectors = [corners[other] - corners[vertex] for other in others]
        for left in range(3):
            for right in range(left + 1, 3):
                v1, v2 = vectors[left], vectors[right]
                denom = float(np.linalg.norm(v1) * np.linalg.norm(v2))
                cosine = float(np.dot(v1, v2) / denom) if denom > 0 else 1.0
                angle = float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
                max_angle = max(max_angle, angle)

    return {
        "aspect_ratio": aspect_ratio,
        "skewness": skewness,
        "jacobian_ratio": jacobian_ratio,
        "element_quality": quality,
        "max_corner_angle_deg": max_angle,
    }


def merge_mesh_quality_into_result(result: MeshResult, metrics: dict[str, Any]) -> MeshResult:
    if not metrics:
        return result
    result.quality_metrics = metrics
    return result
