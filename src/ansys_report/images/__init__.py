"""Image path resolution and validation."""

from ansys_report.images.auto_discover import (
    load_image_match_rules,
    resolve_assets_auto_discover,
    resolve_assets_smart,
    scan_image_folder,
)
from ansys_report.images.folder_aliases import (
    build_folder_aliases_from_resolved,
    merge_folder_aliases,
    resolve_gallery_folder,
)
from ansys_report.images.mapper import assets_to_validation, build_inline_images, resolve_assets
from ansys_report.images.semantic_image_router import apply_semantic_fallback, semantic_fallback_enabled
from ansys_report.images.slot_semantics import is_semantic_scope_slot, parse_slot_semantics
from ansys_report.images.slots import collect_figure_slots, figure_slots_for_config

__all__ = [
    "apply_semantic_fallback",
    "assets_to_validation",
    "build_folder_aliases_from_resolved",
    "build_inline_images",
    "collect_figure_slots",
    "figure_slots_for_config",
    "is_semantic_scope_slot",
    "load_image_match_rules",
    "merge_folder_aliases",
    "parse_slot_semantics",
    "resolve_assets",
    "resolve_assets_auto_discover",
    "resolve_assets_smart",
    "resolve_gallery_folder",
    "scan_image_folder",
    "semantic_fallback_enabled",
]
