"""Choose the best image map for an exports folder layout."""

from __future__ import annotations

import logging
from pathlib import Path

from ansys_report.config import ImageMapConfig, ProjectConfig
from ansys_report.images.log_slot_mapper import parse_autodiscover_export_log

logger = logging.getLogger(__name__)

EP2741_MARKERS = (
    "static_structural",
    "vibration_resistance_analysis_x",
    "equivalent_static_analysis_posx",
)


def detect_export_layout(image_root: Path) -> str:
    """Return 'ep2741', 'ep2737', or 'unknown'."""
    if not image_root.exists():
        return "unknown"
    if any((image_root / marker).exists() for marker in EP2741_MARKERS):
        return "ep2741"
    if (image_root / "static").exists() and (image_root / "harmonic").exists():
        return "ep2737"
    return "unknown"


def count_map_hits(image_root: Path, image_map: ImageMapConfig | None) -> tuple[int, int]:
    if image_map is None or not image_root.exists():
        return 0, 0
    total = len(image_map.slots)
    hits = sum(1 for rel in image_map.slots.values() if (image_root / rel).exists())
    return hits, total


def resolve_image_map_for_exports(
    cfg: ProjectConfig,
    image_root: Path,
    *,
    repo_root: Path | None = None,
) -> tuple[ImageMapConfig | None, str]:
    """Pick image map + effective resolve mode for *image_root*."""
    repo = repo_root or Path(__file__).resolve().parents[3]
    layout = detect_export_layout(image_root)
    configured: ImageMapConfig | None = None

    if cfg.image_map_path and cfg.image_map_path.exists():
        from ansys_report.config import load_image_map

        configured = load_image_map(cfg.image_map_path)

    hits, total = count_map_hits(image_root, configured)
    mode = (cfg.image_resolve_mode or "hybrid").lower()

    if configured and hits == 0 and total > 0:
        logger.warning(
            "Configured image map %s has 0/%d paths under %s (layout=%s); "
            "using log map + auto-discover instead",
            cfg.image_map_path,
            total,
            image_root,
            layout,
        )
        configured = None

    if configured is not None:
        return configured, mode

    log_path = image_root / "auto_discover_log.txt"
    if log_path.exists():
        log_slots = parse_autodiscover_export_log(log_path, image_root)
        if log_slots:
            logger.info(
                "Using auto_discover_log.txt map (%d slots) for %s layout",
                len(log_slots),
                layout,
            )
            return ImageMapConfig.from_mapping(log_slots), "hybrid"

    ep2741_default = repo / "config" / "image_map.ep2741.yaml"
    if layout == "ep2741" and ep2741_default.exists():
        from ansys_report.config import load_image_map

        fallback = load_image_map(ep2741_default)
        fb_hits, fb_total = count_map_hits(image_root, fallback)
        if fb_hits > 0:
            logger.info("Using bundled EP2741 image map (%d/%d hits)", fb_hits, fb_total)
            return fallback, "hybrid"

    return None, mode if mode in {"auto", "hybrid"} else "auto"
