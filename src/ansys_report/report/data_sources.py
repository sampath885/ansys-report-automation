"""Report which context blocks came from live extraction vs fallback fixtures."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig

# section_key → (label, predicate that live data is present)
_DPF_SECTIONS: list[tuple[str, str, Any]] = [
    ("modal", "Modal frequencies", lambda b: any(m.get("freq_hz") is not None for m in b.get("modes", []))),
    ("static", "Static stress (step 3)", lambda b: b.get("max_stress_mpa") is not None),
    ("harmonic_x", "Harmonic X", lambda b: b.get("peak_displacement_mm") is not None),
    ("harmonic_y", "Harmonic Y", lambda b: b.get("peak_displacement_mm") is not None),
    ("harmonic_z", "Harmonic Z", lambda b: b.get("peak_displacement_mm") is not None),
]

_STATIC_BOLT = ("static", "bolt_loads", "Static bolt loads (Table 15)")


def summarize_data_sources(ctx: dict[str, Any], cfg: ProjectConfig) -> list[dict[str, str]]:
    """Return rows describing data origin for each major report block."""
    rows: list[dict[str, str]] = []

    rows.append(
        {
            "block": "Config",
            "status": "policy",
            "source": (
                f"word_table_data={'on' if cfg.use_word_table_data else 'off'}, "
                f"dpf_golden_fallback={'on' if cfg.use_dpf_golden_fallback else 'off'}"
            ),
        }
    )

    for key, label, has_live in _DPF_SECTIONS:
        block = ctx.get(key) or {}
        rows.append(_row_for_block(key, label, block, has_live))

    static = ctx.get("static") or {}
    rows.append(
        _row_for_block(
            "static.bolt_loads",
            _STATIC_BOLT[2],
            static,
            lambda b: bool(b.get("bolt_loads")),
            list_ok=True,
        )
    )

    shock = ctx.get("shock") or {}
    shock_src = shock.get("source")
    directions = shock.get("directions") or []
    filled = sum(1 for d in directions if d.get("max_stress_mpa") is not None)
    rows.append(
        {
            "block": "shock",
            "status": _status(shock_src, filled > 0, filled, len(directions)),
            "source": shock_src or ("dpf" if filled else "missing"),
        }
    )

    if ctx.get("equipment", {}).get("bodies"):
        rows.append({"block": "equipment", "status": "live", "source": "caerep"})
    if ctx.get("modelling", {}).get("node_count") is not None:
        rows.append({"block": "modelling", "status": "live", "source": "caerep/solve.out"})
    if ctx.get("modelling", {}).get("quality_metrics"):
        rows.append({"block": "mesh_quality", "status": "live", "source": "dpf"})
    if ctx.get("loads", {}).get("loads"):
        rows.append({"block": "loads", "status": "live", "source": "caerep"})
    if ctx.get("materials", {}).get("materials"):
        rows.append({"block": "materials", "status": "live", "source": "caerep"})
    if ctx.get("design_calcs"):
        rows.append({"block": "design_calcs", "status": "live", "source": "excel"})

    refs = ctx.get("reference_tables") or {}
    if refs.get("revision_log"):
        src = "word_yaml" if cfg.use_word_table_data else "report_defaults.yaml"
        rows.append({"block": "reference_tables (1–4, 2, 7, 9, 11)", "status": "config", "source": src})
    if refs.get("surface_finish_factors"):
        rows.append({"block": "reference_tables (28–29)", "status": "config", "source": "standards_tables.yaml"})

    return rows


def format_data_sources_report(ctx: dict[str, Any], cfg: ProjectConfig) -> str:
    rows = summarize_data_sources(ctx, cfg)
    lines = ["Data sources:"]
    for row in rows:
        lines.append(f"  {row['block']}: {row['status']} ({row['source']})")
    return "\n".join(lines)


def _row_for_block(
    key: str,
    label: str,
    block: dict[str, Any],
    has_live: Any,
    *,
    list_ok: bool = False,
) -> dict[str, str]:
    explicit = block.get("source")
    if callable(has_live):
        present = bool(has_live(block))
    else:
        value = block.get(has_live)
        present = bool(value) if list_ok else value is not None
    if explicit == "golden":
        source = "golden"
    elif present:
        source = "dpf"
    else:
        source = "missing"
    return {
        "block": key,
        "status": _status(explicit, present),
        "source": source,
    }


def _status(
    explicit: str | None,
    present: bool,
    filled: int | None = None,
    total: int | None = None,
) -> str:
    if explicit == "golden":
        return "fallback"
    if filled is not None and total is not None:
        if filled == 0:
            return "missing"
        if filled < total:
            return f"partial ({filled}/{total})"
        return "live"
    if present:
        return "live"
    return "missing"
