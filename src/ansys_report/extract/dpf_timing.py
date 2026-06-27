"""Lightweight timing helpers for DPF extraction steps."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


@contextmanager
def log_dpf_step(label: str, rst_path: Path | None = None):
    """Log wall-clock duration for a DPF operation."""
    target = rst_path.name if rst_path else "n/a"
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        logger.info("DPF %s finished in %.1fs (%s)", label, elapsed, target)
