# -*- coding: utf-8 -*-
"""
EP2737 - batch export report figures from ANSYS Mechanical.

RUN INSIDE MECHANICAL (not Workbench, not this repo's terminal):
  Automation tab -> Scripting -> Open this file -> Run (green play).
  main() runs automatically (Mechanical does not set __name__ == "__main__").
  If needed, type main() in the Shell panel.

AUTO-DISCOVER MODE (default, AUTO_DISCOVER = True)
---------------------------------------------------
Exports:
  - Model: geometry, mesh, connections, coordinate systems, materials
  - Each analysis: loading overview (all loads visible) + each load/BC
  - Solution: all 3D results + center Worksheet chart PNGs (frequency response, …)
Suppressed tree items are skipped.  Manifest is optional (image size only).

Also run scripts/mechanical/export_result_summary.py (same session) to export
Result Summary JSON for report tables under exports/result_summaries/.

Output structure:
  exports/
    geometry/  mesh/  connections/  coordinate_systems/  materials/
    <analysis_name>/
      loading/
        loading_conditions_overview.png
        fixed_support.png  pressure.png  ...
      solution/
        total_deformation.png
        total_deformation_2.png  ...
        graphs/
          frequency_response.png
          acceleration.png  ...
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
# OPTIONAL OVERRIDES — leave None to auto-detect (works on any machine).
# Exports default to <case_folder>/exports where case_folder is:
#   1) the folder containing this script (when opened from ep2731/, etc.), then
#   2) the active Mechanical MECH path, then Workbench project paths.
# Set OUTPUT_ROOT only if auto-detect still lands in the wrong folder.
# =============================================================================
OUTPUT_ROOT = None
MANIFEST_PATH = None

# Set to "SYS", "SYS-1", ... "SYS-10" to force one system only (manifest mode)
SYSTEM_OVERRIDE = None

# When multiple analyses live in one Mechanical session, export ALL of them.
EXPORT_ALL_IF_COMBINED = True

# ---------------------------------------------------------------------------
# AUTO-DISCOVER SETTINGS
# ---------------------------------------------------------------------------
# True  → model views + all loads + full Solution tree per analysis.
# False → use the JSON manifest exclusively (original behaviour).
AUTO_DISCOVER = True

# Model-level views to capture (folder name, tree search labels).
_AUTO_MODEL_VIEWS = (
    ("geometry", ("Geometry",)),
    ("mesh", ("Mesh",)),
    ("connections", ("Connections", "Contacts")),
    ("coordinate_systems", ("Coordinate Systems",)),
)

# Loading / BC nodes under an analysis (outside Solution).
_LOADING_NAME_KEYWORDS = (
    "fixed support",
    "displacement",
    "pressure",
    "force",
    "gravity",
    "acceleration",
    "moment",
    "bearing",
    "remote",
    "temperature",
    "base excitation",
    "harmonic load",
    "shock",
    "earth gravity",
    "mass",
    "bolt",
    "preload",
    "rotation",
    "velocity",
)

_LOADING_TYPE_HINTS = (
    "Load",
    "Support",
    "Condition",
    "Acceleration",
    "Pressure",
    "Force",
    "Displacement",
    "Gravity",
    "Moment",
    "Mass",
)

# Pause after activate/refresh so Zoom-to-Fit applies before capture (seconds).
_GRAPHICS_SETTLE_S = 0.08

# Worksheet / 2-D graph nodes in Solution (name hints — type "Chart" is preferred).
_CHART_NAME_KEYWORDS = (
    "chart",
    "frequency response",
    "phase angle",
    "response spectrum",
    "time history",
    "bode",
)

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
MAX_EXPORTS = 0
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
        proj = _get_project_directory()
        print("EP2737 Auto-Discover Export")
        print("Project : %s" % proj)
        print("")

        # Try to pick up image-size override from manifest (optional).
        manifest = _try_load_manifest()
        manifest_path = _resolve_manifest_path()
        if manifest:
            if manifest.get("image_width"):
                global IMAGE_WIDTH, IMAGE_HEIGHT
                IMAGE_WIDTH = int(manifest["image_width"])
                IMAGE_HEIGHT = int(manifest["image_height"])

        output_root = _resolve_output_root(manifest)
        print("Output  : %s" % output_root)
        if manifest_path:
            print("Manifest: %s" % manifest_path)
        else:
            print("Manifest: (none — image size defaults only)")
        print("")

        _auto_discover_and_export(model, output_root)
        return

    # ---------- Original manifest-driven flow ----------
    manifest = _load_manifest()
    if manifest.get("image_width"):
        global IMAGE_WIDTH, IMAGE_HEIGHT
        IMAGE_WIDTH = int(manifest["image_width"])
        IMAGE_HEIGHT = int(manifest["image_height"])

    output_root = _resolve_output_root(manifest)
    print("Output  : %s" % output_root)
    print("")

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
    """Export important model views, loading conditions, and key solution results."""
    log_lines = [
        "EP2737 Auto-Discover Export (important items only)",
        "Time   : %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
        "Output : %s" % output_root,
        "-" * 60,
    ]
    ok = 0
    total_nodes = 0
    interrupted = False
    stats = {"ok": ok, "total_nodes": total_nodes, "interrupted": interrupted}

    def _flush_log(note=""):
        log_lines.append("-" * 60)
        msg = "Targets queued: %d   PNGs exported: %d" % (stats["total_nodes"], stats["ok"])
        if note:
            msg += "  [%s]" % note
        log_lines.append(msg)
        log_path = os.path.join(output_root, "auto_discover_log.txt")
        _write_log(log_path, log_lines)
        return log_path

    def _try_export(node, dest, section, show_loads=False, last_step=False, view="isometric"):
        if MAX_EXPORTS > 0 and stats["ok"] >= MAX_EXPORTS:
            raise KeyboardInterrupt
        r_name = _node_name(node)
        if _is_suppressed(node):
            print("  SKIP %s (suppressed in tree)" % r_name)
            log_lines.append("SKIP [%s / %s] suppressed in tree" % (section, r_name))
            return
        dest = _unique_path(dest)
        stats["total_nodes"] += 1
        _export_discovered_node(
            model, node, dest, show_loads=show_loads, last_step=last_step, view=view
        )
        stats["ok"] += 1
        print("  OK   [%d] %s" % (stats["ok"], r_name))
        log_lines.append("OK   [%s / %s] -> %s" % (section, r_name, dest))

    if MAX_EXPORTS > 0:
        print("Safety cap: MAX_EXPORTS = %d" % MAX_EXPORTS)
    print("")

    try:
        print("--- Model views ---")
        for folder, labels in _AUTO_MODEL_VIEWS:
            node = _find_tree_node(model, labels)
            if node is None:
                print("  SKIP %s/ (not found)" % folder)
                log_lines.append("SKIP [model / %s] not found" % folder)
                continue
            dest = os.path.join(output_root, folder, folder + ".png")
            try:
                _try_export(node, dest, folder)
            except KeyboardInterrupt:
                stats["interrupted"] = True
                raise
            except Exception as exc:
                msg = _safe_str(exc)
                print("  ERR  %s  (%s)" % (folder, msg))
                log_lines.append("ERR  [model / %s] %s" % (folder, msg))

        materials = _find_materials_node(model)
        if materials is None:
            print("  SKIP materials/ (not found)")
            log_lines.append("SKIP [model / materials] not found")
        else:
            dest = os.path.join(output_root, "materials", "materials.png")
            try:
                _try_export(materials, dest, "materials")
            except KeyboardInterrupt:
                stats["interrupted"] = True
                raise
            except Exception as exc:
                msg = _safe_str(exc)
                print("  ERR  materials  (%s)" % msg)
                log_lines.append("ERR  [model / materials] %s" % msg)

        print("")

        analyses = _get_all_analyses(model)
        if not analyses:
            print("WARNING: No analyses found.")
            log_lines.append("WARNING: No analyses found.")
        else:
            print("Found %d analysis/analyses." % len(analyses))
            print("")

        for analysis in analyses:
            if MAX_EXPORTS > 0 and stats["ok"] >= MAX_EXPORTS:
                print("STOPPED: reached MAX_EXPORTS limit (%d)." % MAX_EXPORTS)
                log_lines.append("STOPPED: MAX_EXPORTS cap (%d) reached." % MAX_EXPORTS)
                break

            a_name = _node_name(analysis)
            if _is_suppressed(analysis):
                print("  SKIP %s (suppressed in tree)" % a_name)
                log_lines.append("SKIP [%s] suppressed in tree" % a_name)
                continue

            a_folder = _sanitize_filename(a_name) or "analysis"
            loading = _collect_loading_conditions(analysis)
            sol_node = _find_solution_node(analysis)
            if sol_node:
                viewport_results, graph_results = _collect_solution_results(sol_node)
            else:
                viewport_results, graph_results = [], []

            print("-" * 60)
            print("Analysis : %s" % a_name)
            print(
                "Loading  : %d (+ overview)   Solution: %d   Graphs: %d"
                % (len(loading), len(viewport_results), len(graph_results))
            )
            print("")

            overview_dest = os.path.join(
                output_root, a_folder, "loading", "loading_conditions_overview.png"
            )
            try:
                _try_export(
                    analysis,
                    overview_dest,
                    a_name + "/loading",
                    show_loads=True,
                    view="fit",
                )
            except KeyboardInterrupt:
                stats["interrupted"] = True
                raise
            except Exception as exc:
                msg = _safe_str(exc)
                print("  ERR  loading overview  (%s)" % msg)
                log_lines.append("ERR  [%s / loading overview] %s" % (a_name, msg))

            for node in loading:
                try:
                    r_name = _node_name(node)
                    fname = _sanitize_filename(r_name) + ".png"
                    dest = os.path.join(output_root, a_folder, "loading", fname)
                    _try_export(node, dest, a_name + "/loading", show_loads=True, view="fit")
                except KeyboardInterrupt:
                    stats["interrupted"] = True
                    raise
                except Exception as exc:
                    msg = _safe_str(exc)
                    print("  ERR  %s  (%s)" % (_node_name(node), msg))
                    log_lines.append("ERR  [%s / loading / %s] %s" % (a_name, _node_name(node), msg))

            for node in viewport_results:
                try:
                    r_name = _node_name(node)
                    lname = r_name.lower()
                    if "maximum over time" in lname or "max over time" in lname:
                        fname = "equivalent_stress_maximum_overtime.png"
                    elif "equivalent stress" in lname or "von mises" in lname or "von-mises" in lname:
                        fname = "equivalent_stress.png"
                    else:
                        fname = _sanitize_filename(r_name) + ".png"
                    dest = os.path.join(output_root, a_folder, "solution", fname)
                    _try_export(node, dest, a_name + "/solution", last_step=True)
                    if "equivalent stress" in lname or "von mises" in lname or "von-mises" in lname:
                        flange_dest = os.path.join(
                            output_root, a_folder, "solution", "equivalent_stress_flange.png"
                        )
                        try:
                            _export_discovered_stress_flange(
                                model, node, flange_dest, last_step=True
                            )
                            stats["ok"] += 1
                            log_lines.append(
                                "OK   [%s / solution / flange stress] -> %s"
                                % (a_name, flange_dest)
                            )
                        except KeyboardInterrupt:
                            stats["interrupted"] = True
                            raise
                        except Exception as exc:
                            msg = _safe_str(exc)
                            print("  ERR  flange stress  (%s)" % msg)
                            log_lines.append(
                                "ERR  [%s / solution / flange stress] %s" % (a_name, msg)
                            )
                except KeyboardInterrupt:
                    stats["interrupted"] = True
                    raise
                except Exception as exc:
                    msg = _safe_str(exc)
                    print("  ERR  %s  (%s)" % (_node_name(node), msg))
                    log_lines.append("ERR  [%s / solution / %s] %s" % (a_name, _node_name(node), msg))

            for node in graph_results:
                try:
                    r_name = _node_name(node)
                    fname = _sanitize_filename(r_name) + ".png"
                    dest = os.path.join(output_root, a_folder, "solution", "graphs", fname)
                    _try_export(
                        node, dest, a_name + "/solution/graphs", last_step=True, view="graph"
                    )
                except KeyboardInterrupt:
                    stats["interrupted"] = True
                    raise
                except Exception as exc:
                    msg = _safe_str(exc)
                    print("  ERR  %s  (%s)" % (_node_name(node), msg))
                    log_lines.append(
                        "ERR  [%s / solution/graphs / %s] %s" % (a_name, _node_name(node), msg)
                    )

            if _is_modal_analysis_name(a_name):
                try:
                    _export_modal_mode_shapes(
                        model,
                        analysis,
                        sol_node,
                        output_root,
                        a_folder,
                        a_name,
                        _try_export,
                        stats,
                        log_lines,
                    )
                except KeyboardInterrupt:
                    stats["interrupted"] = True
                    raise
                except Exception as exc:
                    msg = _safe_str(exc)
                    print("  ERR  modal mode shapes  (%s)" % msg)
                    log_lines.append("ERR  [%s / modal modes] %s" % (a_name, msg))

    except KeyboardInterrupt:
        stats["interrupted"] = True
        print("")
        print("*** INTERRUPTED by user (Ctrl+C / Ctrl+Break) ***")
        print("Saving partial log...")

    finally:
        interrupted = stats["interrupted"]
        ok = stats["ok"]
        total_nodes = stats["total_nodes"]
        note = "INTERRUPTED" if interrupted else ""
        log_path = _flush_log(note)
        print("")
        print("=" * 60)
        if interrupted:
            print("Export INTERRUPTED after %d PNG(s)." % ok)
        else:
            print("Auto-discover complete.")
        print("Targets queued     : %d" % total_nodes)
        print("PNGs exported      : %d" % ok)
        print("Output folder      : %s" % output_root)
        print("Log                : %s" % log_path)
        print("=" * 60)

    return ok


def _export_discovered_stress_flange(model, node, dest_path, last_step=False):
    """Export an equivalent-stress result scoped to the flange named selection."""
    _restore_all_bodies_visible(model)
    _activate(node)
    if last_step:
        _try_set_load_step(model, node, "last")
    _apply_flange_scope(model)
    _apply_view("isometric")
    _export_png(dest_path, IMAGE_WIDTH, IMAGE_HEIGHT)
    _restore_all_bodies_visible(model)


def _export_discovered_node(model, node, dest_path, show_loads=False, last_step=False, view="isometric"):
    """Activate a tree node and export the current graphics view."""
    if view == "graph" or _is_worksheet_graph_node(node):
        _export_worksheet_graph(model, node, dest_path, last_step=last_step)
        return

    _restore_all_bodies_visible(model)
    _activate(node)
    if last_step:
        _try_set_load_step(model, node, "last")
    if show_loads:
        _show_loads(True)
    try:
        ExtAPI.Graphics.Refresh()  # noqa: F821
    except Exception:
        pass
    _apply_view(view)
    _prepare_graphics_for_export()
    _export_png(dest_path, IMAGE_WIDTH, IMAGE_HEIGHT)
    if show_loads:
        _show_loads(False)


def _get_all_analyses(model):
    """Return list of every Analysis node in the model."""
    analyses = []
    seen_ids = set()

    def _add(node):
        try:
            if _is_suppressed(node):
                return
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
            if not _is_suppressed(node):
                _add(node)

    return analyses


def _is_analysis_node(node):
    try:
        t = node.GetType().Name
    except Exception:
        return False
    return "Analysis" in t and "Settings" not in t and "Information" not in t


def _is_analyses_grouping(node):
    name = _node_name(node).lower().strip()
    if name in ("analyses", "analysis"):
        return True
    try:
        t = node.GetType().Name
    except Exception:
        return False
    return "Analyses" in t or "AnalysisGroup" in t


def _get_export_sections(model):
    """Legacy helper — retained for tests; auto-discover uses curated collectors."""
    sections = []
    seen_roots = set()

    def _add(folder, root):
        try:
            rid = id(root)
        except Exception:
            return
        if rid in seen_roots:
            return
        seen_roots.add(rid)
        folder = _sanitize_filename(folder) or "section"
        sections.append((folder, root))

    for child in _iter_children(model):
        if _is_suppressed(child):
            continue
        if _is_analyses_grouping(child):
            continue
        if _is_analysis_node(child):
            continue
        _add(_node_name(child), child)

    for analysis in _get_all_analyses(model):
        _add(_node_name(analysis), analysis)

    return sections


def _find_tree_node(model, labels):
    """Find the first unsuppressed tree node matching any label."""
    for label in labels:
        hit = _find_by_name(model, label, partial=False)
        if hit is None:
            hit = _find_by_name(model, label, partial=True)
        if hit is not None and not _is_suppressed(hit):
            return hit
    return None


def _find_materials_node(model):
    """Best-effort materials view: assignments folder, or Geometry fallback."""
    for label in ("Material Assignments", "Materials", "Engineering Data"):
        hit = _find_tree_node(model, (label,))
        if hit is not None:
            return hit
    geometry = _find_tree_node(model, ("Geometry",))
    if geometry is not None:
        return geometry
    for node in _walk_tree(model):
        if _is_suppressed(node):
            continue
        name = _node_name(node).lower()
        if "material" in name and "property" not in name:
            return node
    return None


def _node_type_name(node):
    try:
        return node.GetType().Name or ""
    except Exception:
        return ""


def _is_descendant_of(node, ancestor):
    if ancestor is None or node is None:
        return False
    current = node
    for _ in range(50):
        if current is None:
            return False
        if current is ancestor:
            return True
        try:
            current = current.Parent
        except Exception:
            break
        except:
            break
    return False


def _looks_like_loading(node, name_lower):
    if not name_lower or _is_skip_prefix(name_lower):
        return False
    if name_lower in ("solution", "analysis settings"):
        return False
    if any(k in name_lower for k in _LOADING_NAME_KEYWORDS):
        return True
    t = _node_type_name(node)
    if not t:
        return False
    if "Analysis" in t or "Solution" in t or "Result" in t:
        return False
    return any(h in t for h in _LOADING_TYPE_HINTS)


def _collect_loading_conditions(analysis):
    """Loads and BCs under an analysis, excluding the Solution branch."""
    sol = _find_solution_node(analysis)
    loads = []
    seen = set()

    for child in _iter_children(analysis):
        cname = _node_name(child).lower()
        if cname == "solution" or (sol is not None and child is sol):
            continue
        if _is_skip_prefix(cname):
            continue
        for node in _walk_tree(child):
            if _is_suppressed(node):
                continue
            if sol is not None and _is_descendant_of(node, sol):
                continue
            try:
                nid = id(node)
            except Exception:
                continue
            if nid in seen:
                continue
            name = _node_name(node).lower().strip()
            if not _looks_like_loading(node, name):
                continue
            seen.add(nid)
            loads.append(node)
    return loads


def _collect_solution_results(sol_node):
    """Split Solution nodes into 3-D viewport results and worksheet graph/chart results."""
    if sol_node is None or _is_suppressed(sol_node):
        return [], []

    viewport = []
    graphs = []
    for node in _collect_exportable_nodes_under(sol_node, include_root=False):
        if _is_worksheet_graph_node(node):
            graphs.append(node)
        else:
            viewport.append(node)
    return viewport, graphs


def _is_modal_analysis_name(name):
    """True for the standalone Modal analysis (not harmonic/shock nested Modal BC refs)."""
    if not name:
        return False
    n = name.lower().strip()
    if n != "modal":
        return False
    return True


def _modal_deformation_filename(mode):
    if int(mode) == 1:
        return "total_deformation.png"
    return "total_deformation_%d.png" % int(mode)


def _find_modal_deformation_nodes(analysis, sol_node):
    """Collect Total Deformation result nodes under Modal Solution (or analysis)."""
    nodes = []
    seen = set()
    roots = []
    if sol_node is not None:
        roots.append(sol_node)
    roots.append(analysis)

    for root in roots:
        for node in _collect_exportable_nodes_under(root, include_root=False):
            try:
                nid = id(node)
            except Exception:
                continue
            if nid in seen:
                continue
            lname = _node_name(node).lower()
            if "deformation" not in lname:
                continue
            if _is_worksheet_graph_node(node):
                continue
            seen.add(nid)
            nodes.append(node)

    def _sort_key(n):
        name = _node_name(n).lower()
        m = re.search(r"deformation\s*(\d+)", name)
        if m:
            return (0, int(m.group(1)))
        if name.strip() == "total deformation":
            return (0, 1)
        return (1, name)

    nodes.sort(key=_sort_key)
    return nodes


def _pick_modal_deform_node(nodes, mode):
    """Pick the tree node for *mode* (1-based), or a shared node for SetMode()."""
    mode = int(mode)
    mode_label = "mode %d" % mode
    for node in nodes:
        lname = _node_name(node).lower()
        if mode_label in lname:
            return node
        if lname.endswith(" %d" % mode) or lname.endswith("_%d" % mode):
            return node
        m = re.search(r"deformation\s*(\d+)", lname)
        if m and int(m.group(1)) == mode:
            return node
    idx = mode - 1
    if 0 <= idx < len(nodes):
        return nodes[idx]
    return nodes[0] if nodes else None


def _export_modal_mode_shapes(
    model,
    analysis,
    sol_node,
    output_root,
    a_folder,
    a_name,
    try_export_fn,
    stats,
    log_lines,
    num_modes=6,
):
    """
    Ensure modal/solution/total_deformation.png … _6.png exist.

    Auto-discover may skip Solution when the tree is empty or modes share one
    result object — this uses the same SetMode() path as manifest export.
    """
    if sol_node is None:
        sol_node = _find_solution_node(analysis)
    if sol_node is None:
        print("  SKIP modal modes (no Solution node under %s)" % a_name)
        log_lines.append("SKIP [%s / modal modes] no Solution node" % a_name)
        return

    deform_nodes = _find_modal_deformation_nodes(analysis, sol_node)
    if not deform_nodes:
        print("  SKIP modal modes (no Total Deformation under Solution)")
        log_lines.append("SKIP [%s / modal modes] no Total Deformation results" % a_name)
        return

    solution_dir = os.path.join(output_root, a_folder, "solution")
    exported = 0
    for mode in range(1, num_modes + 1):
        fname = _modal_deformation_filename(mode)
        dest = os.path.join(solution_dir, fname)
        if os.path.isfile(dest):
            continue

        node = _pick_modal_deform_node(deform_nodes, mode)
        if node is None:
            continue

        dest = _unique_path(dest)
        try:
            _activate(node)
            _try_set_mode(node, mode)
            try_export_fn(node, dest, a_name + "/solution", last_step=False, view="isometric")
            exported += 1
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            msg = _safe_str(exc)
            print("  ERR  modal mode %d  (%s)" % (mode, msg))
            log_lines.append("ERR  [%s / modal mode %d] %s" % (a_name, mode, msg))

    if exported:
        print("  Modal mode shapes exported: %d" % exported)


def _is_worksheet_graph_node(node):
    """True for ResultChart / Figure / worksheet plot nodes in Solution."""
    t = _node_type_name(node)
    if any(k in t for k in ("Chart", "Figure", "Graph", "Tracker")):
        return True

    name = _node_name(node).lower()
    if any(k in name for k in _CHART_NAME_KEYWORDS):
        return True

    for prop in ("ResultChartType", "ChartViewingStyle", "ChartDimensions", "XAxisValues"):
        try:
            if getattr(node, prop) is not None:
                return True
        except Exception:
            pass
        except:
            pass
    return False


def _export_worksheet_graph(model, node, dest_path, last_step=False):
    """Export the center Worksheet tab charts (not the bottom Graph pane)."""
    _activate(node)
    if last_step:
        _try_set_load_step(model, node, "last")

    for meth in ("EvaluateAllResults", "Evaluate"):
        try:
            getattr(node, meth)()
            break
        except Exception:
            pass
        except:
            pass

    _ensure_worksheet_visible()
    if _GRAPHICS_SETTLE_S > 0:
        time.sleep(_GRAPHICS_SETTLE_S * 3)

    _export_worksheet_graph_image(model, dest_path, IMAGE_WIDTH, IMAGE_HEIGHT)


def _ensure_worksheet_visible():
    """Show the main Worksheet pane (Amplitude/Phase charts in the center area)."""
    try:
        jscript = ExtAPI.Application.ScriptByName("jscript")  # noqa: F821
        jscript.ExecuteCommand(
            "if (!DS.Script.isWorksheetWindowActive()) "
            "DS.Script.toggleWorksheetVisibility();"
        )
    except Exception:
        pass
    except:
        pass


def _export_worksheet_graph_image(model, path, width, height):
    """Export Worksheet charts — center pane, not the bottom Graph/timeline pane."""
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    errors = []

    if _export_worksheet_via_jscript(path):
        return
    errors.append("WriteGraphToFile")

    try:
        if _export_worksheet_pane_screenshot(path, width, height):
            return
    except Exception as exc:
        errors.append("worksheet screenshot: " + str(exc))

    try:
        _prepare_chart_graphics_fallback(model)
        settings = _build_image_export_settings(append_graph=False, use_current_display=True)
        if settings is not None:
            ExtAPI.Graphics.ExportImage(path, GraphicsImageExportFormat.PNG, settings)  # noqa: F821
            if os.path.isfile(path):
                return
    except Exception as exc:
        errors.append("ExportImage: " + str(exc))

    raise RuntimeError("Worksheet graph export failed: " + " | ".join(errors))


def _export_worksheet_via_jscript(path):
    """DS.Script g_WorksheetTabBrowser WriteGraphToFile — format 0=PNG, 1=JPG, 3=BMP."""
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            fmt = 1
        elif ext == ".bmp":
            fmt = 3
        else:
            fmt = 0
        js_path = path.replace("\\", "/").replace('"', '\\"')
        jscript = ExtAPI.Application.ScriptByName("jscript")  # noqa: F821
        cmd = (
            "var g_WorksheetTabBrowser = DS.Script.g_WorksheetTabBrowser;"
            'var fName = "%s";'
            "g_WorksheetTabBrowser.Document.Script.WriteGraphToFile(%d, fName);"
        ) % (js_path, fmt)
        jscript.ExecuteCommand(cmd)
        return os.path.isfile(path)
    except Exception:
        return False


def _export_worksheet_pane_screenshot(path, width, height):
    """Screen-capture the Mechanical Worksheet pane (CopyFromScreen)."""
    try:
        import clr  # noqa: F401

        clr.AddReference("System.Drawing")
        from System.Drawing import Bitmap, Graphics, Size  # noqa: F401
    except Exception:
        return False

    pane = ExtAPI.UserInterface.GetPane(MechanicalPanelEnum.Worksheet)  # noqa: F821
    if pane is None:
        return False

    try:
        w = int(width) if width else int(pane.Control.Width)
        h = int(height) if height else int(pane.Control.Height)
        loc_x = int(pane.CommandContainer.WindowRect.Left)
        loc_y = int(pane.CommandContainer.WindowRect.Top)
    except Exception:
        return False

    if w <= 0 or h <= 0:
        return False

    bmp = Bitmap(w, h)
    g = Graphics.FromImage(bmp)
    try:
        g.CopyFromScreen(loc_x, loc_y, 0, 0, Size(w, h))
        bmp.Save(path)
    finally:
        g.Dispose()
        bmp.Dispose()

    return os.path.isfile(path)


def _prepare_chart_graphics_fallback(model):
    """Last resort: plain graphics export with no bottom-graph overlay."""
    _hide_all_bodies(model)
    _suppress_graph_overlay()


def _graphics_view_options():
    graphics = _extapi_get(lambda: ExtAPI.Graphics)  # noqa: F821
    if graphics is None:
        return None
    return getattr(graphics, "ViewOptions", None)


def _suppress_graph_overlay():
    """Hide the bottom-left Graph / result-tracker overlay before viewport capture."""
    vo = _graphics_view_options()
    if vo is not None:
        try:
            vo.DisplayGraphOverlay = False
        except Exception:
            pass
    try:
        ExtAPI.Graphics.Refresh()  # noqa: F821
    except Exception:
        pass


def _hide_all_bodies(model):
    for body in _all_bodies(model):
        try:
            body.Visible = False
        except Exception:
            pass
        except:
            pass


def _build_image_export_settings(append_graph=False, use_current_display=True):
    """Build GraphicsImageExportSettings when the Mechanical API is available."""
    try:
        settings = Ansys.Mechanical.Graphics.GraphicsImageExportSettings()  # noqa: F821
        settings.Width = int(IMAGE_WIDTH)
        settings.Height = int(IMAGE_HEIGHT)
        settings.CurrentGraphicsDisplay = bool(use_current_display)
        settings.AppendGraph = bool(append_graph)
        try:
            settings.Background = GraphicsBackgroundType.White  # noqa: F821
        except Exception:
            pass
        try:
            settings.Capture = GraphicsCaptureType.ImageAndLegend  # noqa: F821
        except Exception:
            pass
        return settings
    except Exception:
        return None


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


def _collect_exportable_nodes_under(root, include_root=False, _visited=None):
    """
    Walk *root* and yield every exportable tree node in depth-first order.

    Rules:
      - Suppressed nodes (or nodes under a suppressed parent) are skipped entirely.
      - Nodes matching _AUTO_SKIP_PREFIXES → skip node AND all its children.
      - Nodes matching _AUTO_CONTAINER_PREFIXES → don't export the node itself
        but DO recurse into its children (e.g. Contact Tool > Contact Pressure).
      - Everything else → yield the node, then recurse into its children.
    """
    if _visited is None:
        _visited = set()

    if include_root and not _is_suppressed(root):
        name = _node_name(root).strip()
        if name and not _is_skip_prefix(name.lower()):
            try:
                rid = id(root)
                if rid not in _visited:
                    _visited.add(rid)
                    yield root
            except Exception:
                pass

    for child in _iter_children(root):
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

        if _is_suppressed(child):
            continue

        if _is_skip_prefix(name):
            continue

        if _is_container_prefix(name):
            for sub in _collect_exportable_nodes_under(child, False, _visited):
                yield sub
        else:
            yield child
            for sub in _collect_exportable_nodes_under(child, False, _visited):
                yield sub


def _collect_result_nodes_under(sol_node, _visited=None):
    """Backward-compatible alias: exportable nodes under a Solution branch."""
    return _collect_exportable_nodes_under(sol_node, include_root=False, _visited=_visited)


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
        if _is_suppressed(obj):
            return False, "tree object is suppressed"
        _activate(obj)
        if job.get("show_loads"):
            _show_loads(True)
    else:
        obj = _find_result_object(search_root, job)
        if obj is None:
            return False, "result not found - create/insert the result in Mechanical first"
        if _is_suppressed(obj):
            return False, "result is suppressed in tree"
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


def _read_suppressed(node):
    """Return True/False if Suppressed is set; None if the property is unavailable."""
    try:
        return bool(node.Suppressed)
    except Exception:
        pass
    except:
        pass
    return None


def _is_suppressed(node):
    """True if this tree node or any ancestor is suppressed."""
    current = node
    for _ in range(50):
        if current is None:
            break
        state = _read_suppressed(current)
        if state is True:
            return True
        try:
            current = current.Parent
        except Exception:
            break
        except:
            break
    return False


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
        if _is_suppressed(node):
            continue
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
        if _is_suppressed(node):
            continue
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


def _apply_zoom_fit():
    """Zoom-to-fit (View > Zoom to Fit); safe to call before every export."""
    cam = _extapi_get(lambda: ExtAPI.Graphics.Camera)  # noqa: F821
    if cam is not None:
        for fit in (lambda: cam.SetFit(), lambda: cam.SetFit(None)):
            try:
                fit()
            except Exception:
                pass
            except:
                pass

    graphics = _extapi_get(lambda: ExtAPI.Graphics)  # noqa: F821
    if graphics is not None:
        mvm = getattr(graphics, "ModelViewManager", None)
        if mvm is not None:
            for meth in ("Fit", "ZoomToFit", "SetFit"):
                fn = getattr(mvm, meth, None)
                if fn is None:
                    continue
                try:
                    fn()
                except Exception:
                    pass
                except:
                    pass
        for refresh in (getattr(graphics, "Redraw", None), getattr(graphics, "Refresh", None)):
            if refresh is None:
                continue
            try:
                refresh()
            except Exception:
                pass
            except:
                pass


def _prepare_graphics_for_export():
    """Let the viewport settle, hide graph overlay, then zoom-to-fit twice before capture."""
    _suppress_graph_overlay()
    if _GRAPHICS_SETTLE_S > 0:
        time.sleep(_GRAPHICS_SETTLE_S)
    _apply_zoom_fit()
    if _GRAPHICS_SETTLE_S > 0:
        time.sleep(_GRAPHICS_SETTLE_S)
    _apply_zoom_fit()
    _suppress_graph_overlay()


def _apply_view(view):
    """Set camera orientation when requested, then always zoom-to-fit."""
    cam = _extapi_get(lambda: ExtAPI.Graphics.Camera)  # noqa: F821
    if cam is not None:
        if view == "isometric":
            try:
                cam.SetIsometric()
            except Exception:
                pass
            except:
                pass
        elif view == "fit":
            pass  # keep current orientation; fit only
    _apply_zoom_fit()


def _export_png(path, width, height):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    _prepare_graphics_for_export()

    graphics = ExtAPI.Graphics  # noqa: F821
    errors = []

    try:
        settings = _build_image_export_settings(append_graph=False, use_current_display=True)
        if settings is not None:
            graphics.ExportImage(path, GraphicsImageExportFormat.PNG, settings)  # noqa: F821
            if os.path.isfile(path):
                return
    except Exception as exc:
        errors.append(str(exc))

    try:
        graphics.ExportImage(path, int(width), int(height), False)
        if os.path.isfile(path):
            return
    except Exception as exc:
        errors.append(str(exc))

    try:
        graphics.ExportImage(path, int(width), int(height))
        if os.path.isfile(path):
            return
    except Exception as exc:
        errors.append(str(exc))

    try:
        graphics.ExportImage(path)
        if os.path.isfile(path):
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
        if _is_suppressed(node):
            continue
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
            if _is_suppressed(node):
                continue
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
    path = _resolve_manifest_path()
    if not path:
        _fail(
            "Manifest not found.\n"
            "Copy config/ep2737_mechanical_export.json onto this machine, or set "
            "MANIFEST_PATH at the top of this script to its full path."
        )
    with open(path, "r") as fh:
        return json.load(fh)


def _try_load_manifest():
    """Non-fatal version: returns None if the manifest is absent or broken."""
    path = _resolve_manifest_path()
    if not path:
        return None
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except Exception:
        return None


def _script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return None


_WB_FILES_DP0_RE = re.compile(
    r"^(.*)[\\/][^\\/]+_files[\\/]dp0(?:[\\/]|$)", re.IGNORECASE
)
_WB_MECH_PATH_RE = re.compile(
    r"^(.*)[\\/][^\\/]+_files[\\/]dp0[\\/]SYS(?:-\d+)?[\\/]MECH",
    re.IGNORECASE,
)
_WB_SYS_MECH_RE = re.compile(
    r"[\\/]dp0[\\/](SYS(?:-\d+)?)[\\/]MECH", re.IGNORECASE
)


def _is_repo_script_dir(path):
    norm = os.path.normpath(path).replace("\\", "/").lower()
    return norm.endswith("/scripts/mechanical")


def _looks_like_case_folder(folder):
    """True when *folder* looks like a Workbench case directory on disk."""
    if not folder or not os.path.isdir(folder):
        return False
    try:
        for name in os.listdir(folder):
            low = name.lower()
            if low.endswith(".wbpj") or low.endswith("_files"):
                return True
        for sub in ("exports", "images", "figures"):
            if os.path.isdir(os.path.join(folder, sub)):
                return True
    except Exception:
        pass
    return False


def _folder_from_workbench_path(raw_path):
    """Workbench project folder (directory containing the .wbpj), if inferrable."""
    if not raw_path or raw_path == "?":
        return None
    norm = str(raw_path).replace("/", "\\")
    match = _WB_FILES_DP0_RE.search(norm)
    if match:
        return os.path.normpath(match.group(1))
    norm_path = os.path.normpath(norm)
    if norm_path.lower().endswith(".wbpj"):
        return os.path.dirname(norm_path)
    if os.path.isdir(norm_path):
        if _looks_like_case_folder(norm_path):
            return norm_path
        # A plain directory path from ExtAPI — only trust it when it is a real folder.
        return norm_path
    parent = os.path.dirname(norm_path)
    return parent or None


def _project_folder(raw_path):
    """Backward-compatible alias for workbench path parsing."""
    return _folder_from_workbench_path(raw_path)


def _mech_project_folder(raw_path):
    """Project folder when *raw_path* points inside dp0/SYS*/MECH."""
    if not raw_path or raw_path == "?":
        return None
    norm = str(raw_path).replace("/", "\\")
    match = _WB_MECH_PATH_RE.search(norm)
    if match:
        return os.path.normpath(match.group(1))
    return _folder_from_workbench_path(raw_path)


def _case_folder_from_script():
    """Folder containing this script when run from a copied-in case directory."""
    script = _script_dir()
    if not script or _is_repo_script_dir(script):
        return None
    folder = os.path.normpath(script)
    if _looks_like_case_folder(folder):
        return folder
    # Script was opened from a case folder even before exports/.wbpj exist.
    return folder


def _collect_mech_project_folders():
    """Unique case folders inferred from active Mechanical / Workbench paths."""
    folders = []
    seen = set()
    for raw in _project_path_candidates():
        folder = _mech_project_folder(raw)
        if not folder:
            continue
        key = os.path.normcase(folder)
        if key in seen:
            continue
        seen.add(key)
        folders.append(folder)
    return folders


def _pick_mech_project_folder(mech_folders):
    """Choose one case folder when several MECH paths are visible."""
    if not mech_folders:
        return None
    if len(mech_folders) == 1:
        return mech_folders[0]

    active_sys = _detect_system_from_path()
    if active_sys:
        sys_pattern = re.compile(
            r"[\\/]dp0[\\/]" + re.escape(active_sys) + r"[\\/]MECH",
            re.IGNORECASE,
        )
        for raw in _project_path_candidates():
            if not raw:
                continue
            norm = str(raw).replace("/", "\\")
            if sys_pattern.search(norm):
                folder = _mech_project_folder(raw)
                if folder:
                    return folder

    script_folder = _case_folder_from_script()
    if script_folder:
        script_key = os.path.normcase(script_folder)
        for folder in mech_folders:
            if os.path.normcase(folder) == script_key:
                return folder
        for folder in mech_folders:
            if script_key.startswith(os.path.normcase(folder) + os.sep):
                return script_folder
            if os.path.normcase(folder).startswith(script_key + os.sep):
                return script_folder

    return mech_folders[0]


def _resolve_project_folder():
    """
    Best-effort case folder for exports/manifest.

    Priority:
      1. Script directory (when not the repo copy — user opened script in their case)
      2. Active MECH session path from ExtAPI
      3. Other Workbench paths from ExtAPI / cwd
    """
    script_folder = _case_folder_from_script()
    if script_folder:
        return script_folder

    mech_folder = _pick_mech_project_folder(_collect_mech_project_folders())
    if mech_folder:
        return mech_folder

    for raw in _project_path_candidates():
        folder = _folder_from_workbench_path(raw)
        if folder:
            return folder
    return None


def _path_parent_exists(path):
    parent = os.path.dirname(path)
    if not parent:
        return False
    try:
        return os.path.isdir(parent) or os.path.isdir(path)
    except Exception:
        return False


def _resolve_manifest_path():
    """Find ep2737_mechanical_export.json on this machine."""
    if MANIFEST_PATH:
        path = os.path.normpath(MANIFEST_PATH)
        if os.path.isfile(path):
            return path

    script = _script_dir()
    if script:
        for rel in (
            os.path.join("..", "..", "config", "ep2737_mechanical_export.json"),
            os.path.join("config", "ep2737_mechanical_export.json"),
        ):
            path = os.path.normpath(os.path.join(script, rel))
            if os.path.isfile(path):
                return path

    folder = _resolve_project_folder()
    if folder:
        for rel in (
            os.path.join("config", "ep2737_mechanical_export.json"),
            os.path.join("..", "config", "ep2737_mechanical_export.json"),
            os.path.join("..", "..", "config", "ep2737_mechanical_export.json"),
        ):
            path = os.path.normpath(os.path.join(folder, rel))
            if os.path.isfile(path):
                return path

    for raw in _project_path_candidates():
        folder = _folder_from_workbench_path(raw)
        if not folder:
            continue
        for rel in (
            os.path.join("config", "ep2737_mechanical_export.json"),
            os.path.join("..", "config", "ep2737_mechanical_export.json"),
            os.path.join("..", "..", "config", "ep2737_mechanical_export.json"),
        ):
            path = os.path.normpath(os.path.join(folder, rel))
            if os.path.isfile(path):
                return path
    return None


def _resolve_output_root(manifest=None):
    """Pick an export folder that exists on this machine."""
    if OUTPUT_ROOT:
        return os.path.normpath(OUTPUT_ROOT)

    folder = _resolve_project_folder()
    if folder:
        return os.path.join(folder, "exports")

    if manifest and manifest.get("output_root"):
        candidate = os.path.normpath(str(manifest["output_root"]))
        if _path_parent_exists(candidate):
            return candidate

    try:
        return os.path.join(os.getcwd(), "exports")
    except Exception:
        return "exports"


def _detect_system_key(model):
    active = _detect_system_from_active(model)
    if active:
        return active
    return _detect_system_from_path()


def _extapi_get(getter, default=None):
    """Read an ExtAPI property; Win32Exception is not always a Python Exception."""
    try:
        value = getter()
        if value is None:
            return default
        return value
    except:
        return default


def _project_path_candidates():
    """Project path strings for SYS detection; never raises."""
    candidates = []
    project = _extapi_get(lambda: ExtAPI.DataModel.Project)  # noqa: F821
    if project is not None:
        for prop in (
            "ProjectPath",
            "ProjectDirectory",
            "RootDirectory",
            "FilePath",
            "WorkingDirectory",
            "Directory",
            "Location",
        ):
            try:
                value = getattr(project, prop, None)
            except:
                value = None
            if value:
                candidates.append(value)
    script = _script_dir()
    if script:
        candidates.append(script)
    try:
        candidates.append(os.getcwd())
    except:
        pass

    mech_first = []
    other = []
    seen = set()
    for raw in candidates:
        if not raw:
            continue
        key = os.path.normcase(str(raw))
        if key in seen:
            continue
        seen.add(key)
        norm = str(raw).replace("/", "\\")
        if _WB_SYS_MECH_RE.search(norm) or "_files" in norm.lower():
            mech_first.append(raw)
        else:
            other.append(raw)
    return mech_first + other


def _get_project_directory():
    """Best-effort project folder for logging; never raises."""
    folder = _resolve_project_folder()
    if folder:
        return folder
    for raw in _project_path_candidates():
        if raw:
            return str(raw)
    return "?"


def _detect_system_from_path():
    candidates = _project_path_candidates()

    for raw in candidates:
        if not raw:
            continue
        norm = str(raw).replace("/", "\\")
        match = _WB_SYS_MECH_RE.search(norm)
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
            if _is_suppressed(analysis):
                continue
            names.append(_node_name(analysis))
    except Exception:
        pass
    if not names:
        for node in _walk_tree(model):
            try:
                if "Analysis" in node.GetType().Name:
                    if _is_suppressed(node):
                        continue
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
            if _node_name(analysis) == name and not _is_suppressed(analysis):
                return analysis
    except Exception:
        pass
    for node in _walk_tree(model):
        if _node_name(node) != name:
            continue
        if _is_suppressed(node):
            continue
        try:
            if "Analysis" in node.GetType().Name:
                return node
        except Exception:
            pass
    return None


def _print_detection_debug(model, mapped=None):
    proj = _get_project_directory()
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
