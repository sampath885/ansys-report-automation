"""Build export-folder context for semantic image routing (no hardcoded project maps)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from ansys_report.images.folder_aliases import all_gallery_canonical_folders
from ansys_report.images.slot_semantics import analysis_root_from_rel_path

_LOG_OK = re.compile(
    r"^OK\s+\[([^\]]+)\]\s+->\s+(.+\.png)\s*$",
    re.IGNORECASE,
)


def build_export_context(image_root: Path) -> dict:
    """Summarize this export tree for Gemini (folders, log labels, manifest)."""
    root = image_root.resolve()
    folders = _index_export_folders(root)
    manifest = _load_manifest(root / "result_summaries" / "manifest.json")
    _merge_manifest_into_folders(folders, manifest)
    _merge_log_into_folders(folders, root / "auto_discover_log.txt")

    folder_list = sorted(folders.values(), key=lambda item: item["folder"])
    from ansys_report.images.export_inference import enrich_export_context

    context = {
        "image_root": str(root),
        "analysis_folders": folder_list,
        "manifest_entries": manifest,
        "canonical_gallery_folders": sorted(all_gallery_canonical_folders()),
    }
    return enrich_export_context(context)


def context_fingerprint(context: dict) -> str:
    """Stable hash input for semantic cache invalidation when export layout changes."""
    payload = {
        "folders": [
            {
                "folder": item.get("folder"),
                "analysis_names": item.get("analysis_names"),
                "manifest_keys": item.get("manifest_keys"),
            }
            for item in context.get("analysis_folders", [])
        ],
        "manifest": context.get("manifest_entries", []),
    }
    return json.dumps(payload, sort_keys=True)


def _index_export_folders(image_root: Path) -> dict[str, dict]:
    folders: dict[str, dict] = {}
    if not image_root.exists():
        return folders

    samples: dict[str, list[str]] = defaultdict(list)
    for path in sorted(image_root.rglob("*.png")):
        try:
            rel = path.relative_to(image_root).as_posix()
        except ValueError:
            continue
        top = analysis_root_from_rel_path(rel)
        if not top or top.startswith("."):
            continue
        bucket = samples[top]
        if len(bucket) < 8:
            bucket.append(rel)

    for folder, paths in samples.items():
        folders[folder] = {
            "folder": folder,
            "analysis_names": [],
            "manifest_keys": [],
            "workbench_folders": [],
            "sample_paths": paths,
        }
    return folders


def _load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("summaries") or []
    return [entry for entry in entries if isinstance(entry, dict)]


def _manifest_folder_key(entry: dict) -> str | None:
    file_name = str(entry.get("file") or "")
    if file_name.endswith(".json"):
        return file_name[: -len(".json")]
    return None


def _merge_manifest_into_folders(folders: dict[str, dict], manifest: list[dict]) -> None:
    for entry in manifest:
        folder_key = _manifest_folder_key(entry)
        if not folder_key:
            continue
        bucket = folders.setdefault(
            folder_key,
            {
                "folder": folder_key,
                "analysis_names": [],
                "manifest_keys": [],
                "workbench_folders": [],
                "sample_paths": [],
            },
        )
        analysis = str(entry.get("analysis_name") or "").strip()
        if analysis and analysis not in bucket["analysis_names"]:
            bucket["analysis_names"].append(analysis)
        system_key = entry.get("system_key")
        if system_key and system_key not in bucket["manifest_keys"]:
            bucket["manifest_keys"].append(str(system_key))
        wb = entry.get("workbench_folder")
        if wb and wb not in bucket["workbench_folders"]:
            bucket["workbench_folders"].append(str(wb))


def _merge_log_into_folders(folders: dict[str, dict], log_path: Path) -> None:
    if not log_path.exists():
        return
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LOG_OK.match(line.strip())
        if not match:
            continue
        label, raw_path = match.group(1), match.group(2).replace("\\", "/")
        top = analysis_root_from_rel_path(raw_path.split("exports/")[-1] if "exports/" in raw_path else raw_path)
        if not top:
            continue
        bucket = folders.setdefault(
            top,
            {
                "folder": top,
                "analysis_names": [],
                "manifest_keys": [],
                "workbench_folders": [],
                "sample_paths": [],
            },
        )
        analysis = label.split("/")[0].strip()
        if analysis and analysis not in bucket["analysis_names"]:
            bucket["analysis_names"].append(analysis)
        rel_hint = raw_path
        if len(bucket["sample_paths"]) < 8 and rel_hint not in bucket["sample_paths"]:
            bucket["sample_paths"].append(rel_hint)
