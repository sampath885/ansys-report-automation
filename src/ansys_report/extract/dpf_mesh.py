"""Mesh statistics via DPF."""

from __future__ import annotations

import logging
from pathlib import Path

from ansys_report.extract.dpf_base import open_model
from ansys_report.models import MeshResult

logger = logging.getLogger(__name__)


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
