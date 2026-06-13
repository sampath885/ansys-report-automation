"""Resolved report content blocks for EP2737 block-based rendering."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


BlockKind = Literal[
    "cover",
    "heading",
    "paragraph",
    "table",
    "figure",
    "scalar",
    "narrative",
    "page_break",
    "pending",
]


class RenderBlock(BaseModel):
    kind: BlockKind
    text: str | None = None
    level: int = 1
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    caption: str | None = None
    image_path: str | None = None
    slot: str | None = None
    label: str | None = None
    value: str | None = None
    unit: str | None = None
    observations: list[str] = Field(default_factory=list)
    conclusions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    pending: bool = False
    note: str | None = None


class RenderSection(BaseModel):
    key: str
    heading: str | None = None
    heading_level: int = 1
    parent_section: str | None = None
    blocks: list[RenderBlock] = Field(default_factory=list)


class RenderDocument(BaseModel):
    sections: list[RenderSection] = Field(default_factory=list)
    missing_figures: list[str] = Field(default_factory=list)
    pending_blocks: list[str] = Field(default_factory=list)


def narrative_block(data: dict[str, Any]) -> RenderBlock | None:
    narr = data.get("narrative") or {}
    obs = narr.get("observations") or []
    con = narr.get("conclusions") or []
    rec = narr.get("recommendations") or []
    if not obs and not con and not rec:
        return None
    return RenderBlock(
        kind="narrative",
        observations=[str(x) for x in obs],
        conclusions=[str(x) for x in con],
        recommendations=[str(x) for x in rec],
    )
