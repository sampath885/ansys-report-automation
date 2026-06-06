"""Optional Mechanical image export via ansys-mechanical-core."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def export_views_if_available(output_dir: Path) -> bool:
    """Connect to running Mechanical and export configured views. Returns True on success."""
    try:
        from ansys.mechanical.core import launch_mechanical

        app = launch_mechanical()
        if app is None:
            logger.info("Mechanical not running; skip auto image export.")
            return False
        logger.info("Mechanical connected; run scripts/mechanical_export_views.py manually.")
        return False
    except ImportError:
        logger.debug("ansys-mechanical-core not installed.")
        return False
    except Exception as exc:
        logger.warning("Mechanical export unavailable: %s", exc)
        return False
