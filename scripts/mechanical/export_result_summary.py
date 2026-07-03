# -*- coding: utf-8 -*-
"""
Export Solution Information -> Result Summary from ANSYS Mechanical.

RUN INSIDE MECHANICAL (Automation -> Scripting -> Open -> Run):
  exports/result_summaries/<analysis>.json + manifest.json

Strategies (first non-empty wins, then merged):
  1) Worksheet / DataGrid in the center pane (Result Summary table)
  2) TabularData pane (1-based cell indexing)
  3) Solution result objects (.Minimum / .Maximum on deformation & stress)

Set DEBUG_TABLE = True to print pane/grid diagnostics in the Mechanical shell.
Set OUTPUT_ROOT to your case exports folder if auto-detect lands in Temp.
"""

from __future__ import print_function

import json
import os
import re
import time

DEBUG_TABLE = False
OUTPUT_ROOT = None
SETTLE_S = 0.25

STEM_TO_SYSTEM_KEY = {
    "static_structural": "static_structural",
    "modal": "modal",
    "modal_analysis": "modal",
    "vibration_resistance_analysis_x": "vibration_x",
    "vibration_resistance_analysis_y": "vibration_y",
    "vibration_resistance_analysis_z": "vibration_z",
    "equivalent_static_analysis_posx": "shock_plus_x",
    "equivalent_static_analysis_posy": "shock_plus_y",
    "equivalent_static_analysis_posz": "shock_plus_z",
    "equivalent_static_analysis_negx": "shock_minus_x",
    "equivalent_static_analysis_negy": "shock_minus_y",
    "equivalent_static_analysis_negz": "shock_minus_z",
}

_ASSEMBLY_DEFORM = ("total deformation",)
_ASSEMBLY_STRESS = (
    "equivalent stress",
    "equivalent von-mises stress",
    "von mises stress",
    "von-mises stress",
)


def _safe_str(text):
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
    import __builtin__ as _builtins  # type: ignore[no-redef]


def print(*args, **kwargs):  # noqa: A001
    if args:
        args = tuple(_safe_str(a) for a in args)
    _builtins.print(*args, **kwargs)


class ExportError(Exception):
    pass


def main():
    try:
        return _main_impl()
    except ExportError:
        return 1


def _main_impl():
    _require_mechanical()
    model = ExtAPI.DataModel.Project.Model  # noqa: F821

    output_root = _resolve_output_root()
    summary_dir = os.path.join(output_root, "result_summaries")
    if not os.path.isdir(summary_dir):
        os.makedirs(summary_dir)

    project_dir = _get_project_directory()
    print("Result Summary Export")
    print("Project: %s" % project_dir)
    print("Output : %s" % summary_dir)
    if project_dir and "local\\temp" in project_dir.replace("/", "\\").lower():
        print("")
        print("WARNING: Project folder resolved to Temp (Mechanical cwd).")
        print("         Set OUTPUT_ROOT at top of script to your case exports folder.")
        print("         Example: OUTPUT_ROOT = r'F:\\...\\EP_2741\\exports'")
    print("")

    analyses = _get_all_analyses(model)
    if not analyses:
        _fail("No analyses found in this Mechanical session.")

    manifest = {
        "version": 1,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summaries": [],
    }
    ok = 0

    for analysis in analyses:
        if _is_suppressed(analysis):
            continue
        a_name = _node_name(analysis)
        stem = _sanitize_filename(a_name)
        system_key = _map_analysis_to_system_key(a_name)
        folder = _map_analysis_to_folder(a_name, system_key)

        sol = _find_solution_node(analysis)
        if sol is None:
            print("SKIP %s (no Solution)" % a_name)
            continue

        sol_info = _find_solution_information(sol)
        out_file = os.path.join(summary_dir, stem + ".json")
        try:
            payload, source = _export_result_summary(analysis, sol, sol_info, system_key, folder)
            with open(out_file, "w") as fh:
                json.dump(payload, fh, indent=2)
            manifest["summaries"].append(
                {
                    "analysis_name": a_name,
                    "file": stem + ".json",
                    "system_key": system_key,
                    "workbench_folder": folder,
                    "source": source,
                }
            )
            ok += 1
            print("OK   %s -> %s (%s) [%s, %d rows]" % (a_name, out_file, system_key or "?", source, len(payload.get("rows") or [])))
        except Exception as exc:
            print("ERR  %s (%s)" % (a_name, _safe_str(exc)))

    manifest_path = os.path.join(summary_dir, "manifest.json")
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    print("")
    print("=" * 60)
    print("Exported %d Result Summary file(s)." % ok)
    print("Manifest: %s" % manifest_path)
    if ok == 0:
        print("")
        print("TIP: Set DEBUG_TABLE = True at top of script and re-run.")
        print("TIP: Set OUTPUT_ROOT = r'F:\\...\\exports' if output is in Temp.")
    print("=" * 60)
    return 0


def _export_result_summary(analysis, sol, sol_info, system_key, folder):
    _prepare_solution_view(sol, sol_info)

    rows = []
    source = "unknown"

    ws_rows, ws_note = _read_worksheet_result_summary()
    if ws_rows:
        rows = ws_rows
        source = "worksheet_" + ws_note

    if not rows:
        tab_rows = _read_tabular_data_rows()
        if tab_rows:
            rows = tab_rows
            source = "tabular_data"

    api_rows = _collect_from_solution_results(sol, analysis=analysis, system_key=system_key)
    if api_rows:
        if rows:
            rows = _merge_rows(rows, api_rows)
            if source == "unknown":
                source = "solution_api"
            else:
                source = source + "+api"
        else:
            rows = api_rows
            source = "solution_api"

    if not rows:
        raise RuntimeError("Result Summary table is empty (worksheet + API)")

    time_s = None
    for row in rows:
        if row.get("time_s") is not None:
            time_s = row["time_s"]

    return (
        {
            "analysis_name": _node_name(analysis),
            "system_key": system_key,
            "workbench_folder": folder,
            "time_s": time_s,
            "rows": rows,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "extraction_source": source,
        },
        source,
    )


def _prepare_solution_view(sol, sol_info):
    """Activate Solution (+ Solution Information) before reading grids or result API."""
    _activate(sol)
    if sol_info is not None:
        _activate(sol_info)
    _evaluate_solution(sol)
    _ensure_worksheet_visible()
    if SETTLE_S > 0:
        time.sleep(SETTLE_S)
    try:
        ExtAPI.Graphics.Refresh()  # noqa: F821
    except Exception:
        pass


def _read_worksheet_result_summary():
    """Read center Worksheet grid (Result Summary table)."""
    notes = []

    grid_rows = _read_worksheet_datagrid()
    if grid_rows:
        parsed = _parse_grid_rows(grid_rows)
        if parsed:
            return parsed, "datagrid"

    if DEBUG_TABLE:
        print("  [debug] worksheet strategies found no parseable rows")
    return [], ""


def _read_worksheet_datagrid():
    try:
        pane = ExtAPI.UserInterface.GetPane(MechanicalPanelEnum.Worksheet)  # noqa: F821
    except Exception:
        return []
    if pane is None:
        return []

    root = getattr(pane, "Control", None) or getattr(pane, "ControlUnknown", None)
    if root is None:
        return []

    collected = []
    for grid in _walk_controls(root):
        type_name = grid.GetType().Name
        if "DataGrid" not in type_name and "Grid" not in type_name:
            continue
        try:
            row_count = int(getattr(grid, "RowCount", 0) or 0)
            col_count = int(getattr(grid, "ColumnCount", 0) or 0)
        except Exception:
            continue
        if row_count <= 0 or col_count <= 0:
            continue

        if DEBUG_TABLE:
            print("  [debug] grid %s %dx%d" % (type_name, row_count, col_count))

        table = []
        for r in range(row_count):
            line = []
            for c in range(col_count):
                try:
                    cell = grid.Rows[r].Cells[c]
                    val = cell.Value
                    if val is None:
                        val = cell.FormattedValue
                    line.append(_safe_str(val).strip())
                except Exception:
                    line.append("")
            if any(line):
                table.append(line)
        if table:
            collected.append(table)

    if not collected:
        return []

    # Pick the grid that looks most like Result Summary (has Results / Maximum headers).
    best = []
    best_score = -1
    for table in collected:
        score = _score_summary_grid(table)
        if score > best_score:
            best_score = score
            best = table
    return best


def _read_tabular_data_rows():
    """TabularData uses 1-based row/column indexing."""
    try:
        pane = ExtAPI.UserInterface.GetPane(MechanicalPanelEnum.TabularData)  # noqa: F821
    except Exception:
        return []
    if pane is None:
        return []

    table = getattr(pane, "ControlUnknown", None)
    if table is None:
        return []

    n_rows = _table_rows(table)
    n_cols = _table_cols(table)
    if DEBUG_TABLE:
        print("  [debug] TabularData %dx%d" % (n_rows, n_cols))
    if n_rows <= 0 or n_cols <= 0:
        return []

    grid = []
    for r in range(1, n_rows + 1):
        line = []
        for c in range(1, n_cols + 1):
            line.append(_cell_text(table, r, c).strip())
        if any(line):
            grid.append(line)

    return _parse_grid_rows(grid)


def _parse_grid_rows(grid):
    if not grid:
        return []

    header_row = -1
    col_map = {}
    for ri, row in enumerate(grid[:20]):
        labels = [c.lower() for c in row]
        joined = " ".join(labels)
        if "results" in labels or ("minimum" in joined and "maximum" in joined):
            header_row = ri
            for ci, label in enumerate(labels):
                if label.startswith("result"):
                    col_map["result"] = ci
                elif label.startswith("min"):
                    col_map["minimum"] = ci
                elif label.startswith("max"):
                    col_map["maximum"] = ci
                elif label.startswith("u") and "unit" not in col_map:
                    col_map["unit"] = ci
                elif "time" in label:
                    col_map["time_s"] = ci
            break

    if header_row < 0:
        if len(grid[0]) >= 3:
            col_map = {"result": 0, "minimum": 1, "maximum": 2, "unit": 3, "time_s": 4}
            header_row = -1
        else:
            return []

    rows = []
    for row in grid[header_row + 1 :]:
        if not row or not any(row):
            continue
        result = _pick_cell(row, col_map.get("result", 0))
        if not result:
            continue
        rows.append(
            {
                "result": result,
                "minimum": _parse_number(_pick_cell(row, col_map.get("minimum", 1))),
                "maximum": _parse_number(_pick_cell(row, col_map.get("maximum", 2))),
                "unit": _pick_cell(row, col_map.get("unit", 3)) or None,
                "time_s": _parse_number(_pick_cell(row, col_map.get("time_s", 4))),
            }
        )
    return rows


def _pick_cell(row, idx):
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _score_summary_grid(grid):
    score = 0
    for row in grid[:5]:
        blob = " ".join(row).lower()
        if "result" in blob:
            score += 5
        if "maximum" in blob:
            score += 3
        if "minimum" in blob:
            score += 2
        if "deformation" in blob or "stress" in blob:
            score += 4
    return score


def _is_modal_analysis(analysis, system_key=None):
    if system_key == "modal":
        return True
    if analysis is None:
        return False
    name = _node_name(analysis).lower()
    if "modal" in name:
        return True
    try:
        return "Modal" in analysis.GetType().Name
    except Exception:
        return False


def _collect_from_solution_results(sol, analysis=None, system_key=None):
    """Fallback: read .Minimum / .Maximum from Solution result objects."""
    if _is_modal_analysis(analysis, system_key):
        modal_rows = _collect_modal_rows(sol, analysis)
        if modal_rows:
            return modal_rows

    _activate(sol)
    _evaluate_solution(sol)

    candidates = []
    for child in _walk_tree(sol):
        if _is_suppressed(child):
            continue
        name = _node_name(child)
        lname = name.lower().strip()
        if not name or lname == "solution information":
            continue
        tname = _node_type_name(child).lower()
        if any(k in tname for k in ("chart", "tracker", "figure", "image", "information")):
            continue
        if any(k in lname for k in ("chart", "tracker", "convergence", "information")):
            continue

        try:
            _activate(child)
        except Exception:
            pass

        min_v, max_v, unit, time_s = _read_result_min_max(child)
        if max_v is None and min_v is None:
            continue

        candidates.append(
            {
                "result": name,
                "minimum": min_v,
                "maximum": max_v,
                "unit": unit,
                "time_s": time_s,
                "lname": lname,
            }
        )

    if not candidates:
        return []

    rows = []
    deform = _pick_best_candidate(candidates, _ASSEMBLY_DEFORM)
    if deform:
        rows.append(_row_from_candidate(deform, "Total Deformation"))

    stress = _pick_best_candidate(candidates, _ASSEMBLY_STRESS)
    if stress:
        rows.append(_row_from_candidate(stress, "Equivalent Stress"))

    for item in candidates:
        lname = item["lname"]
        if item is deform or item is stress:
            continue
        if "stress" not in lname and (not item.get("unit") or "mpa" not in item["unit"].lower()):
            continue
        if any(k in lname for k in ("flange", "scope", "probe", "tool")):
            continue
        rows.append(_row_from_candidate(item, item["result"]))

    if not rows and candidates:
        for item in candidates:
            rows.append(_row_from_candidate(item, item["result"]))

    return rows


def _collect_modal_rows(sol, analysis):
    """Modal: iterate modes on deformation results and read frequency / deformation."""
    _activate(sol)
    _evaluate_solution(sol)

    deform_nodes = []
    for child in _walk_tree(sol):
        if _is_suppressed(child):
            continue
        lname = _node_name(child).lower()
        tname = _node_type_name(child).lower()
        if "deformation" not in lname:
            continue
        if any(k in tname for k in ("chart", "tracker", "figure", "image")):
            continue
        if any(k in lname for k in ("chart", "tracker")):
            continue
        deform_nodes.append(child)

    if not deform_nodes:
        return _collect_modal_from_tabular(sol)

    rows = []
    seen_modes = set()
    for node in deform_nodes[:3]:
        for mode in range(1, 25):
            if not _try_set_mode(node, mode):
                if mode > 1:
                    break
                continue
            try:
                _activate(node)
            except Exception:
                pass

            freq = _read_result_frequency(node)
            min_v, max_v, unit, _ = _read_result_min_max(node)
            if freq is None and max_v is None and min_v is None:
                if mode > 1:
                    break
                continue
            if mode in seen_modes:
                continue
            seen_modes.add(mode)

            if freq is not None:
                rows.append(
                    {
                        "result": "Mode %d Frequency" % mode,
                        "minimum": None,
                        "maximum": freq,
                        "unit": "Hz",
                        "time_s": None,
                    }
                )
            if max_v is not None or min_v is not None:
                rows.append(
                    {
                        "result": "Mode %d Total Deformation" % mode,
                        "minimum": min_v,
                        "maximum": max_v,
                        "unit": unit or "mm",
                        "time_s": None,
                    }
                )

    if rows:
        return rows
    return _collect_modal_from_tabular(sol)


def _collect_modal_from_tabular(sol):
    """Try TabularData after activating Solution (modal frequency table)."""
    sol_info = _find_solution_information(sol)
    if sol_info is not None:
        try:
            _activate(sol_info)
        except Exception:
            pass
    grid = []
    try:
        pane = ExtAPI.UserInterface.GetPane(MechanicalPanelEnum.TabularData)  # noqa: F821
        table = pane.ControlUnknown if pane else None
        if table is not None:
            n_rows = _table_rows(table)
            n_cols = _table_cols(table)
            for r in range(1, n_rows + 1):
                line = [_cell_text(table, r, c).strip() for c in range(1, n_cols + 1)]
                if any(line):
                    grid.append(line)
    except Exception:
        pass

    rows = []
    for line in grid:
        joined = " ".join(line).lower()
        if "frequency" in joined or "mode" in joined:
            freq = None
            for cell in line:
                val = _parse_number(cell)
                if val is not None and val > 1:
                    freq = val
                    break
            if freq is not None:
                label = line[0] if line else "Mode"
                rows.append(
                    {
                        "result": label,
                        "minimum": None,
                        "maximum": freq,
                        "unit": "Hz",
                        "time_s": None,
                    }
                )
    return rows


def _try_set_mode(result_obj, mode):
    for method in ("SetMode", "SetResultMode"):
        try:
            getattr(result_obj, method)(int(mode))
            return True
        except Exception:
            pass
    try:
        result_obj.Mode = int(mode)
        return True
    except Exception:
        return False


def _read_result_frequency(obj):
    for attr in ("Frequency", "ResultFrequency", "ModeFrequency", "ModalFrequency"):
        try:
            val = _quantity_number(getattr(obj, attr))
            if val is not None and val > 0:
                return val
        except Exception:
            pass
    return None


def _pick_best_candidate(candidates, keywords):
    best = None
    best_score = -1
    for item in candidates:
        lname = item["lname"]
        score = 0
        for kw in keywords:
            if kw in lname:
                score += 10
        if item.get("maximum") is not None:
            score += 2
        if score > best_score:
            best_score = score
            best = item
    return best if best_score > 0 else None


def _row_from_candidate(item, label):
    return {
        "result": label,
        "minimum": item.get("minimum"),
        "maximum": item.get("maximum"),
        "unit": item.get("unit"),
        "time_s": item.get("time_s"),
    }


def _read_result_min_max(obj):
    min_v = None
    max_v = None
    unit = None
    time_s = None

    min_attrs = (
        "Minimum",
        "MinimumOfMinimumOverTime",
        "MinimumPrincipal",
    )
    max_attrs = (
        "Maximum",
        "MaximumOfMaximumOverTime",
        "MaximumPrincipal",
    )

    for ma in max_attrs:
        try:
            prop = getattr(obj, ma)
            max_v = _quantity_number(prop)
            unit = unit or _quantity_unit(prop)
        except Exception:
            pass
        if max_v is not None:
            break

    for ma in min_attrs:
        try:
            prop = getattr(obj, ma)
            min_v = _quantity_number(prop)
            unit = unit or _quantity_unit(prop)
        except Exception:
            pass
        if min_v is not None:
            break

    for ta in ("Time", "ResultTime", "LastTime"):
        try:
            prop = getattr(obj, ta)
            time_s = _quantity_number(prop)
        except Exception:
            pass

    return min_v, max_v, unit, time_s


def _quantity_number(prop):
    if prop is None:
        return None
    for attr in ("Value", "NumericValue"):
        try:
            val = getattr(prop, attr)
            if val is not None:
                return float(val)
        except Exception:
            pass
    try:
        return float(prop)
    except Exception:
        return None


def _quantity_unit(prop):
    if prop is None:
        return None
    for attr in ("Unit", "Units"):
        try:
            val = getattr(prop, attr)
            if val:
                return _safe_str(val)
        except Exception:
            pass
    return None


def _merge_rows(primary, secondary):
    """Keep primary rows; add secondary rows for missing result labels."""
    seen = set()
    merged = []
    for row in primary:
        key = row.get("result", "").lower().strip()
        seen.add(key)
        merged.append(row)
    for row in secondary:
        key = row.get("result", "").lower().strip()
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _walk_controls(root):
    """Depth-first walk of WinForms controls."""
    stack = [root]
    seen = set()
    while stack:
        ctrl = stack.pop()
        try:
            cid = id(ctrl)
        except Exception:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        yield ctrl
        try:
            count = int(ctrl.Controls.Count)
        except Exception:
            continue
        for i in range(count):
            try:
                stack.append(ctrl.Controls[i])
            except Exception:
                pass


def _evaluate_solution(sol):
    for meth in ("EvaluateAllResults", "Evaluate"):
        try:
            getattr(sol, meth)()
            return
        except Exception:
            pass


def _table_rows(table):
    for attr in ("RowsCount", "RowCount"):
        try:
            return int(getattr(table, attr))
        except Exception:
            pass
    return 0


def _table_cols(table):
    for attr in ("ColumnsCount", "ColumnCount"):
        try:
            return int(getattr(table, attr))
        except Exception:
            pass
    return 0


def _cell_text(table, row, col):
    for meth in ("cell", "Cell"):
        try:
            fn = getattr(table, meth)
            cell = fn(int(row), int(col))
            for prop in ("Text", "Value", "Content"):
                try:
                    val = getattr(cell, prop)
                    if val is not None:
                        return _safe_str(val)
                except Exception:
                    pass
            return _safe_str(cell)
        except Exception:
            pass
    return ""


def _parse_number(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _find_solution_information(sol_node):
    try:
        info = sol_node.SolutionInformation
        if info is not None:
            return info
    except Exception:
        pass
    for child in _iter_children(sol_node):
        name = _node_name(child).lower()
        tname = _node_type_name(child).replace(" ", "").lower()
        if name == "solution information" or "solutioninformation" in tname:
            return child
    return None


def _find_solution_node(analysis):
    try:
        sol = analysis.Solution
        if sol is not None:
            return sol
    except Exception:
        pass
    for child in _iter_children(analysis):
        if _node_name(child).lower() == "solution":
            return child
    return None


def _get_all_analyses(model):
    analyses = []
    try:
        for a in model.Analyses:
            if not _is_suppressed(a):
                analyses.append(a)
        if analyses:
            return analyses
    except Exception:
        pass
    for node in _walk_tree(model):
        tname = _node_type_name(node)
        if "Analysis" in tname and "Settings" not in tname and "Information" not in tname:
            if not _is_suppressed(node):
                analyses.append(node)
    return analyses


def _map_analysis_to_system_key(label):
    if not label:
        return None
    stem = _sanitize_filename(label)
    if stem in STEM_TO_SYSTEM_KEY:
        return STEM_TO_SYSTEM_KEY[stem]
    mapped = _map_analysis_label_to_sys(label)
    if mapped:
        folder_map = {
            "SYS": "static_structural",
            "SYS-1": "modal",
            "SYS-2": "vibration_x",
            "SYS-3": "vibration_y",
            "SYS-4": "vibration_z",
            "SYS-5": "shock_plus_x",
            "SYS-6": "shock_plus_y",
            "SYS-7": "shock_plus_z",
            "SYS-8": "shock_minus_x",
            "SYS-9": "shock_minus_y",
            "SYS-10": "shock_minus_z",
        }
        return folder_map.get(mapped)
    return None


def _map_analysis_to_folder(label, system_key):
    if system_key:
        rev = {
            "static_structural": "SYS",
            "modal": "SYS-1",
            "vibration_x": "SYS-2",
            "vibration_y": "SYS-3",
            "vibration_z": "SYS-4",
            "shock_plus_x": "SYS-5",
            "shock_plus_y": "SYS-6",
            "shock_plus_z": "SYS-7",
            "shock_minus_x": "SYS-8",
            "shock_minus_y": "SYS-9",
            "shock_minus_z": "SYS-10",
        }
        return rev.get(system_key)
    return _map_analysis_label_to_sys(label)


def _map_analysis_label_to_sys(label):
    if not label:
        return None
    n = label.lower().strip()
    if "static structural" in n:
        return "SYS"
    if re.search(r"\bmodal\b", n):
        return "SYS-1"
    if "harmonic" in n or "vibration" in n:
        if "x direction" in n or re.search(r"\bx\b", n) or "_x" in n or "posx" in n or "negx" in n:
            return "SYS-2" if "neg" not in n and "minus" not in n and "-x" not in n else "SYS-8"
        if "y direction" in n or re.search(r"\by\b", n) or "_y" in n or "posy" in n or "negy" in n:
            return "SYS-3" if "neg" not in n and "minus" not in n and "-y" not in n else "SYS-9"
        if "z direction" in n or re.search(r"\bz\b", n) or "_z" in n or "posz" in n or "negz" in n:
            return "SYS-4" if "neg" not in n and "minus" not in n and "-z" not in n else "SYS-10"
        if "posx" in n or "plus_x" in n:
            return "SYS-2"
        if "posy" in n:
            return "SYS-3"
        if "posz" in n:
            return "SYS-4"
        if "negx" in n or "minus_x" in n:
            return "SYS-8"
        if "negy" in n or "minus_y" in n:
            return "SYS-9"
        if "negz" in n or "minus_z" in n:
            return "SYS-10"
    if "shock" in n or "equivalent static" in n:
        if re.search(r"posx|plus.?x|\+.?x", n):
            return "SYS-5"
        if re.search(r"posy|plus.?y|\+.?y", n):
            return "SYS-6"
        if re.search(r"posz|plus.?z|\+.?z", n):
            return "SYS-7"
        if re.search(r"negx|minus.?x|-.?x", n):
            return "SYS-8"
        if re.search(r"negy|minus.?y|-.?y", n):
            return "SYS-9"
        if re.search(r"negz|minus.?z|-.?z", n):
            return "SYS-10"
    return None


def _ensure_worksheet_visible():
    try:
        jscript = ExtAPI.Application.ScriptByName("jscript")  # noqa: F821
        jscript.ExecuteCommand(
            "if (!DS.Script.isWorksheetWindowActive()) "
            "DS.Script.toggleWorksheetVisibility();"
        )
    except Exception:
        pass


def _sanitize_filename(name):
    s = _safe_str(name).strip().lower()
    s = re.sub(r"[^\w.\-]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] or "unnamed"


_WB_FILES_DP0_RE = re.compile(r"^(.*)[\\/][^\\/]+_files[\\/]dp0", re.IGNORECASE)
_WB_MECH_PATH_RE = re.compile(
    r"^(.*)[\\/][^\\/]+_files[\\/]dp0[\\/]SYS(?:-\d+)?[\\/]MECH",
    re.IGNORECASE,
)


def _is_repo_script_dir(path):
    norm = os.path.normpath(path).replace("\\", "/").lower()
    return norm.endswith("/scripts/mechanical")


def _looks_like_case_folder(folder):
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
    if not raw_path:
        return None
    norm = str(raw_path).replace("/", "\\")
    match = _WB_FILES_DP0_RE.search(norm)
    if match:
        return os.path.normpath(match.group(1))
    if norm.lower().endswith(".wbpj"):
        return os.path.dirname(norm)
    if os.path.isdir(norm) and _looks_like_case_folder(norm):
        return norm
    parent = os.path.dirname(norm)
    return parent or None


def _mech_project_folder(raw_path):
    if not raw_path:
        return None
    norm = str(raw_path).replace("/", "\\")
    match = _WB_MECH_PATH_RE.search(norm)
    if match:
        return os.path.normpath(match.group(1))
    return _folder_from_workbench_path(raw_path)


def _case_folder_from_script():
    script = _script_dir()
    if not script or _is_repo_script_dir(script):
        return None
    folder = os.path.normpath(script)
    return folder


def _project_path_candidates():
    """Workbench paths; prefer dp0/SYS*/MECH paths over cwd (often Temp)."""
    candidates = []
    try:
        project = ExtAPI.DataModel.Project  # noqa: F821
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
                val = getattr(project, prop, None)
                if val:
                    candidates.append(val)
            except Exception:
                pass
    except Exception:
        pass
    script = _script_dir()
    if script:
        candidates.append(script)
    try:
        candidates.append(os.getcwd())
    except Exception:
        pass

    mech_first = []
    other = []
    seen = set()
    _WB_SYS_MECH_RE = re.compile(r"[\\/]dp0[\\/](SYS(?:-\d+)?)[\\/]MECH", re.IGNORECASE)
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


def _collect_mech_project_folders():
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


def _resolve_project_folder():
    script_folder = _case_folder_from_script()
    if script_folder:
        return script_folder
    mech_folders = _collect_mech_project_folders()
    if len(mech_folders) == 1:
        return mech_folders[0]
    if mech_folders:
        return mech_folders[0]
    for raw in _project_path_candidates():
        folder = _folder_from_workbench_path(raw)
        if folder:
            return folder
    return None


def _resolve_output_root():
    if OUTPUT_ROOT:
        return os.path.normpath(OUTPUT_ROOT)
    folder = _resolve_project_folder()
    if folder:
        return os.path.join(folder, "exports")
    return os.path.join(os.getcwd(), "exports")


def _get_project_directory():
    folder = _resolve_project_folder()
    if folder:
        return folder
    for raw in _project_path_candidates():
        if raw:
            return str(raw)
    return "?"


def _script_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return None


def _node_type_name(node):
    try:
        return node.GetType().Name or ""
    except Exception:
        return ""


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


def _is_suppressed(node):
    current = node
    for _ in range(50):
        if current is None:
            break
        try:
            if bool(current.Suppressed):
                return True
        except Exception:
            pass
        try:
            current = current.Parent
        except Exception:
            break
    return False


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


def _require_mechanical():
    try:
        ExtAPI  # noqa: F821
    except NameError:
        print("ERROR: Run this script inside ANSYS Mechanical.")
        raise ExportError("ExtAPI not available")


def _fail(message):
    print("ERROR: " + message)
    raise ExportError(message)


try:
    main()
except ExportError:
    pass
except SystemExit:
    pass
