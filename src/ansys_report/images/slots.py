"""Collect figure slot names required by section content specs."""

from __future__ import annotations

from ansys_report.report.section_spec import BlockSpec, SectionContentSpec, load_section_content_spec
from ansys_report.sections.shock import SHOCK_DIRECTIONS


def _walk_blocks(blocks: list[BlockSpec]) -> list[BlockSpec]:
    out: list[BlockSpec] = []
    for block in blocks:
        out.append(block)
        if block.blocks:
            out.extend(_walk_blocks(block.blocks))
    return out


def _expand_slot_template(template: str) -> list[str]:
    if "{shock_item.key}" in template:
        return [template.replace("{shock_item.key}", key) for key, *_ in SHOCK_DIRECTIONS]
    return [template]


def collect_figure_slots(spec: SectionContentSpec) -> list[str]:
    slots: list[str] = []
    for section in spec.sections:
        for block in _walk_blocks(section.blocks):
            if block.type != "figure":
                continue
            if block.slot:
                slots.append(block.slot)
            elif block.slot_template:
                slots.extend(_expand_slot_template(block.slot_template))
    return sorted(set(slots))


def figure_slots_for_config(section_content_path) -> list[str]:
    from pathlib import Path

    if section_content_path is None:
        return []
    path = Path(section_content_path)
    if not path.exists():
        return []
    return collect_figure_slots(load_section_content_spec(path))
