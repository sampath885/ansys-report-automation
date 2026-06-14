# -*- coding: utf-8 -*-
"""
EP2737 - batch export report figures from ANSYS Mechanical.

RUN INSIDE MECHANICAL (not Workbench, not this repo's terminal):
  Automation tab -> Scripting -> Open this file -> Run (green play).
  main() runs automatically (Mechanical does not set __name__ == "__main__").
  If needed, type main() in the Shell panel.

The script detects which Workbench system you opened (SYS, SYS-1, ... SYS-10),
or exports ALL analyses when they share one combined Mechanical session
(EP2737 default layout). PNGs are saved under:

  c:\\Users\\jaswa\\OneDrive\\Desktop\\ansys automation\\ansys_automation_files\\exports\\...

Log file:  <exports>/export_log_<SYS>.txt

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
OUTPUT_ROOT = r"c:\Users\jaswa\OneDrive\Desktop\ansys automation\ansys_automation_files\exports"
MANIFEST_PATH = r"c:\Users\jaswa\OneDrive\Desktop\ansys automation\config\ep2737_mechanical_export.json"

# Set to "SYS", "SYS-1", ... "SYS-10" to force one system only (otherwise leave None)
SYSTEM_OVERRIDE = None

# When multiple analyses live in one Mechanical session, export ALL of them in one Run.
EXPORT_ALL_IF_COMBINED = True
# =============================================================================

SYSTEM_ORDER = ["SYS"] + ["SYS-%d" % i for i in range(1, 11)]

FLANGE_NAME_HINTS = ("flange", "pipe flange", "welded", "cut-extrude")
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080


class ExportError(Exception):
    """Raised instead of sys.exit so Mechanical Shell does not show SystemExitException."""


def main():
    try:
        _main_impl()
    except ExportError:
        return 1
    return 0


def _main_impl():
    _require_mechanical()
    manifest = _load_manifest()
    if manifest.get("image_width"):
        global IMAGE_WIDTH, IMAGE_HEIGHT
        IMAGE_WIDTH = int(manifest["image_width"])
        IMAGE_HEIGHT = int(manifest["image_height"])

    output_root = manifest.get("output_root") or OUTPUT_ROOT
    output_root = os.path.normpath(output_root)

    model = ExtAPI.DataModel.Project.Model  # noqa: F821 - provided by Mechanical
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
    while stack:
        node = stack.pop()
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
        # Fallback: nth deformation result under Solution
        deform = [n for n in candidates if "deformation" in _node_name(n).lower()]
        idx = int(mode) - 1
        if 0 <= idx < len(deform):
            return deform[idx]

    if candidates:
        # Prefer shortest name match (usually the parent result, not sub-features)
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

    # ANSYS versions use slightly different ExportImage signatures
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
        # Try named selection
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
    # Walk up to Solution / analysis and pick last step if API exists
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
# Manifest / environment
# ---------------------------------------------------------------------------


def _load_manifest():
    path = MANIFEST_PATH
    if not os.path.isfile(path):
        _fail("Manifest not found: %s\nEdit MANIFEST_PATH at the top of this script." % path)
    with open(path, "r") as fh:
        return json.load(fh)


def _detect_system_key(model):
    """Prefer active/selected analysis (combined Mechanical tree), then folder path."""
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
    """Map clicked/active result to SYS key via parent analysis name."""
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

    # Fallback: only one harmonic/modal/etc. with results - scan top-level analyses
    try:
        for analysis in model.Analyses:
            sys_key = _map_analysis_label_to_sys(_node_name(analysis))
            if sys_key:
                # If multiple, don't guess - active walk should have worked
                pass
    except Exception:
        pass
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
        if re.search(r"[-−]\s*x\b|minus\s*x|\-\s*x", n):
            return "SYS-8"
        if re.search(r"[-−]\s*y\b|minus\s*y|\-\s*y", n):
            return "SYS-9"
        if re.search(r"[-−]\s*z\b|minus\s*z|\-\s*z", n):
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
