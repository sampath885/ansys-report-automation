"""Load EP2737 section content matrix YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

DEFAULT_SECTION_CONTENT = (
    Path(__file__).resolve().parents[3] / "config" / "ep2737_section_content.yaml"
)


class BlockSpec(BaseModel):
    type: str
    text: str | None = None
    template: str | None = None
    field: str | None = None
    level: int = 1
    slot: str | None = None
    slot_template: str | None = None
    caption: str | None = None
    caption_template: str | None = None
    required: bool = False
    implemented: bool = True
    note: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows_path: str | None = None
    columns: list[str] = Field(default_factory=list)
    static_rows: list[list[str]] = Field(default_factory=list)
    label: str | None = None
    unit: str | None = None
    suffix_template: str | None = None
    when_field: str | None = None
    unless_field: str | None = None
    headers_path: str | None = None
    columns_path: str | None = None
    raw_table: bool = False
    items_path: str | None = None
    item_prefix: str = "item"
    blocks: list[BlockSpec] = Field(default_factory=list)
    narrative_from: str | list[str] | None = None
    ref_key: str | None = None
    when_style: str | None = None
    unless_style: str | None = None
    narrative_mode: str | None = None
    analysis_folder: str | None = None
    analysis_folder_template: str | None = None
    subfolder: str | None = None
    category: str | None = None
    filename: str | None = None
    caption_prefix: str | None = None
    caption_suffix: str | None = None

    model_config = {"extra": "ignore"}


class SectionSpec(BaseModel):
    key: str
    section_key: str | None = None
    heading: str | None = None
    heading_level: int = 1
    parent_section: str | None = None
    enabled: bool = True
    enabled_when_any: list[str] = Field(default_factory=list)
    reference_table: str | None = None
    blocks: list[BlockSpec] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class SectionContentSpec(BaseModel):
    version: int = 1
    reference_template: str = ""
    sections: list[SectionSpec] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


def load_section_content_spec(path: Path | None = None) -> SectionContentSpec:
    spec_path = path or DEFAULT_SECTION_CONTENT
    with spec_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    sections = []
    for item in raw.get("sections", []):
        sections.append(_parse_section(item))
    return SectionContentSpec(
        version=raw.get("version", 1),
        reference_template=raw.get("reference_template", ""),
        sections=sections,
    )


def _parse_section(data: dict[str, Any]) -> SectionSpec:
    blocks = [_parse_block(b) for b in data.get("blocks", [])]
    return SectionSpec(
        key=data["key"],
        section_key=data.get("section_key"),
        heading=data.get("heading"),
        heading_level=data.get("heading_level", 1),
        parent_section=data.get("parent_section"),
        enabled=data.get("enabled", True),
        enabled_when_any=data.get("enabled_when_any", []),
        reference_table=data.get("reference_table"),
        blocks=blocks,
    )


def _parse_block(data: dict[str, Any]) -> BlockSpec:
    nested = [_parse_block(b) for b in data.get("blocks", [])]
    return BlockSpec(**{**data, "blocks": nested})
