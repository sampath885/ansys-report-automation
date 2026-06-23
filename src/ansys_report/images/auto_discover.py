"""Match auto-discover Mechanical export folders to report figure slots."""

from __future__ import annotations

import fnmatch
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from ansys_report.config import ImageMapConfig
from ansys_report.models import MissingAssets

logger = logging.getLogger(__name__)

_LOG_LINE = re.compile(
    r"^OK\s+\[[^\]]+\]\s+->\s+(.+\.png)\s*$",
    re.IGNORECASE,
)


class ImageMatchRule(BaseModel):
    path: str | None = None
    path_glob: str | None = None
    folder_keywords: list[str] = Field(default_factory=list)
    subpath: str = ""
    file: str | None = None
    exclude_keywords: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class ImageMatchRulesConfig(BaseModel):
    version: int = 1
    rules: dict[str, ImageMatchRule] = Field(default_factory=dict)


def load_image_match_rules(path: Path) -> ImageMatchRulesConfig:
    import yaml

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    rules_raw = data.get("rules", data)
    rules: dict[str, ImageMatchRule] = {}
    if isinstance(rules_raw, dict):
        for key, value in rules_raw.items():
            if isinstance(value, dict):
                rules[str(key)] = ImageMatchRule(**value)
            elif isinstance(value, str):
                rules[str(key)] = ImageMatchRule(path=value)
    return ImageMatchRulesConfig(version=int(data.get("version", 1)), rules=rules)


def scan_image_folder(image_root: Path) -> list[str]:
    """Return POSIX relative paths for every PNG under image_root."""
    if not image_root.exists():
        return []
    paths: list[str] = []
    for path in sorted(image_root.rglob("*.png")):
        try:
            rel = path.relative_to(image_root).as_posix()
        except ValueError:
            continue
        paths.append(rel)
    return paths


def parse_auto_discover_log(log_path: Path) -> dict[str, str]:
    """Parse auto_discover_log.txt entries into basename -> relative path hints."""
    if not log_path.exists():
        return {}
    hints: dict[str, str] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LOG_LINE.match(line.strip())
        if not match:
            continue
        full = match.group(1).replace("\\", "/")
        name = Path(full).name
        hints[name] = full
    return hints


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _matches_rule(rel_path: str, rule: ImageMatchRule) -> bool:
    rel_lower = rel_path.lower()
    if rule.exclude_keywords and any(kw.lower() in rel_lower for kw in rule.exclude_keywords):
        return False

    if rule.path:
        return rel_lower == _normalize_rel(rule.path).lower()

    if rule.path_glob:
        return fnmatch.fnmatch(rel_lower, _normalize_rel(rule.path_glob).lower())

    if rule.folder_keywords:
        if not all(kw.lower() in rel_lower for kw in rule.folder_keywords):
            return False
        if rule.file:
            target = _normalize_rel(rule.file).lower()
            if rule.subpath:
                target = f"{_normalize_rel(rule.subpath).lower().rstrip('/')}/{target}"
            return rel_lower.endswith(target) or rel_lower == target
        return True

    return False


def _pick_best_match(candidates: list[str], rule: ImageMatchRule) -> str | None:
    if not candidates:
        return None
    if rule.path:
        norm = _normalize_rel(rule.path).lower()
        for candidate in candidates:
            if candidate.lower() == norm:
                return candidate
    if len(candidates) == 1:
        return candidates[0]
    # Prefer shorter paths (less nested duplicates) then lexicographic stability.
    return sorted(candidates, key=lambda p: (p.count("/"), len(p), p.lower()))[0]


def resolve_slot_with_rules(
    slot: str,
    rule: ImageMatchRule,
    image_root: Path,
    indexed_paths: list[str],
) -> Path | None:
    matches = [rel for rel in indexed_paths if _matches_rule(rel, rule)]
    chosen = _pick_best_match(matches, rule)
    if not chosen:
        return None
    path = image_root / chosen
    return path.resolve() if path.exists() else None


def resolve_assets_auto_discover(
    image_root: Path,
    rules: ImageMatchRulesConfig,
    slots: list[str] | None = None,
    check_quality: bool = True,
    quality_checker=None,
) -> MissingAssets:
    from ansys_report.images.mapper import _quality_warnings

    target_slots = slots if slots is not None else sorted(rules.rules.keys())
    indexed = scan_image_folder(image_root)
    missing: list[str] = []
    warnings: list[str] = []
    resolved: dict[str, Path] = {}

    for slot in target_slots:
        rule = rules.rules.get(slot)
        if rule is None:
            missing.append(slot)
            continue
        path = resolve_slot_with_rules(slot, rule, image_root, indexed)
        if path is None:
            missing.append(slot)
            continue
        resolved[slot] = path
        if check_quality:
            checker = quality_checker or _quality_warnings
            warnings.extend(checker(slot, path))

    return MissingAssets(missing_slots=missing, warnings=warnings, resolved=resolved)


def resolve_assets_smart(
    image_root: Path,
    *,
    slots: list[str] | None = None,
    image_map: ImageMapConfig | None = None,
    rules: ImageMatchRulesConfig | None = None,
    mode: str = "hybrid",
    check_quality: bool = True,
) -> MissingAssets:
    """Resolve figure slots using exact map, auto-discover rules, or both."""
    from ansys_report.images.mapper import resolve_assets

    mode = (mode or "hybrid").lower()
    if mode not in {"exact", "auto", "hybrid"}:
        raise ValueError(f"Unknown image_resolve_mode: {mode}")

    requested = list(slots or [])
    if not requested:
        if image_map:
            requested.extend(image_map.slots.keys())
        if rules:
            requested.extend(rules.rules.keys())
        requested = sorted(set(requested))

    resolved: dict[str, Path] = {}
    warnings: list[str] = []
    missing_after: list[str] = []

    if mode in {"exact", "hybrid"} and image_map and image_map.slots:
        exact = resolve_assets(image_root, image_map, check_quality=check_quality)
        resolved.update(exact.resolved)
        warnings.extend(exact.warnings)

    pending = [slot for slot in requested if slot not in resolved]

    if mode in {"auto", "hybrid"} and rules and rules.rules:
        auto = resolve_assets_auto_discover(
            image_root,
            rules,
            slots=pending or None,
            check_quality=check_quality,
        )
        resolved.update(auto.resolved)
        warnings.extend(auto.warnings)
        pending = [slot for slot in requested if slot not in resolved]

    missing_after = [slot for slot in requested if slot not in resolved]

    # De-duplicate warnings preserving order.
    seen: set[str] = set()
    unique_warnings: list[str] = []
    for msg in warnings:
        if msg not in seen:
            seen.add(msg)
            unique_warnings.append(msg)

    return MissingAssets(
        missing_slots=missing_after,
        warnings=unique_warnings,
        resolved=resolved,
    )
