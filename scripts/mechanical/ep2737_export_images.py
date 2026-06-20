# -*- coding: utf-8 -*-
"""
EP2737 - batch export report figures from ANSYS Mechanical.

RUN INSIDE MECHANICAL (not Workbench, not this repo's terminal):
  Automation tab -> Scripting -> Open this file -> Run (green play).
  main() runs automatically (Mechanical does not set __name__ == "__main__").
  If needed, type main() in the Shell panel.

AUTO-DISCOVER MODE (default, AUTO_DISCOVER = True)
---------------------------------------------------
The script walks the ENTIRE solved Mechanical tree and exports a PNG for
EVERY result node it finds - deformation, stress, strain, frequency response
charts, phase angle charts, contact results, safety factors, probes, etc.
No manifest is required.  Works for ANY project / analysis type.

Output structure:
  exports/
    common/
      geometry_isometric.png
      mesh_isometric.png
      contacts_isometric.png
      coordinate_systems_isometric.png
    <sanitised_analysis_name>/     e.g. static_structural/
      total_deformation.png
      equivalent_stress_von-mises_.png
      ...
    <next_analysis>/
      ...
    auto_discover_log.txt

MANIFEST MODE (AUTO_DISCOVER = False)
--------------------------------------
Uses config/ep2737_mechanical_export.json to drive exports with explicit
slots, keywords and scope (assembly / flange).  Falls back to this mode
only when AUTO_DISCOVER is set False at the top of this file.

Requires: solved model with Solution results visible in the tree.
IronPython 2.7 or CPython 3 (Ansys 2025 R2) - both supported.
"""

from __future__ import print_function

import json
import os
import re
import time


def _safe_str(text):
    """Strip non-ASCII chars for Mechanical IronPython shell and log files."""
    if text is None:
        return ""
    try:
        text = str(text)
    except Exception:
        return ""
    try:
        return text.encode("ascii", "replace").decode("ascii")
    except Exception:
        return text


try:
    import builtins as _builtins
except ImportError:
    import __builtin__ as _builtins  # type: ignore[no-redef]  # IronPython 2.7


def print(*args, **kwargs):  # noqa: A001 — Mechanical needs ASCII-safe output
    if args:
        args = tuple(_safe_str(a) for a in args)
    if kwargs.get("sep") is not None:
        kwargs["sep"] = _safe_str(kwargs["sep"])
    if kwargs.get("end") is not None:
        kwargs["end"] = _safe_str(kwargs["end"])
    _builtins.print(*args, **kwargs)


# =============================================================================
# EDIT THESE TWO PATHS IF YOUR MACHINE USES DIFFERENT LOCATIONS
# =============================================================================
OUTPUT_ROOT = r"C:\Users\krant\Desktop\ansys\ansys-report-automation\ouputs"
MANIFEST_PATH = r"C:\Users\krant\Desktop\ansys\ansys-report-automation\config\ep2737_mechanical_export.json"

# Set to "SYS", "SYS-1", ... "SYS-10" to force one system only (manifest mode)
SYSTEM_OVERRIDE = None

# When multiple analyses live in one Mechanical session, export ALL of them.
EXPORT_ALL_IF_COMBINED = True

# ---------------------------------------------------------------------------
# AUTO-DISCOVER SETTINGS
# ---------------------------------------------------------------------------
# True  → walk the ENTIRE solved tree; export every result found.
#         Works for any project.  Manifest is optional (used for image size).
# False → use the JSON manifest exclusively (original behaviour).
AUTO_DISCOVER = True

# Also capture Geometry, Mesh, Connections, Coordinate Systems as common views.
AUTO_DISCOVER_SETUP_VIEWS = True

# Node names (lower-case prefix match) to skip COMPLETELY during auto-discover
# (neither export them nor walk their children).
_AUTO_SKIP_PREFIXES = (
    "solution information",
    "analysis settings",
    "convergence",
    "newton-raphson",
    "named selections",
    "named selection manager",
)

# Node names to skip exporting but STILL recurse into (transparent containers).
_AUTO_CONTAINER_PREFIXES = (
    "contact tool",
    "stress tool",
    "fatigue tool",
    "beam tool",
)

# Hard safety cap: stop after this many PNGs regardless of tree size.
# Set to 0 to disable the cap entirely.
MAX_EXPORTS = 500
# =============================================================================

SYSTEM_ORDER = ["SYS"] + ["SYS-%d" % i for i in range(1, 11)]

FLANGE_NAME_HINTS = ("flange", "pipe flange", "welded", "cut-extrude")
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080


class ExportError(Exception):
    """Raised instead of sys.exit so Mechanical Shell does not show SystemExitException."""


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main():
    try:
        _main_impl()
    except ExportError:
        return 1
    return 0


def _main_impl():
    _require_mechanical()

    model = ExtAPI.DataModel.Project.Model  # noqa: F821

    if AUTO_DISCOVER:
        try:
            proj = ExtAPI.DataModel.Project.ProjectDirectory  # noqa: F821
        except Exception:
            proj = "?"
        print("EP2737 Auto-Discover Export")
        print("Project : %s" % proj)
        print("")

        # Try to pick up image-size override from manifest (optional).
        manifest = _try_load_manifest()
        if manifest:
            if manifest.get("image_width"):
                global IMAGE_WIDTH, IMAGE_HEIGHT
                IMAGE_WIDTH = int(manifest["image_width"])
                IMAGE_HEIGHT = int(manifest["image_height"])

        output_root = os.path.normpath(OUTPUT_ROOT)
        if manifest and manifest.get("output_root"):
            output_root = os.path.normpath(manifest["output_root"])

        _auto_discover_and_export(model, output_root)
        return

    # ---------- Original manifest-driven flow ----------
    manifest = _load_manifest()
    if manifest.get("image_width"):
        global IMAGE_WIDTH, IMAGE_HEIGHT
        IMAGE_WIDTH = int(manifest["image_width"])
        IMAGE_HEIGHT = int(manifest["image_height"])

    output_root = manifest.get("output_root") or OUTPUT_ROOT
    output_root = os.path.normpath(output_root)

    mapped = _map_analyses_to_systems(model)
    _print_detection_debug(model, mapped)

    if SYSTEM_OVERRIDE:
        root = _analysis_root_for_key(mapped, SYSTEM_OVERRIDE)
        _export_system(model, manifest, output_root, SYSTEM_OVERRIDE, root)
        return

    single = _detect_system_key(model)
    if single:
        root = _analysis_root_for_key(mapped, single)
        _export_system(model, manifest, output_root, single, root)
        return

    if EXPORT_ALL_IF_COMBINED and len(mapped) >= 2:
        print("Combined Mechanical session - exporting ALL %d analyses." % len(mapped))
        print("")
        total_ok = 0
        for system_key, analysis_name, analysis_root in mapped:
            print("-" * 60)
            print("Analysis: %s  ->  %s" % (analysis_name, system_key))
            ok, _, _ = _export_system(
                model, manifest, output_root, system_key, analysis_root, quiet_summary=False
            )
            total_ok += ok
        print("")
        print("=" * 60)
        print("All analyses done. Total PNGs exported: %d" % total_ok)
        print("Output folder: %s" % output_root)
        print("=" * 60)
        return

    if len(mapped) == 1:
        system_key, analysis_name, analysis_root = mapped[0]
        print("Single analysis session: %s -> %s" % (analysis_name, system_key))
        _export_system(model, manifest, output_root, system_key, analysis_root)
        return

    analyses = _list_analysis_names(model)
    hint = "\n".join("  - %s" % n for n in analyses) if analyses else "  (no analyses found)"
    _fail(
        "Could not map any analysis to a Workbench system key.\n"
        "Analyses in this Mechanical session:\n%s\n\n"
        "Set SYSTEM_OVERRIDE = 'SYS-3' (etc.) at the top of this script."
        % hint
    )


# ---------------------------------------------------------------------------
# AUTO-DISCOVER ENGINE
# ---------------------------------------------------------------------------


def _sanitize_filename(name):
    """Convert an arbitrary tree node name into a safe filename component."""
    s = _safe_str(name).strip().lower()
    # Keep alphanumerics, hyphens, underscores, dots; replace the rest with _
    s = re.sub(r"[^\w.\-]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] or "unnamed"


def _unique_path(path):
    """Append _2, _3 … to the stem if the file already exists."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    counter = 2
    while True:
        candidate = "%s_%d%s" % (base, counter, ext)
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _auto_discover_and_export(model, output_root):
    """Walk the full Mechanical tree and export a PNG for every result found."""
    log_lines = [
        "EP2737 Auto-Discover Export",
        "Time   : %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "Output : %s" % output_root,
        "-" * 60,
    ]
    ok = 0
    total_nodes = 0
    interrupted = False

    def _flush_log(note=""):
        log_lines.append("-" * 60)
        msg = "Total result nodes: %d   PNGs exported: %d" % (total_nodes, ok)
        if note:
            msg += "  [%s]" % note
        log_lines.append(msg)
        log_path = os.path.join(output_root, "auto_discover_log.txt")
        _write_log(log_path, log_lines)
        return log_path

    try:
        # 1. Common setup views
        if AUTO_DISCOVER_SETUP_VIEWS:
            n_ok, n_nodes, lines = _export_setup_views(model, output_root)
            ok += n_ok
            total_nodes += n_nodes
            log_lines.extend(lines)

        # 2. Per-analysis results
        analyses = _get_all_analyses(model)
        if not analyses:
            print("WARNING: No analyses found in the Mechanical tree.")
            log_lines.append("WARNING: No analyses found.")
        else:
            print("Found %d analysis/analyses." % len(analyses))
            if MAX_EXPORTS > 0:
                print("Safety cap: MAX_EXPORTS = %d" % MAX_EXPORTS)
            print("")

        for analysis in analyses:
            if MAX_EXPORTS > 0 and ok >= MAX_EXPORTS:
                print("")
                print("STOPPED: reached MAX_EXPORTS limit (%d)." % MAX_EXPORTS)
                print("Raise MAX_EXPORTS at the top of the script to export more.")
                log_lines.append("STOPPED: MAX_EXPORTS cap (%d) reached." % MAX_EXPORTS)
                break

            a_name = _node_name(analysis)
            a_folder = _sanitize_filename(a_name)
            if not a_folder:
                a_folder = "analysis"

            sol_node = _find_solution_node(analysis)
            if sol_node is None:
                msg = "No Solution node found under '%s' - skipped." % a_name
                print("  SKIP " + msg)
                log_lines.append("SKIP [%s] %s" % (a_name, msg))
                continue

            result_nodes = list(_collect_result_nodes_under(sol_node))

            print("-" * 60)
            print("Analysis : %s" % a_name)
            print("Folder   : %s" % a_folder)
            print("Results  : %d node(s)" % len(result_nodes))
            print("")
            total_nodes += len(result_nodes)

            if not result_nodes:
                log_lines.append("SKIP [%s] 0 result nodes found" % a_name)
                continue

            for node in result_nodes:
                # --- Keyboard interrupt check (Ctrl+C / Ctrl+Break) ---
                # This try/except is checked once per node so the user can
                # interrupt the export at any time without losing progress.
                try:
                    if MAX_EXPORTS > 0 and ok >= MAX_EXPORTS:
                        print("")
                        print("STOPPED: reached MAX_EXPORTS limit (%d)." % MAX_EXPORTS)
                        log_lines.append("STOPPED: MAX_EXPORTS cap (%d) reached." % MAX_EXPORTS)
                        raise KeyboardInterrupt

                    r_name = _node_name(node)
                    fname = _sanitize_filename(r_name) + ".png"
                    dest = os.path.join(output_root, a_folder, fname)
                    dest = _unique_path(dest)

                    _restore_all_bodies_visible(model)
                    _activate(node)
                    try:
                        ExtAPI.Graphics.Refresh()  # noqa: F821
                    except Exception:
                        pass
                    _apply_view("isometric")
                    _export_png(dest, IMAGE_WIDTH, IMAGE_HEIGHT)
                    ok += 1
                    print("  OK   [%d] %s" % (ok, r_name))
                    log_lines.append("OK   [%s / %s] -> %s" % (a_name, r_name, dest))

                except KeyboardInterrupt:
                    interrupted = True
                    raise  # bubble up to outer handler

                except Exception as exc:
                    msg = _safe_str(exc)
                    print("  ERR  %s  (%s)" % (_node_name(node), msg))
                    log_lines.append("ERR  [%s / %s] %s" % (a_name, _node_name(node), msg))

    except KeyboardInterrupt:
        interrupted = True
        print("")
        print("*** INTERRUPTED by user (Ctrl+C / Ctrl+Break) ***")
        print("Saving partial log...")

    finally:
        note = "INTERRUPTED" if interrupted else ""
        log_path = _flush_log(note)
        print("")
        print("=" * 60)
        if interrupted:
            print("Export INTERRUPTED after %d PNG(s)." % ok)
        else:
            print("Auto-discover complete.")
        print("Result nodes found : %d" % total_nodes)
        print("PNGs exported      : %d" % ok)
        print("Output folder      : %s" % output_root)
        print("Log                : %s" % log_path)
        print("=" * 60)

    return ok


def _get_all_analyses(model):
    """Return list of every Analysis node in the model."""
    analyses = []
    seen_ids = set()

    def _add(node):
        try:
            nid = id(node)
            if nid in seen_ids:
                return
            seen_ids.add(nid)
            analyses.append(node)
        except Exception:
            pass

    # Primary: model.Analyses property (most reliable)
    try:
        for a in model.Analyses:
            _add(a)
        if analyses:
            return analyses
    except Exception:
        pass

    # Fallback: walk the tree and pick Analysis-typed nodes
    for node in _walk_tree(model):
        try:
            t = node.GetType().Name
        except Exception:
            continue
        if "Analysis" in t and "Settings" not in t and "Information" not in t:
            _add(node)

    return analyses


def _find_solution_node(analysis):
    """Return the Solution node that lives directly under an analysis."""
    # Direct attribute (most reliable)
    try:
        sol = analysis.Solution
        if sol is not None:
            return sol
    except Exception:
        pass

    # Walk immediate children
    for child in _iter_children(analysis):
        name = _node_name(child).lower()
        if name == "solution":
            return child
        try:
            t = child.GetType().Name
            if (
                "Solution" in t
                and "Settings" not in t
                and "Information" not in t
                and "SolutionConfiguration" not in t
            ):
                return child
        except Exception:
            pass

    return None


def _is_skip_prefix(name_lower):
    """Return True if a node's name matches the skip-completely list."""
    for prefix in _AUTO_SKIP_PREFIXES:
        if name_lower.startswith(prefix):
            return True
    return False


def _is_container_prefix(name_lower):
    """Return True if a node is a transparent container (recurse but don't export)."""
    for prefix in _AUTO_CONTAINER_PREFIXES:
        if name_lower.startswith(prefix):
            return True
    return False


def _collect_result_nodes_under(sol_node, _visited=None):
    """
    Walk *sol_node* (the Solution branch) and yield every exportable result
    node in depth-first order.

    Rules:
      - Nodes matching _AUTO_SKIP_PREFIXES → skip node AND all its children.
      - Nodes matching _AUTO_CONTAINER_PREFIXES → don't export the node itself
        but DO recurse into its children (e.g. Contact Tool > Contact Pressure).
      - Everything else → yield the node, then recurse into its children.
    Cycle protection via _visited id-set prevents infinite loops.
    """
    if _visited is None:
        _visited = set()

    for child in _iter_children(sol_node):
        try:
            cid = id(child)
        except Exception:
            continue
        if cid in _visited:
            continue
        _visited.add(cid)

        name = _node_name(child).lower().strip()
        if not name:
            continue

        if _is_skip_prefix(name):
            continue

        if _is_container_prefix(name):
            for sub in _collect_result_nodes_under(child, _visited):
                yield sub
        else:
            yield child
            for sub in _collect_result_nodes_under(child, _visited):
                yield sub


def _export_setup_views(model, output_root):
    """
    Export common geometry/mesh/connections views into output_root/common/.
    Returns (ok_count, node_count, log_lines).
    """
    common_dir = os.path.join(output_root, "common")
    targets = [
        ("Geometry", "geometry_isometric.png", True),
        ("Mesh", "mesh_isometric.png", True),
        ("Connections", "contacts_isometric.png", True),
        ("Coordinate Systems", "coordinate_systems_isometric.png", True),
    ]

    ok = 0
    log_lines = []
    print("--- Common setup views ---")

    for label, fname, partial in targets:
        node = _find_by_name(model, label, partial=False)
        if node is None and partial:
            node = _find_by_name(model, label, partial=True)
        if node is None:
            print("  SKIP common/%s (not found)" % fname)
            continue

        dest = os.path.join(common_dir, fname)
        try:
            _restore_all_bodies_visible(model)
            _activate(node)
            try:
                ExtAPI.Graphics.Refresh()  # noqa: F821
            except Exception:
                pass
            _apply_view("isometric")
            _export_png(dest, IMAGE_WIDTH, IMAGE_HEIGHT)
            ok += 1
            print("  OK   common/%s" % fname)
            log_lines.append("OK   [common / %s] -> %s" % (label, dest))
        except Exception as exc:
            msg = _safe_str(exc)
            print("  ERR  common/%s  (%s)" % (fname, msg))
            log_lines.append("ERR  [common / %s] %s" % (label, msg))

    print("")
    return ok, len(targets), log_lines


# ---------------------------------------------------------------------------
# Manifest-driven export (kept for backward compatibility / AUTO_DISCOVER=False)
# ---------------------------------------------------------------------------


def _export_system(model, manifest, output_root, system_key, analysis_root, quiet_summary=False):
    systems = manifest.get("systems") or {}
    if system_key not in systems:
        _fail(
            "System %s is not in the export manifest.\nKnown keys: %s"
            % (system_key, ", ".join(sorted(systems.keys())))
        )

    system_spec = systems[system_key]
    exports = system_spec.get("exports") or []
    log_path = os.path.join(output_root, "export_log_%s.txt" % system_key.replace("-", "_"))
    log_lines = []
    log_lines.append("EP2737 Mechanical export")
    log_lines.append("Time: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    log_lines.append("System: %s (%s)" % (system_key, system_spec.get("label", "")))
    log_lines.append("Output: %s" % output_root)
    log_lines.append("Jobs: %d" % len(exports))
    log_lines.append("-" * 60)

    ok = 0
    skipped = 0
    failed = 0

    if analysis_root is not None:
        try:
            _activate(analysis_root)
        except Exception:
            pass

    if not quiet_summary:
        print("Using system key: %s" % system_key)
        print("Exporting %d job(s)..." % len(exports))
        print("")

    for job in exports:
        slot = job.get("slot", "?")
        rel_file = job.get("file", "")
        dest = os.path.join(output_root, rel_file.replace("/", os.sep))
        required = bool(job.get("required", False))
        try:
            success, note = _run_export_job(model, job, dest, analysis_root=analysis_root)
            if success:
                ok += 1
                log_lines.append("OK   [%s] -> %s (%s)" % (slot, rel_file, note))
                print("OK   %s -> %s" % (slot, dest))
            else:
                skipped += 1
                log_lines.append("SKIP [%s] -> %s (%s)" % (slot, rel_file, note))
                print("SKIP %s - %s" % (slot, note))
                if required:
                    failed += 1
        except Exception as exc:
            skipped += 1
            if required:
                failed += 1
            msg = str(exc)
            log_lines.append("ERR  [%s] -> %s (%s)" % (slot, rel_file, msg))
            print("ERR  %s - %s" % (slot, msg))

    _restore_all_bodies_visible(model)

    log_lines.append("-" * 60)
    log_lines.append("Exported: %d  Skipped: %d  Required failures: %d" % (ok, skipped, failed))
    _write_log(log_path, log_lines)

    if not quiet_summary:
        print("")
        print("Done. Exported %d PNG(s) for %s." % (ok, system_key))
        print("Log: %s" % log_path)
        if failed:
            print("WARNING: %d required export(s) failed - check the log." % failed)

    return ok, skipped, failed


def _run_export_job(model, job, dest_path, analysis_root=None):
    export_type = (job.get("type") or "result").lower()
    scope = (job.get("scope") or "assembly").lower()
    view = (job.get("view") or "isometric").lower()
    search_root = analysis_root or model

    _restore_all_bodies_visible(model)

    if export_type == "viewport":
        obj = _find_viewport_target(search_root, job, model=model)
        if obj is None:
            return False, "tree object not found for viewport export"
        _activate(obj)
        if job.get("show_loads"):
            _show_loads(True)
    else:
        obj = _find_result_object(search_root, job)
        if obj is None:
            return False, "result not found - create/insert the result in Mechanical first"
        _activate(obj)
        _try_set_mode(obj, job.get("mode"))
        _try_set_load_step(model, obj, job.get("load_step"))

    if scope == "flange":
        _apply_flange_scope(model)
    else:
        _restore_all_bodies_visible(model)

    _apply_view(view)
    _export_png(dest_path, IMAGE_WIDTH, IMAGE_HEIGHT)
    return True, export_type


# ---------------------------------------------------------------------------
# Mechanical tree helpers
# ---------------------------------------------------------------------------


def _iter_children(obj):
    try:
        count = obj.Children.Count
    except Exception:
        return
    for i in range(count):
        try:
            yield obj.Children[i]
        except Exception:
            pass


def _walk_tree(root):
    stack = [root]
    visited = set()
    while stack:
        node = stack.pop()
        try:
            nid = id(node)
        except Exception:
            continue
        if nid in visited:
            continue
        visited.add(nid)
        yield node
        for child in _iter_children(node):
            stack.append(child)


def _node_name(node):
    try:
        return node.Name or ""
    except Exception:
        return ""


def _find_viewport_target(search_root, job, model=None):
    activate_names = job.get("activate") or []
    keywords = job.get("keywords") or []
    fallbacks = [search_root]
    if model is not None and model is not search_root:
        fallbacks.append(model)

    for root in fallbacks:
        for label in activate_names:
            hit = _find_by_name(root, label, partial=True)
            if hit:
                return hit
        for kw in keywords:
            hit = _find_by_name(root, kw, partial=True)
            if hit:
                return hit

    return search_root


def _find_result_object(search_root, job):
    keywords = list(job.get("keywords") or [])
    mode = job.get("mode")
    scope = (job.get("scope") or "assembly").lower()

    if scope == "flange":
        keywords.extend(["WELDED PLANE PIPE FLANGE", "ASTM A182", "ASTM"])

    candidates = []
    for node in _walk_tree(search_root):
        name = _node_name(node)
        lname = name.lower()
        if not any(kw.lower() in lname for kw in keywords):
            continue
        if "chart" in lname and "chart" not in " ".join(k.lower() for k in keywords):
            continue
        if scope == "flange" and "equivalent stress" in lname:
            candidates.append(node)
            continue
        if scope == "flange" and any(x in lname for x in ("flange", "astm", "welded")):
            candidates.insert(0, node)
            continue
        candidates.append(node)

    if mode is not None:
        mode_hits = []
        mode_label = "mode %d" % int(mode)
        for node in candidates:
            lname = _node_name(node).lower()
            if mode_label in lname or lname.endswith(" %d" % int(mode)):
                mode_hits.append(node)
        if mode_hits:
            return mode_hits[0]
        deform = [n for n in candidates if "deformation" in _node_name(n).lower()]
        idx = int(mode) - 1
        if 0 <= idx < len(deform):
            return deform[idx]

    if candidates:
        candidates.sort(key=lambda n: len(_node_name(n)))
        return candidates[0]
    return None


def _find_by_name(root, text, partial=True):
    text_l = text.lower()
    for node in _walk_tree(root):
        name = _node_name(node).lower()
        if partial and text_l in name:
            return node
        if not partial and name == text_l:
            return node
    return None


def _activate(obj):
    try:
        obj.Activate()
        return
    except Exception:
        pass
    try:
        obj.Activate(True)
    except Exception:
        pass


def _show_loads(enabled):
    try:
        ExtAPI.Graphics.Options.ShowLoads = enabled  # noqa: F821
    except Exception:
        pass


def _apply_view(view):
    cam = ExtAPI.Graphics.Camera  # noqa: F821
    try:
        if view == "isometric":
            cam.SetIsometric()
        cam.SetFit()
    except Exception:
        pass


def _export_png(path, width, height):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    graphics = ExtAPI.Graphics  # noqa: F821
    errors = []

    try:
        graphics.ExportImage(path, width, height)
        return
    except Exception as exc:
        errors.append(str(exc))

    try:
        graphics.ExportImage(path, int(width), int(height), True)
        return
    except Exception as exc:
        errors.append(str(exc))

    try:
        graphics.ExportImage(path)
        return
    except Exception as exc:
        errors.append(str(exc))

    raise RuntimeError("ExportImage failed: " + " | ".join(errors))


def _all_bodies(model):
    bodies = []
    try:
        geometry = model.Geometry
    except Exception:
        return bodies
    for node in _walk_tree(geometry):
        try:
            ctype = node.GetType().Name
        except Exception:
            ctype = ""
        if "Body" in ctype or ctype.endswith("Body"):
            bodies.append(node)
    return bodies


def _restore_all_bodies_visible(model):
    for body in _all_bodies(model):
        try:
            body.Visible = True
        except Exception:
            pass


def _apply_flange_scope(model):
    _restore_all_bodies_visible(model)
    shown = 0
    for body in _all_bodies(model):
        name = _node_name(body).lower()
        if any(h in name for h in FLANGE_NAME_HINTS):
            try:
                body.Visible = True
                shown += 1
            except Exception:
                pass
        else:
            try:
                body.Visible = False
            except Exception:
                pass

    if shown == 0:
        for node in _walk_tree(model):
            lname = _node_name(node).lower()
            if "named selection" in lname or lname == "flange":
                if "flange" in lname:
                    _activate(node)
                    return


def _try_set_mode(result_obj, mode):
    if mode is None:
        return
    for method in ("SetMode", "SetResultMode"):
        try:
            getattr(result_obj, method)(int(mode))
            return
        except Exception:
            pass
    try:
        result_obj.Mode = int(mode)
    except Exception:
        pass


def _try_set_load_step(model, result_obj, load_step):
    if not load_step:
        return
    if str(load_step).lower() != "last":
        return
    node = result_obj
    for _ in range(12):
        if node is None:
            break
        for method in ("SetResultStep", "SetStep", "SetLastStep"):
            try:
                fn = getattr(node, method)
                fn()
                return
            except Exception:
                pass
        try:
            node = node.Parent
        except Exception:
            break


# ---------------------------------------------------------------------------
# Manifest / environment helpers
# ---------------------------------------------------------------------------


def _load_manifest():
    path = MANIFEST_PATH
    if not os.path.isfile(path):
        _fail("Manifest not found: %s\nEdit MANIFEST_PATH at the top of this script." % path)
    with open(path, "r") as fh:
        return json.load(fh)


def _try_load_manifest():
    """Non-fatal version: returns None if the manifest is absent or broken."""
    if not os.path.isfile(MANIFEST_PATH):
        return None
    try:
        with open(MANIFEST_PATH, "r") as fh:
            return json.load(fh)
    except Exception:
        return None


def _detect_system_key(model):
    active = _detect_system_from_active(model)
    if active:
        return active
    return _detect_system_from_path()


def _detect_system_from_path():
    candidates = []
    try:
        candidates.append(ExtAPI.DataModel.Project.ProjectDirectory)  # noqa: F821
    except Exception:
        pass
    try:
        candidates.append(ExtAPI.DataModel.Project.RootDirectory)  # noqa: F821
    except Exception:
        pass
    try:
        candidates.append(ExtAPI.DataModel.Project.ProjectPath)  # noqa: F821
    except Exception:
        pass
    candidates.append(os.getcwd())

    pattern = re.compile(r"[\\/]dp0[\\/](SYS(?:-\d+)?)[\\/]MECH", re.IGNORECASE)
    for raw in candidates:
        if not raw:
            continue
        norm = str(raw).replace("/", "\\")
        match = pattern.search(norm)
        if match:
            return match.group(1).upper()
    return None


def _detect_system_from_active(model):
    obj = _get_activated_object(model)
    node = obj
    for _ in range(30):
        if node is None:
            break
        name = _node_name(node)
        sys_key = _map_analysis_label_to_sys(name)
        if sys_key:
            return sys_key
        try:
            if "Analysis" in node.GetType().Name:
                sys_key = _map_analysis_label_to_sys(name)
                if sys_key:
                    return sys_key
        except Exception:
            pass
        try:
            node = node.Parent
        except Exception:
            break
    return None


def _get_activated_object(model):
    try:
        obj = model.ActivatedObject
        if obj is not None:
            return obj
    except Exception:
        pass
    try:
        active = ExtAPI.DataModel.Project.GetActiveObjects()  # noqa: F821
        if active and len(active) > 0:
            return active[0]
    except Exception:
        pass
    try:
        active = model.GetActiveObjects()
        if active and len(active) > 0:
            return active[0]
    except Exception:
        pass
    return None


def _list_analysis_names(model):
    names = []
    try:
        for analysis in model.Analyses:
            names.append(_node_name(analysis))
    except Exception:
        pass
    if not names:
        for node in _walk_tree(model):
            try:
                if "Analysis" in node.GetType().Name:
                    name = _node_name(node)
                    if name and name not in names:
                        names.append(name)
            except Exception:
                pass
    return names


def _map_analysis_label_to_sys(label):
    if not label:
        return None
    n = label.lower().strip()

    if "static structural" in n:
        return "SYS"
    if re.search(r"\bmodal\b", n):
        return "SYS-1"

    if "harmonic" in n:
        if "x direction" in n or re.search(r"\bx\b", n):
            return "SYS-2"
        if "y direction" in n or re.search(r"\by\b", n):
            return "SYS-3"
        if "z direction" in n or re.search(r"\bz\b", n):
            return "SYS-4"

    if "shock" in n or "equivalent static" in n or "equivalent shock" in n:
        if re.search(r"[+]\s*x\b|plus\s*x|\+\s*x", n):
            return "SYS-5"
        if re.search(r"[+]\s*y\b|plus\s*y|\+\s*y", n):
            return "SYS-6"
        if re.search(r"[+]\s*z\b|plus\s*z|\+\s*z", n):
            return "SYS-7"
        if re.search(r"[-\u2212]\s*x\b|minus\s*x|\-\s*x", n):
            return "SYS-8"
        if re.search(r"[-\u2212]\s*y\b|minus\s*y|\-\s*y", n):
            return "SYS-9"
        if re.search(r"[-\u2212]\s*z\b|minus\s*z|\-\s*z", n):
            return "SYS-10"

    return None


def _map_analyses_to_systems(model):
    mapped = []
    seen = set()
    for name in _list_analysis_names(model):
        key = _map_analysis_label_to_sys(name)
        if not key or key in seen:
            continue
        obj = _find_analysis_by_name(model, name)
        if obj is None:
            continue
        mapped.append((key, name, obj))
        seen.add(key)

    def sort_key(item):
        try:
            return SYSTEM_ORDER.index(item[0])
        except ValueError:
            return 99

    mapped.sort(key=sort_key)
    return mapped


def _analysis_root_for_key(mapped, system_key):
    for key, _name, obj in mapped:
        if key == system_key:
            return obj
    return None


def _find_analysis_by_name(model, name):
    try:
        for analysis in model.Analyses:
            if _node_name(analysis) == name:
                return analysis
    except Exception:
        pass
    for node in _walk_tree(model):
        if _node_name(node) != name:
            continue
        try:
            if "Analysis" in node.GetType().Name:
                return node
        except Exception:
            pass
    return None


def _print_detection_debug(model, mapped=None):
    try:
        proj = ExtAPI.DataModel.Project.ProjectDirectory  # noqa: F821
    except Exception:
        proj = "?"
    print("Project directory: %s" % proj)
    print("Path detect:     %s" % (_detect_system_from_path() or "(none)"))
    print("Active detect:   %s" % (_detect_system_from_active(model) or "(none)"))
    analyses = _list_analysis_names(model)
    if analyses:
        print("Analyses:        %s" % ", ".join(analyses))
    if mapped:
        print("Mapped systems:  %s" % ", ".join("%s=%s" % (k, n) for k, n, _ in mapped))
        if len(mapped) >= 2 and EXPORT_ALL_IF_COMBINED and not SYSTEM_OVERRIDE:
            print("Mode:            EXPORT ALL (combined session)")
    print("")


def _require_mechanical():
    try:
        ExtAPI  # noqa: F821
    except NameError:
        print("")
        print("ERROR: ExtAPI is not available.")
        print("This script must be run INSIDE ANSYS Mechanical, not from Windows cmd/PowerShell.")
        print("")
        raise ExportError("ExtAPI not available")


def _write_log(path, lines):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    safe_lines = [_safe_str(line) for line in lines]
    with open(path, "w") as fh:
        fh.write("\n".join(safe_lines) + "\n")


def _fail(message):
    print("")
    print("ERROR: " + message)
    print("")
    raise ExportError(message)


# Mechanical Scripting "Run" does not set __name__ == "__main__". main() always runs on execute.
try:
    main()
except ExportError:
    pass
except SystemExit:
    pass
except KeyboardInterrupt:
    print("")
    print("Export stopped by user.")
    print("")
