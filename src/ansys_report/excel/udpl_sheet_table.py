"""Extract UDPL valve calculation worksheets as raw tables (no recalculation).

Sheets are pasted into Word with the same column headers and cell values as Excel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Sheets that are reference data, not Section 10 design calculations.
EXCLUDE_SHEET_KEYWORDS: tuple[str, ...] = (
    "bom",
    "material propert",
    "material_properties",
    "basic design",
    "po specification",
    "weight balance",
    "design_specification",
    "design specification",
    "sheet1",
    "surface finish",
    "reliability",
    "bolt loads",
)

# EP1581-style subsection ordering (matched via sheet name + content).
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "pressure_class": ("pressure class", "pressure rating"),
    "wall_thickness": ("wall thickness", "b16", "verification"),
    "lame": ("lamis", "lame", "inner surface", "hoop stress"),
    "union_bolt": ("union flange", "union bolt", "bolt design"),
    "bolt_thread": ("bolt thread", "thread calculation"),
    "bolt_preload": ("pretention", "pretension", "preload", "tightening torque"),
    "flange_rigidity": ("flange rigidity", "flange design", "flange stresses"),
    "effort": ("effort required", "effort calculation", "effort calc"),
    "spindle": ("spindle design", "spindle"),
    "end_connection": ("end connection", "end conn"),
    "spring": ("spring calculation", "disc spring", "bearing_cal"),
    "hub": ("hub thickness",),
}

CATEGORY_ORDER: tuple[str, ...] = tuple(CATEGORY_KEYWORDS.keys()) + ("general",)

IMPLICIT_HEADERS_LAME: tuple[str, ...] = (
    "Sl. No.",
    "IN/OP",
    "Parameter",
    "Value",
    "Unit",
    "Reference",
)

MAX_SCAN_ROWS = 600
EMPTY_ROW_LIMIT = 4


@dataclass
class UdplSheetTable:
    title: str
    sheet_name: str
    category: str
    headers: list[str]
    raw_rows: list[list[str]]
    subtitle: str | None = None


def should_exclude_sheet(sheet_name: str, all_sheet_names: list[str]) -> bool:
    lower = sheet_name.lower().strip()
    if not lower or lower.startswith("_"):
        return True
    if any(token in lower for token in EXCLUDE_SHEET_KEYWORDS):
        return True
    if re.search(r"cn8", lower) and any(re.search(r"2741", name.lower()) for name in all_sheet_names):
        return True
    return False


def classify_sheet(sheet_name: str, preview_text: str) -> str:
    blob = f"{sheet_name.lower()} {preview_text.lower()}"
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in blob)
        if score:
            scores[category] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)


def extract_udpl_sheet_table(ws, *, sheet_name: str) -> UdplSheetTable | None:
    """Return a raw table from a worksheet, or None if not a calculation sheet."""
    matrix = _read_sheet_matrix(ws)
    if not matrix:
        return None

    header_idx = _find_header_row_index(matrix)
    subtitle: str | None = None

    if header_idx is not None:
        if header_idx > 0:
            subtitle = _row_as_title(matrix[header_idx - 1]) or _row_as_title(matrix[0])
        headers = _normalize_headers(matrix[header_idx])
        data_rows = matrix[header_idx + 1 :]
    else:
        lame_start = _find_lame_data_start(matrix)
        if lame_start is None:
            alt = _find_parameter_value_header(matrix)
            if alt is None:
                return None
            header_idx, headers = alt
            if header_idx > 0:
                subtitle = _row_as_title(matrix[header_idx - 1])
            data_rows = matrix[header_idx + 1 :]
        else:
            if lame_start > 0:
                subtitle = _row_as_title(matrix[lame_start - 1]) or _row_as_title(matrix[0])
            headers = list(IMPLICIT_HEADERS_LAME)
            data_rows = matrix[lame_start:]

    raw_rows = _collect_data_rows(data_rows, len(headers))
    if len(raw_rows) < 2:
        return None
    if not _valid_calc_headers(headers):
        return None
    headers, raw_rows = _trim_width(headers, raw_rows)

    preview = " ".join(" ".join(r) for r in raw_rows[:5])
    category = classify_sheet(sheet_name, preview)
    title = _title_from_sheet(sheet_name)
    if subtitle and subtitle.lower() not in title.lower():
        title = subtitle if len(subtitle) > len(title) else title

    return UdplSheetTable(
        title=title,
        sheet_name=sheet_name,
        category=category,
        headers=headers,
        raw_rows=raw_rows,
        subtitle=subtitle,
    )


def sort_tables(tables: list[UdplSheetTable]) -> list[UdplSheetTable]:
    order = {name: idx for idx, name in enumerate(CATEGORY_ORDER)}

    def _key(table: UdplSheetTable) -> tuple[int, str]:
        return (order.get(table.category, len(CATEGORY_ORDER)), table.title.lower())

    return sorted(tables, key=_key)


def _read_sheet_matrix(ws) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    for row in ws.iter_rows(max_row=MAX_SCAN_ROWS, values_only=True):
        rows.append(tuple(row))
    return rows


def _normalize_header_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _normalize_headers(row: tuple[Any, ...]) -> list[str]:
    headers: list[str] = []
    for cell in row:
        text = _normalize_header_text(cell)
        if text:
            headers.append(text)
    if not headers:
        return ["Parameter", "Value"]
    return headers


def _valid_calc_headers(headers: list[str]) -> bool:
    lowered = [h.lower() for h in headers if h]
    if not lowered:
        return False
    if not any("parameter" in h for h in lowered):
        return False
    if any(len(h) > 100 for h in headers if h):
        return False
    return True


def _trim_width(headers: list[str], raw_rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    width = len(headers)
    while width > 2:
        if headers[width - 1]:
            break
        if any(len(row) >= width and row[width - 1].strip() for row in raw_rows):
            break
        width -= 1
    headers = headers[:width]
    trimmed = [row[:width] for row in raw_rows]
    return headers, trimmed


def _find_header_row_index(matrix: list[tuple[Any, ...]]) -> int | None:
    for idx, row in enumerate(matrix[:40]):
        if _is_calc_header_row(row):
            headers = _normalize_headers(row)
            if _valid_calc_headers(headers):
                return idx
    return None


def _is_calc_header_row(row: tuple[Any, ...]) -> bool:
    texts = [_normalize_header_text(c).lower() for c in row if c is not None]
    if not texts:
        return False
    blob = " ".join(texts)
    if "parameter" in blob and ("value" in blob or "in/op" in blob or "in / op" in blob):
        return True
    if ("sl. no" in blob or "sr. no" in blob or "sl no" in blob) and "parameter" in blob:
        return True
    if blob.count("parameter") and ("unit" in blob or "reference" in blob or "referance" in blob):
        return True
    return False


def _find_lame_data_start(matrix: list[tuple[Any, ...]]) -> int | None:
    """Rows like: 1 | Input | Internal Body Test Pressure | 8 | MPa | PO."""
    for idx, row in enumerate(matrix[:80]):
        if _row_has_inop(row):
            return idx
    return None


def _row_has_inop(row: tuple[Any, ...]) -> bool:
    for cell in row[:8]:
        if cell is None:
            continue
        token = str(cell).strip().upper()
        if token in ("INPUT", "OUTPUT", "INPUT ", "OUTPUT "):
            return True
    return False


def _find_parameter_value_header(matrix: list[tuple[Any, ...]]) -> tuple[int, list[str]] | None:
    """Sheets with Parameter | Unit | Value | Source header (no IN/OP)."""
    for idx, row in enumerate(matrix[:25]):
        texts = [_normalize_header_text(c).lower() for c in row]
        if "parameter" in texts and "value" in texts:
            return idx, _normalize_headers(row)
    return None


def _collect_data_rows(rows: list[tuple[Any, ...]], num_cols: int) -> list[list[str]]:
    out: list[list[str]] = []
    empty_streak = 0
    for row in rows:
        if _is_empty_row(row):
            empty_streak += 1
            if empty_streak >= EMPTY_ROW_LIMIT:
                break
            continue
        empty_streak = 0
        if not _is_data_row(row):
            continue
        out.append(_format_row(row, num_cols))
    return out


def _is_empty_row(row: tuple[Any, ...]) -> bool:
    return all(c is None or str(c).strip() == "" for c in row)


def _is_data_row(row: tuple[Any, ...]) -> bool:
    if _is_empty_row(row):
        return False
    non_empty = [c for c in row if c is not None and str(c).strip()]
    if len(non_empty) < 2:
        return False
    first = _normalize_header_text(non_empty[0]).lower()
    if first in ("parameter", "sl. no.", "sr. no", "sl no", "sr no"):
        return False
    return True


def _format_row(row: tuple[Any, ...], num_cols: int) -> list[str]:
    cells = [_format_cell(c) for c in row[:num_cols]]
    while len(cells) < num_cols:
        cells.append("")
    return cells


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value)) if value == int(value) else str(value)
        text = f"{value:.10g}"
        return text
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _row_as_title(row: tuple[Any, ...]) -> str | None:
    parts = [_normalize_header_text(c) for c in row if c is not None and str(c).strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    joined = " ".join(parts[:3])
    if _row_has_inop(row):
        return None
    if any(k in joined.lower() for k in ("input", "output", "parameter", "sl. no")):
        return None
    if len(joined) > 120:
        return joined[:120]
    return joined if len(joined) > 8 else None


def _title_from_sheet(sheet_name: str) -> str:
    text = re.sub(r"_2741$|_cn8$", "", sheet_name, flags=re.I)
    text = re.sub(r"[_\-]+", " ", text.strip())
    return re.sub(r"\s+", " ", text).strip()
