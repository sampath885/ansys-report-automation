"""Shared DPF session and unit helpers."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def open_model(rst_path: Path):
    """Open a DPF Model; returns None if DPF/ANSYS unavailable."""
    try:
        from ansys.dpf import core as dpf

        return dpf.Model(str(rst_path))
    except Exception as exc:
        logger.warning("DPF unavailable for %s: %s", rst_path, exc)
        return None


def to_mpa(value: float | None, unit_hint: str = "Pa") -> float | None:
    if value is None:
        return None
    if unit_hint in ("Pa", "N/m^2"):
        return value / 1e6
    if unit_hint in ("MPa",):
        return value
    return value / 1e6


def to_mm(value: float | None, unit_hint: str = "m") -> float | None:
    if value is None:
        return None
    if unit_hint in ("m",):
        return value * 1000.0
    if unit_hint in ("mm",):
        return value
    return value * 1000.0
