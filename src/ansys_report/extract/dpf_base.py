"""Shared DPF session and unit helpers."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_model_cache: dict[str, Any] = {}
_ping_ok_cache: set[str] = set()


def _default_open_timeout() -> float:
    raw = os.getenv("DPF_OPEN_TIMEOUT", "180")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 180.0


_DISABLE_TOKENS = {"0", "false", "no", "off"}


def _dpf_force_disabled() -> bool:
    """True only when ANSYS_AVAILABLE is explicitly set to a falsey value."""
    raw = os.getenv("ANSYS_AVAILABLE")
    if raw is None:
        return False
    return raw.strip().lower() in _DISABLE_TOKENS


_dpf_importable_cache: bool | None = None


def clear_dpf_cache() -> None:
    """Drop cached DPF models and ping results (for tests or between builds)."""
    _model_cache.clear()
    _ping_ok_cache.clear()


def _rst_cache_key(rst_path: Path) -> str:
    return str(rst_path.resolve())


def _skip_subprocess_ping() -> bool:
    return os.getenv("DPF_SKIP_SUBPROCESS_PING", "").strip().lower() in {"1", "true", "yes", "on"}


def _subprocess_ping_mode() -> str:
    """How often to run the isolated DPF open check before in-process loads.

    ``first`` (default): ping only until the first RST opens successfully in-process.
    ``all``: ping every unique RST (slowest, safest on corrupt files).
    ``none``: never ping (fastest; use when RST files are trusted).
    """
    raw = os.getenv("DPF_SUBPROCESS_PING", "first").strip().lower()
    if raw in {"all", "every", "always"}:
        return "all"
    if raw in {"0", "false", "no", "off", "none", "skip"}:
        return "none"
    return "first"


def _needs_subprocess_ping(cache_key: str) -> bool:
    if _skip_subprocess_ping() or _subprocess_ping_mode() == "none":
        return False
    if cache_key in _ping_ok_cache:
        return False
    if _subprocess_ping_mode() == "first" and _model_cache:
        return False
    return True


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Kill a subprocess and any children (important for DPF workers on Windows)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _run_subprocess_json(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout_s: float,
    label: str,
    rst_path: Path,
) -> dict | None:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc)
        proc.communicate()
        logger.error("%s timed out after %.0fs: %s", label, timeout_s, rst_path)
        return None

    if proc.returncode != 0:
        logger.warning(
            "%s failed for %s: %s",
            label,
            rst_path,
            (stderr or stdout or "").strip(),
        )
        return None

    try:
        return json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError, AttributeError):
        logger.warning("%s returned invalid JSON for %s", label, rst_path)
        return None


def dpf_available() -> bool:
    """Whether DPF can be used: not force-disabled and ansys.dpf.core importable.

    Auto-detects rather than requiring ANSYS_AVAILABLE=1. Set ANSYS_AVAILABLE=0
    (or false/no/off) to force-disable extraction (e.g. CI without a DPF server).
    The actual ability to open a given RST is still verified by the subprocess ping.
    """
    global _dpf_importable_cache
    if _dpf_force_disabled():
        return False
    if _dpf_importable_cache is None:
        try:
            import ansys.dpf.core  # noqa: F401

            _dpf_importable_cache = True
        except Exception:
            _dpf_importable_cache = False
    return _dpf_importable_cache


def _subprocess_ping(rst_path: Path, timeout_s: float) -> bool:
    """Verify RST opens in an isolated process before loading DPF in-process."""
    cache_key = _rst_cache_key(rst_path)
    if cache_key in _ping_ok_cache:
        return True

    cmd = [
        sys.executable,
        "-m",
        "ansys_report.extract.dpf_subprocess",
        "ping",
        str(rst_path),
    ]
    env = {**os.environ, "ANSYS_AVAILABLE": "1"}
    payload = _run_subprocess_json(
        cmd,
        env=env,
        timeout_s=timeout_s,
        label="DPF open",
        rst_path=rst_path,
    )
    if payload is None:
        return False
    if not payload.get("ok"):
        logger.warning("DPF subprocess ping rejected %s: %s", rst_path, payload.get("error"))
        return False
    _ping_ok_cache.add(cache_key)
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
    return _run_subprocess_json(
        cmd,
        env=env,
        timeout_s=timeout_s,
        label=f"DPF subprocess {command}",
        rst_path=rst_path,
    )


def open_model(rst_path: Path, *, timeout_s: float | None = None):
    """Open a DPF Model; returns None if DPF/ANSYS unavailable or open times out."""
    if not dpf_available():
        return None

    cache_key = _rst_cache_key(rst_path)
    cached = _model_cache.get(cache_key)
    if cached is not None:
        return cached

    timeout = _default_open_timeout() if timeout_s is None else timeout_s
    if timeout > 0 and _needs_subprocess_ping(cache_key) and not _subprocess_ping(rst_path, timeout):
        return None

    try:
        from ansys.dpf import core as dpf

        model = dpf.Model(str(rst_path))
    except Exception as exc:
        logger.warning("DPF unavailable for %s: %s", rst_path, exc)
        return None

    _model_cache[cache_key] = model
    _ping_ok_cache.add(cache_key)
    return model


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
