"""Gemini semantic fallback router for static / harmonic / shock figure slots."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

from ansys_report.images.export_context import build_export_context
from ansys_report.images.export_inference import (
    build_folder_aliases_from_export_context,
    infer_semantic_mappings_from_context,
)
from ansys_report.images.folder_aliases import (
    build_folder_aliases_from_resolved,
    filter_semantic_candidate_paths,
    merge_folder_aliases,
)
from ansys_report.images.semantic_validation import validate_semantic_batch
from ansys_report.images.auto_discover import _path_key
from ansys_report.images.slot_semantics import is_semantic_scope_slot, parse_slot_semantics

logger = logging.getLogger(__name__)

_CACHE_VERSION = 4
_DEFAULT_MODEL = "gemini-2.5-flash"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class SemanticRouter(Protocol):
    def __call__(
        self,
        slots: list[str],
        candidate_paths: list[str],
        *,
        export_context: dict,
        already_resolved: dict[str, str],
    ) -> dict[str, str | None]: ...


def semantic_fallback_enabled(flag: str = "auto") -> bool:
    """Return whether semantic fallback should run (auto = when GEMINI_API_KEY is set)."""
    mode = (flag or "auto").lower()
    if mode in {"off", "false", "0", "no"}:
        return False
    if mode in {"on", "true", "1", "yes"}:
        return bool(os.getenv("GEMINI_API_KEY"))
    return bool(os.getenv("GEMINI_API_KEY"))


def apply_semantic_fallback(
    image_root: Path,
    pending_slots: list[str],
    indexed_paths: list[str],
    used_paths: set[str],
    *,
    enabled: bool = True,
    gemini_enabled: bool | None = None,
    router: SemanticRouter | None = None,
    cache_path: Path | None = None,
    path_owners: dict[str, str] | None = None,
    already_resolved_paths: dict[str, str] | None = None,
) -> tuple[dict[str, Path], set[str], dict[str, str], list[str]]:
    """
    Resolve unresolved semantic-scope slots via Gemini (with validation + cache).

    Returns:
        resolved_paths, semantic_slot_names, folder_aliases_from_ai, warnings
    """
    warnings: list[str] = []
    semantic_slots = [slot for slot in pending_slots if is_semantic_scope_slot(slot)]
    use_gemini = semantic_fallback_enabled("on") if gemini_enabled is None else bool(gemini_enabled)
    if not enabled or not semantic_slots:
        return {}, set(), {}, warnings

    owners = dict(path_owners or {})
    resolved_for_prompt = dict(already_resolved_paths or {})
    rel_used = _relative_used_paths(used_paths, image_root)

    unused = [
        rel
        for rel in indexed_paths
        if _path_key(rel, image_root) not in used_paths
    ]
    candidates = filter_semantic_candidate_paths(unused)
    if not candidates:
        warnings.append("Semantic image fallback skipped: no candidate PNG paths")
        return {}, set(), {}, warnings

    export_context = build_export_context(image_root)
    manifest_aliases = build_folder_aliases_from_export_context(export_context)
    manifest_map = infer_semantic_mappings_from_context(
        export_context,
        semantic_slots,
        candidates,
    )
    if manifest_map:
        warnings.append(
            f"Manifest inference proposed {len(manifest_map)} slot mapping(s)"
        )

    cache_file = cache_path or (image_root / ".semantic_image_cache.json")
    cache_key = _cache_key(semantic_slots, candidates, export_context, resolved_for_prompt)
    cached = _load_cache(cache_file, cache_key)

    ai_slots = [slot for slot in semantic_slots if slot not in manifest_map]
    raw_map: dict[str, str | None] = dict(manifest_map)
    folder_roles: dict[str, str] = {}
    folder_aliases: dict[str, str] = {}

    if cached is not None:
        cached_map, folder_roles, folder_aliases = cached
        for slot, path in cached_map.items():
            if slot not in raw_map:
                raw_map[slot] = path
        warnings.append(
            f"Semantic image fallback loaded from cache ({len(cached_map)} slot hints)"
        )
    elif ai_slots and (
        router is not None or (use_gemini and os.getenv("GEMINI_API_KEY"))
    ):
        call = router or _call_gemini_router
        try:
            ai_map = call(
                ai_slots,
                candidates,
                export_context=export_context,
                already_resolved={**resolved_for_prompt, **manifest_map},
            )
        except Exception as exc:
            if not manifest_map:
                warnings.append(f"Semantic image fallback failed: {exc}")
                return {}, set(), manifest_aliases, warnings
            warnings.append(f"Gemini fallback failed (using manifest inference): {exc}")
            ai_map = {}
        folder_roles = _folder_roles_from_response(ai_map)
        ai_aliases = _folder_aliases_from_response(ai_map)
        for slot, path in ai_map.items():
            if slot not in raw_map:
                raw_map[slot] = path
        folder_aliases = ai_aliases
        _save_cache(cache_file, cache_key, raw_map, folder_roles, folder_aliases)
        warnings.append(f"Semantic image fallback invoked for {len(ai_slots)} slots")
    elif ai_slots and not use_gemini and router is None:
        warnings.append("Gemini semantic fallback skipped (manifest inference only)")
    elif ai_slots and router is None and not os.getenv("GEMINI_API_KEY"):
        warnings.append("Gemini semantic fallback skipped: GEMINI_API_KEY not set")

    str_assignments = {
        slot: str(path)
        for slot, path in raw_map.items()
        if path is not None and str(path).strip().lower() not in {"null", "none", ""}
    }
    accepted, rejections = validate_semantic_batch(
        str_assignments,
        used_paths=rel_used,
        path_owners=owners,
        folder_roles=folder_roles,
    )
    warnings.extend(f"Semantic mapping rejected: {msg}" for msg in rejections)

    resolved: dict[str, Path] = {}
    semantic_names: set[str] = set()
    for slot, rel in accepted.items():
        path = (image_root / rel).resolve()
        if not path.is_file():
            warnings.append(f"Semantic mapping skipped missing file: {slot} -> {rel}")
            continue
        resolved[slot] = path
        semantic_names.add(slot)

    if resolved:
        warnings.append(
            "Semantic fallback resolved "
            + ", ".join(sorted(resolved.keys())[:8])
            + (f" (+{len(resolved) - 8} more)" if len(resolved) > 8 else "")
        )

    folder_aliases = merge_folder_aliases(
        folder_aliases,
        build_folder_aliases_from_resolved(resolved, image_root),
        manifest_aliases,
    )

    return resolved, semantic_names, folder_aliases, warnings


def _build_prompt(
    slots: list[str],
    candidate_paths: list[str],
    export_context: dict,
    already_resolved: dict[str, str],
) -> str:
    slot_lines: list[str] = []
    for slot in slots:
        sem = parse_slot_semantics(slot)
        desc = sem.description if sem else slot
        slot_lines.append(f"- {slot}: {desc}")

    paths_block = "\n".join(f"- {path}" for path in candidate_paths)
    slot_block = "\n".join(slot_lines)
    context_json = json.dumps(export_context, indent=2)
    resolved_block = (
        json.dumps(already_resolved, indent=2)
        if already_resolved
        else "(none yet — first pass)"
    )

    return f"""You route ANSYS Mechanical export PNG files to fixed report figure slots.

You are NOT matching folder names literally. Each project uses different Workbench folder names.
Use the EXPORT CONTEXT (manifest, auto_discover log, folder scan) to infer what each folder contains.

EXPORT CONTEXT (read carefully — this is the source of truth for this project):
{context_json}

ALREADY RESOLVED SLOTS (paths already taken by rule-based mapping — do not reassign):
{resolved_block}

SLOTS TO FILL (use exact slot names as JSON keys):
{slot_block}

AVAILABLE PNG PATHS (relative paths — use exactly as listed):
{paths_block}

PHYSICS GUIDANCE (read classification on each folder in EXPORT CONTEXT):
- harmonic_* slots → folders classified as harmonic_vibration (analysis_name like "Harmonic Response_X")
- shock_plus_* slots → SAME harmonic_vibration export folders as harmonic_* (Harmonic Response is shock + direction)
- shock_minus_* slots → folders classified as shock_transient (analysis_name like "Transient_Horizontal -X-")
- static_* slots → static_structural folders
- NEVER assign transient folders to harmonic_* slots
- NEVER assign harmonic_response folders to shock_minus_* slots
- Do NOT assign modal, mesh, or geometry folders to any slot above

RULES:
1. Assign at most ONE path per slot. Each path may be used at most ONCE.
2. Match analysis type, axis (X/Y/Z), sign (+/- for shock), and result kind (deformation, stress, flange, acceleration).
3. Use null when no suitable path exists.
4. Do NOT invent paths. Only pick from AVAILABLE or null.
5. Prefer folder classification in EXPORT CONTEXT over guessing from folder spelling.

Return JSON ONLY:
{{
  "mappings": {{
    "slot_name": "relative/path.png",
    "other_slot": null
  }},
  "folder_roles": {{
    "actual_top_level_folder_name": "brief role, e.g. harmonic vibration +X, shock +X, static structural, modal (do not use for slots)"
  }},
  "folder_aliases": {{
    "vibration_resistance_analysis_x": "actual_folder_or_null",
    "equivalent_static_analysis_posx": null
  }}
}}

folder_roles: describe each top-level export folder's physics role so validation can reject wrong assignments.
folder_aliases: map canonical EP2741-style gallery folder names to actual export folder names when inferable.
"""


def _call_gemini_router(
    slots: list[str],
    candidate_paths: list[str],
    *,
    export_context: dict,
    already_resolved: dict[str, str],
) -> dict[str, str | None]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    model = os.getenv("GEMINI_MODEL", _DEFAULT_MODEL)
    prompt = _build_prompt(slots, candidate_paths, export_context, already_resolved)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    url = f"{_GEMINI_URL.format(model=model)}?key={api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail[:500]}") from exc

    text = _extract_text(payload)
    if not text:
        raise RuntimeError("Gemini returned empty response")

    parsed = json.loads(text)
    mappings = parsed.get("mappings") or parsed
    if not isinstance(mappings, dict):
        raise RuntimeError("Gemini response missing mappings object")

    out: dict[str, str | None] = {}
    for slot in slots:
        value = mappings.get(slot)
        if value is None or str(value).lower() in {"null", "none", ""}:
            out[slot] = None
        else:
            out[slot] = str(value).replace("\\", "/")

    folder_roles = parsed.get("folder_roles")
    if isinstance(folder_roles, dict):
        out["__folder_roles__"] = json.dumps(
            {str(k): str(v) for k, v in folder_roles.items()}
        )

    folder_aliases = parsed.get("folder_aliases")
    if isinstance(folder_aliases, dict):
        out["__folder_aliases__"] = json.dumps(
            {
                str(k): str(v)
                for k, v in folder_aliases.items()
                if v is not None and str(v).lower() not in {"null", "none", ""}
            }
        )
    return out


def _relative_used_paths(used_paths: set[str], image_root: Path) -> set[str]:
    root = image_root.resolve()
    rel_used: set[str] = set()
    for key in used_paths:
        candidate = Path(key)
        if candidate.is_absolute():
            try:
                rel_used.add(candidate.relative_to(root).as_posix().lower())
            except ValueError:
                rel_used.add(key.lower())
        else:
            rel_used.add(key.replace("\\", "/").lower())
    return rel_used


def _extract_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts") or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "".join(texts).strip()


def _folder_roles_from_response(raw_map: dict[str, str | None]) -> dict[str, str]:
    blob = raw_map.pop("__folder_roles__", None)
    if not blob:
        return {}
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _folder_aliases_from_response(raw_map: dict[str, str | None]) -> dict[str, str]:
    blob = raw_map.pop("__folder_aliases__", None)
    if not blob:
        return {}
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).replace("\\", "/") for k, v in data.items()}


def _cache_key(
    slots: list[str],
    paths: list[str],
    export_context: dict,
    already_resolved: dict[str, str],
) -> str:
    payload = json.dumps(
        {
            "version": _CACHE_VERSION,
            "slots": sorted(slots),
            "paths": sorted(paths),
            "context_folders": sorted(
                item.get("folder", "")
                for item in (export_context.get("analysis_folders") or [])
            ),
            "already_resolved": dict(sorted(already_resolved.items())),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache(
    path: Path,
    key: str,
) -> tuple[dict[str, str | None], dict[str, str], dict[str, str]] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("version") != _CACHE_VERSION or data.get("key") != key:
        return None
    mappings = data.get("mappings") or {}
    folder_roles = data.get("folder_roles") or {}
    aliases = data.get("folder_aliases") or {}
    return dict(mappings), dict(folder_roles), dict(aliases)


def _save_cache(
    path: Path,
    key: str,
    mappings: dict[str, str | None],
    folder_roles: dict[str, str],
    folder_aliases: dict[str, str],
) -> None:
    clean = {k: v for k, v in mappings.items() if not k.startswith("__")}
    payload = {
        "version": _CACHE_VERSION,
        "key": key,
        "mappings": clean,
        "folder_roles": folder_roles,
        "folder_aliases": folder_aliases,
    }
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write semantic cache: %s", exc)
