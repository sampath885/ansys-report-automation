"""Initialize per-job project config from Workbench scan + CAERep."""

from __future__ import annotations

import argparse
from pathlib import Path

from ansys_report.project_init import ProjectInitError, discover_project_facts, init_project_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold config/project.<bom>.yaml and report defaults from a Workbench tree.",
    )
    parser.add_argument("--bom-id", required=True, help='BOM id, e.g. "EP 2737"')
    parser.add_argument("--title", required=True, help="Report title / equipment name")
    parser.add_argument("--project-dir", type=Path, required=True, help="Workbench project folder")
    parser.add_argument("--case-root", type=Path, default=None, help="Case folder (Excel, STEP, exports)")
    parser.add_argument("--customer", default="Customer name")
    parser.add_argument("--excel-calcs", default="design_calcs.xlsx")
    parser.add_argument("--excel-bolt-preload", default="Bolt pre load.xlsx")
    parser.add_argument("--config-dir", type=Path, default=None, help="Output config directory")
    parser.add_argument("--dry-run", action="store_true", help="Print discovered facts only")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing config files")
    args = parser.parse_args()

    case_root = args.case_root or args.project_dir.parent

    try:
        if args.dry_run:
            facts = discover_project_facts(
                args.project_dir,
                case_root=case_root,
                bom_id=args.bom_id,
                title=args.title,
                excel_calcs=args.excel_calcs,
                excel_bolt_preload=args.excel_bolt_preload,
            )
            for key in sorted(facts):
                if key in {"inventory", "metadata", "modelling"}:
                    continue
                print(f"{key}: {facts[key]}")
            return 0

        paths = init_project_config(
            bom_id=args.bom_id,
            title=args.title,
            project_dir=args.project_dir,
            case_root=case_root,
            customer=args.customer,
            config_dir=args.config_dir,
            excel_calcs=args.excel_calcs,
            excel_bolt_preload=args.excel_bolt_preload,
            overwrite=args.overwrite,
        )
    except ProjectInitError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Wrote project config: {paths['project_config']}")
    print(f"Wrote report defaults: {paths['report_defaults']}")
    print("Edit revision/scope tables and equipment_spec before building.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
