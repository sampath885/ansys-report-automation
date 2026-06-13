"""Shared DPF session and unit helpers."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _default_open_timeout() -> float:
    raw = os.getenv("DPF_OPEN_TIMEOUT", "180")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 180.0


def _subprocess_ping(rst_path: Path, timeout_s: float) -> bool:
    """Verify RST opens in an isolated process before loading DPF in-process."""
    cmd = [
        sys.executable,
        "-m",
        "ansys_report.extract.dpf_subprocess",
        "ping",
        str(rst_path),
    ]
    env = {**os.environ, "ANSYS_AVAILABLE": "1"}
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("DPF open timed out after %.0fs: %s", timeout_s, rst_path)
        return False

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        logger.warning("DPF subprocess ping failed for %s: %s", rst_path, err)
        return False

    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        logger.warning("DPF subprocess ping returned invalid JSON for %s", rst_path)
        return False
    if not payload.get("ok"):
        logger.warning("DPF subprocess ping rejected %s: %s", rst_path, payload.get("error"))
        return False
    return True


def run_dpf_subprocess(
    command: str,
    rst_path: Path,
    *,
    timeout_s: float | None = None,
) -> dict | None:
    """Run a DPF worker command in a subprocess; return parsed JSON or None."""
    timeout_s = timeout_s if timeout_s is not None else _default_open_timeout()
    if timeout_s <= 0:
        return None
    cmd = [
        sys.executable,
        "-m",
        "ansys_report.extract.dpf_subprocess",
        command,
        str(rst_path),
    ]
    env = {**os.environ, "ANSYS_AVAILABLE": "1"}
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("DPF subprocess %s timed out after %.0fs: %s", command, timeout_s, rst_path)
        return None

    if completed.returncode != 0:
        logger.warning(
            "DPF subprocess %s failed for %s: %s",
            command,
            rst_path,
            (completed.stderr or completed.stdout or "").strip(),
        )
        return None

    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        logger.warning("DPF subprocess %s returned invalid JSON for %s", command, rst_path)
        return None


def open_model(rst_path: Path, *, timeout_s: float | None = None):
    """Open a DPF Model; returns None if DPF/ANSYS unavailable or open times out."""
    if os.getenv("ANSYS_AVAILABLE") != "1":
        return None

    timeout = _default_open_timeout() if timeout_s is None else timeout_s
    if timeout > 0 and not _subprocess_ping(rst_path, timeout):
        return None

    try:
        from ansys.dpf import core as dpf

        return dpf.Model(str(rst_path))
    except Exception as exc:
        logger.warning("DPF unavailable for %s: %s", rst_path, exc)
        return None


def to_mpa(value: float | None, unit_hint: str = "Pa") -> float | None:
    if value is None:
        return None
    unit = (unit_hint or "Pa").lower()
    if unit in ("pa", "n/m^2", "n/m**2"):
        return value / 1e6
    if unit in ("mpa",):
        return value
    if unit in ("kpa",):
        return value / 1e3
    return value / 1e6


def to_mm(value: float | None, unit_hint: str = "m") -> float | None:
    if value is None:
        return None
    unit = (unit_hint or "m").lower()
    if unit in ("m",):
        return value * 1000.0
    if unit in ("mm",):
        return value
    return value * 1000.0


def von_mises_max_mpa(stress_field) -> float | None:
    """Max von-Mises stress in MPa from a DPF stress field (6 components)."""
    import numpy as np

    data = stress_field.data
    if data is None or len(data) == 0:
        return None
    vm = np.sqrt(
        0.5
        * (
            (data[:, 0] - data[:, 1]) ** 2
            + (data[:, 1] - data[:, 2]) ** 2
            + (data[:, 2] - data[:, 0]) ** 2
            + 6 * (data[:, 3] ** 2 + data[:, 4] ** 2 + data[:, 5] ** 2)
        )
    )
    return to_mpa(float(vm.max()), getattr(stress_field, "unit", "MPa") or "MPa")


def read_modal_frequencies_hz(model, num_modes: int = 6) -> list[float]:
    """Natural frequencies from modal result metadata (time/freq support)."""
    freqs = list(model.metadata.time_freq_support.time_frequencies.data)
    return [float(f) for f in freqs[:num_modes]]
