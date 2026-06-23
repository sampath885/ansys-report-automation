"""Image path resolution and validation."""

from ansys_report.images.auto_discover import (
    load_image_match_rules,
    resolve_assets_auto_discover,
    resolve_assets_smart,
    scan_image_folder,
)
from ansys_report.images.mapper import assets_to_validation, build_inline_images, resolve_assets
from ansys_report.images.slots import collect_figure_slots, figure_slots_for_config

__all__ = [
    "assets_to_validation",
    "build_inline_images",
    "collect_figure_slots",
    "figure_slots_for_config",
    "load_image_match_rules",
    "resolve_assets",
    "resolve_assets_auto_discover",
    "resolve_assets_smart",
    "scan_image_folder",
]
