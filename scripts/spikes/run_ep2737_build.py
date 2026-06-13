"""Phase 6 build spike — first EP2737 DOCX from real metadata, Excel, and DPF/golden."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "config" / "project.ep2737.yaml"
OUTPUT = REPO / "output" / "EP_2737_report.docx"


def run_build(
    *,
    config: Path | None = None,
    golden_dpf: bool = False,
    out: Path | None = None,
    pdf: bool = False,
) -> int:
    from ansys_report.config import load_project_config, validate_project_paths
    from ansys_report.report.context_builder import build_context
    from ansys_report.report.ep2737_overlay import apply_golden_dpf_overlay, needs_golden_overlay
    from ansys_report.scanner import scan_project

    cfg = load_project_config(config or CONFIG)
    tpl = cfg.template_path
    if tpl is None or not tpl.exists():
        from ansys_report.report.template_builder import create_ep2737_template

        tpl = REPO / "templates" / "EP2737_report_template.docx"
        create_ep2737_template(tpl)

    inventory = scan_project(
        cfg.project_dir,
        cfg.image_folder,
        cfg.excel_calcs,
        case_root=cfg.case_root,
        excel_bolt_preload=cfg.excel_bolt_preload,
    )
    validation = validate_project_paths(cfg)

    dpf_keys = {"modal", "static", "harmonic_x", "harmonic_y", "harmonic_z", "shock"}
    saved_sections = None
    if golden_dpf:
        saved_sections = list(cfg.sections_enabled)
        cfg.sections_enabled = [s for s in saved_sections if s not in dpf_keys]

    ctx, build_val = build_context(cfg, inventory=inventory, use_ai=False)
    validation.merge(build_val)

    if golden_dpf and saved_sections:
        cfg.sections_enabled = saved_sections

    from ansys_report.report.render import render_report

    if golden_dpf or (cfg.use_dpf_golden_fallback and needs_golden_overlay(ctx)):
        apply_golden_dpf_overlay(ctx, cfg, force=golden_dpf)
    elif cfg.use_dpf_golden_fallback:
        apply_golden_dpf_overlay(ctx, cfg, force=False)

    dest = out or OUTPUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    render_report(tpl, ctx, dest, cfg=cfg)

    if pdf:
        from ansys_report.report.pdf import convert_to_pdf, pdf_available

        if pdf_available():
            pdf_path = convert_to_pdf(dest)
            if pdf_path:
                print(f"PDF written: {pdf_path}")
        else:
            print("PDF skipped (install docx2pdf + Word, or LibreOffice)")

    print(f"Report written: {dest}")
    print(f"Config: {config or CONFIG}")
    print(f"reference_front_matter: {cfg.use_reference_front_matter}")
    print(f"BOM: {ctx['bom_id']} — {ctx['title']}")
    if ctx.get("modal", {}).get("modes"):
        m1 = ctx["modal"]["modes"][0]
        print(f"Mode 1: {m1.get('freq_hz', '?'):.3f} Hz" if m1.get("freq_hz") else "Mode 1: n/a")
    static = ctx.get("static", {})
    if static.get("max_stress_mpa") is not None:
        print(
            f"Static step 3: {static['max_stress_mpa']:.1f} MPa, "
            f"{static.get('max_deformation_mm', 0):.3f} mm"
        )
    effort = ctx.get("design_calcs", {}).get("effort", [])
    preload = next((r for r in effort if "preload" in r.get("label", "").lower()), None)
    if preload:
        print(f"Preload: {preload['value']} N")

    from ansys_report.report.data_sources import format_data_sources_report

    print(format_data_sources_report(ctx, cfg))

    if validation.has_errors:
        print("Validation errors present — review before issue")
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EP2737 Phase 6 report build")
    parser.add_argument("--config", type=Path, default=CONFIG, help="Project config YAML")
    parser.add_argument("--golden-dpf", action="store_true", help="CI only: overlay test golden JSON when DPF unavailable")
    parser.add_argument("--pdf", action="store_true", help="Export PDF after DOCX")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    return run_build(
        config=args.config,
        golden_dpf=args.golden_dpf,
        out=args.out,
        pdf=args.pdf,
    )


if __name__ == "__main__":
    sys.exit(main())
