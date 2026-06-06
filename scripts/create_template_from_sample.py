"""One-time: inject Jinja2 placeholders into EP1763 sample docx."""

from __future__ import annotations

import argparse
from pathlib import Path

from ansys_report.report.template_builder import (
    create_minimal_template,
    create_minimal_template_from_scratch,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create EP1763 report template")
    parser.add_argument("--from", dest="source", type=Path, help="Source sample docx")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("templates/EP1763_report_template.docx"),
        help="Output template path",
    )
    args = parser.parse_args()
    if args.source and args.source.exists():
        create_minimal_template(args.source, args.out)
    else:
        create_minimal_template_from_scratch(args.out)
    print(f"Template written to {args.out}")


if __name__ == "__main__":
    main()
