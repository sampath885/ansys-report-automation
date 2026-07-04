"""Assemble render blocks from section content spec + build context."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ansys_report.config import ProjectConfig
from ansys_report.images.component_figures import discover_gallery_figures
from ansys_report.report.blocks import RenderBlock, RenderDocument, RenderSection, merge_narrative_sources, narrative_block
from ansys_report.report.section_spec import BlockSpec, SectionContentSpec, SectionSpec, load_section_content_spec


def assemble_ep2737_document(
    context: dict[str, Any],
    cfg: ProjectConfig,
    spec: SectionContentSpec | None = None,
    spec_path: Path | None = None,
) -> RenderDocument:
    spec = spec or load_section_content_spec(spec_path or cfg.section_content_path)
    enabled = set(cfg.sections_enabled)
    images = context.get("images") or {}
    skip_images = cfg.skip_images
    doc = RenderDocument()
    seen_parents: set[str] = set()

    for section in spec.sections:
        if not _section_enabled(section, enabled):
            continue
        if section.key == "cover":
            doc.sections.append(RenderSection(key="cover", blocks=[RenderBlock(kind="cover")]))
            continue

        section_key = section.section_key or section.key
        data = context.get(section_key, {})
        if section.enabled_when_any and not any(k in enabled for k in section.enabled_when_any):
            continue
        if section_key not in enabled and not section.enabled_when_any:
            continue
        if section_key not in context and section.key != "harmonic_conclusion":
            continue

        blocks: list[RenderBlock] = []
        parent = section.parent_section
        if parent and parent not in seen_parents:
            seen_parents.add(parent)
            blocks.append(RenderBlock(kind="heading", text=parent, level=2))

        if section.heading:
            blocks.append(
                RenderBlock(kind="heading", text=section.heading, level=section.heading_level)
            )

        env = _build_env(context, data, section_key)
        for block_spec in section.blocks:
            blocks.extend(
                _materialize_block(
                    block_spec,
                    env,
                    data,
                    images,
                    skip_images,
                    doc,
                    section_key,
                    context,
                    cfg,
                )
            )

        doc.sections.append(
            RenderSection(
                key=section.key,
                heading=section.heading,
                heading_level=section.heading_level,
                parent_section=section.parent_section,
                blocks=blocks,
            )
        )

    # The reference EP2737 report has no auto-generated executive-summary block,
    # so it is intentionally omitted here to match the client report format.
    return doc


def validate_assembled_document(doc: RenderDocument) -> list[str]:
    warnings: list[str] = []
    warnings.extend(f"Missing figure slot: {s}" for s in doc.missing_figures)
    warnings.extend(f"Pending block: {p}" for p in doc.pending_blocks)
    return warnings


def _narrative_source(
    spec: BlockSpec,
    section_key: str,
    context: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve narrative payload unless narrative_from requests a multi-source merge."""
    if isinstance(spec.narrative_from, list):
        return None
    src_key = spec.narrative_from or section_key
    return context.get(src_key, data)


def _section_enabled(section: SectionSpec, enabled: set[str]) -> bool:
    if not section.enabled:
        return False
    if section.key == "cover":
        return True
    if section.enabled_when_any:
        return any(k in enabled for k in section.enabled_when_any)
    section_key = section.section_key or section.key
    return section_key in enabled


def _build_env(context: dict[str, Any], data: dict[str, Any], section_key: str) -> dict[str, Any]:
    env: dict[str, Any] = dict(context)
    env.update(data)
    env["section_key"] = section_key
    if isinstance(data.get("assembly"), dict):
        env["assembly_mass_kg"] = _fmt(data["assembly"].get("mass_kg"))
    tools = data.get("tools")
    if tools:
        env["tools_text"] = ", ".join(str(t) for t in tools)
    steps = data.get("load_steps")
    if steps is not None:
        env["load_steps_text"] = ", ".join(_fmt(s) for s in steps)
    contacts = data.get("contacts")
    if contacts is not None:
        env["contact_count"] = len(contacts)
    return env


def _materialize_block(
    spec: BlockSpec,
    env: dict[str, Any],
    data: dict[str, Any],
    images: dict[str, Any],
    skip_images: bool,
    doc: RenderDocument,
    section_key: str,
    context: dict[str, Any],
    cfg: ProjectConfig,
) -> list[RenderBlock]:
    if spec.unless_style and _style_enabled(cfg, spec.unless_style):
        return []
    if spec.when_style and not _style_enabled(cfg, spec.when_style):
        return []

    if spec.type == "repeat":
        items = _resolve_path(data, spec.items_path or "") or []
        out: list[RenderBlock] = []
        prefix = spec.item_prefix or "item"
        for item in items:
            row_item = dict(item) if isinstance(item, dict) else item
            if prefix == "shock_item" and isinstance(row_item, dict):
                from ansys_report.extract.bolt_loads import SHOCK_TABLE_NUMBERS

                row_item["table_no"] = SHOCK_TABLE_NUMBERS.get(row_item.get("key", ""), "")
            item_env = {**env, prefix: row_item, **(row_item if isinstance(row_item, dict) else {})}
            for child in spec.blocks:
                out.extend(
                    _materialize_block(
                        _substitute_block_spec(child, row_item, prefix),
                        item_env,
                        row_item if isinstance(row_item, dict) else data,
                        images,
                        skip_images,
                        doc,
                        section_key,
                        context,
                        cfg,
                    )
                )
        return out

    if spec.unless_field and _resolve_path(env, spec.unless_field):
        return []

    if spec.when_field and _resolve_path(env, spec.when_field) is None:
        return []

    if spec.type == "heading":
        text = _render_template(spec.template or spec.text or "", env)
        return [RenderBlock(kind="heading", text=text, level=spec.level)]

    if spec.type == "paragraph":
        if spec.field:
            val = _resolve_path(data, spec.field)
            if val is None:
                return []
            return [RenderBlock(kind="paragraph", text=str(val))]
        text = _render_template(spec.template or "", env)
        if not text.strip():
            return []
        return [RenderBlock(kind="paragraph", text=text)]

    if spec.type == "scalar":
        val = _resolve_path(data, spec.field or "")
        if val is None:
            return []
        suffix = _render_template(spec.suffix_template or "", env) if spec.suffix_template else ""
        unit = f" {spec.unit}" if spec.unit else ""
        value = f"{_fmt(val)}{unit}{suffix}"
        return [
            RenderBlock(
                kind="scalar",
                label=spec.label,
                value=value,
            )
        ]

    if spec.type == "table":
        if spec.implemented is False:
            doc.pending_blocks.append(spec.caption or spec.caption_template or spec.note or "table")
            label = spec.caption or spec.caption_template or spec.note or "Table pending"
            return [
                RenderBlock(
                    kind="pending",
                    caption=label,
                    note=spec.note,
                    pending=True,
                )
            ]

        caption = _render_template(spec.caption or spec.caption_template or "", env)
        headers = list(spec.headers)
        columns = list(spec.columns)
        if spec.headers_path:
            dynamic_headers = _resolve_path(data, spec.headers_path) or _resolve_path(env, spec.headers_path)
            if dynamic_headers:
                headers = [str(h) for h in dynamic_headers]
        if spec.columns_path:
            dynamic_columns = _resolve_path(data, spec.columns_path) or _resolve_path(env, spec.columns_path)
            if dynamic_columns:
                columns = [str(c) for c in dynamic_columns]
        rows: list[list[str]] = []
        if spec.static_rows:
            for row in spec.static_rows:
                rows.append([_render_template(cell, env) for cell in row])
        elif spec.rows_path:
            items = _resolve_path(data, spec.rows_path) or []
            if spec.raw_table or (items and isinstance(items[0], list)):
                for row in items:
                    rows.append([str(c) for c in row])
            elif spec.columns:
                for item in items:
                    rows.append([_fmt(_resolve_path(item, col)) for col in spec.columns])

        if not rows and spec.required:
            return [RenderBlock(kind="paragraph", text="(no data)")]
        if not rows:
            return []

        return [
            RenderBlock(
                kind="table",
                caption=caption or None,
                headers=headers,
                rows=rows,
            )
        ]

    if spec.type == "figure_gallery":
        return _materialize_figure_gallery(spec, env, skip_images, context)

    if spec.type == "figure":
        if spec.field:
            image_path = _resolve_path(data, spec.field) or _resolve_path(env, spec.field)
            caption = _render_template(spec.caption or spec.caption_template or "", env)
            if not image_path:
                return []
            return [
                RenderBlock(
                    kind="figure",
                    caption=caption or None,
                    image_path=str(image_path),
                )
            ]
        slot = _render_template(spec.slot_template or spec.slot or "", env)
        caption = _render_template(spec.caption or spec.caption_template or "", env)
        image_path = _resolve_image(images, slot)
        if skip_images or not image_path:
            if spec.required:
                doc.missing_figures.append(slot or caption)
            if skip_images and caption:
                return [
                    RenderBlock(
                        kind="pending",
                        caption=caption,
                        slot=slot,
                        pending=True,
                        note="Figure pending (skip_images)",
                    )
                ]
            if not skip_images and caption:
                return [
                    RenderBlock(
                        kind="pending",
                        caption=caption,
                        slot=slot,
                        pending=True,
                        note=f"Image not found for slot: {slot or '(unnamed)'}",
                    )
                ]
            return []
        return [
            RenderBlock(
                kind="figure",
                caption=caption or None,
                slot=slot,
                image_path=str(image_path),
            )
        ]

    if spec.type == "reference_table":
        ref = _resolve_path(context, f"reference_tables.{spec.ref_key}") if spec.ref_key else None
        if not ref:
            return []
        headers = ref.get("headers") or []
        rows = ref.get("rows") or []
        if not rows:
            return []
        return [
            RenderBlock(
                kind="table",
                caption=ref.get("caption") or spec.caption,
                headers=[str(h) for h in headers],
                rows=[[str(c) for c in row] for row in rows],
            )
        ]

    if spec.type == "narrative":
        if isinstance(spec.narrative_from, list):
            nb = merge_narrative_sources(spec.narrative_from, context)
        else:
            src = _narrative_source(spec, section_key, context, data)
            nb = narrative_block(src)
        if nb and spec.narrative_mode == "conclusions_only":
            nb = nb.model_copy(update={"observations": [], "recommendations": []})
        return [nb] if nb else []

    return []


def _substitute_block_spec(spec: BlockSpec, item: dict[str, Any], prefix: str) -> BlockSpec:
    raw = spec.model_dump()
    sub_env = {prefix: item, **item} if isinstance(item, dict) else {prefix: item}
    text_fields = ("template", "slot_template", "caption_template", "caption", "text", "analysis_folder_template", "caption_prefix", "caption_suffix", "analysis_folder")
    for key in text_fields:
        if raw.get(key):
            raw[key] = _render_template(raw[key], sub_env)
    nested = [_substitute_block_spec(b, item, prefix) for b in spec.blocks]
    raw["blocks"] = nested
    return BlockSpec(**raw)


def _resolve_path(obj: Any, path: str) -> Any:
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def _style_enabled(cfg: ProjectConfig, style: str) -> bool:
    if style == "ep1581":
        return (cfg.static.conclusion_table_style or "").lower() == "ep1581"
    return True


def _materialize_figure_gallery(
    spec: BlockSpec,
    env: dict[str, Any],
    skip_images: bool,
    context: dict[str, Any],
) -> list[RenderBlock]:
    folder = _render_template(spec.analysis_folder_template or spec.analysis_folder or "", env)
    if not folder:
        return []

    image_root = context.get("image_root")
    if not image_root:
        return []

    root = Path(image_root)
    figures = discover_gallery_figures(
        root,
        folder,
        subfolder=spec.subfolder or "solution",
        category=spec.category or "material_stress",
        filename=spec.filename,
    )
    if not figures:
        return []

    prefix = _render_template(spec.caption_prefix or "", env)
    suffix = _render_template(spec.caption_suffix or "", env)
    blocks: list[RenderBlock] = []
    for fig in figures:
        if spec.caption:
            caption = _render_template(spec.caption, {**env, "figure_label": fig.label, "figure_stem": fig.stem})
        elif spec.caption_template:
            caption = _render_template(
                spec.caption_template,
                {**env, "figure_label": fig.label, "figure_stem": fig.stem},
            )
        else:
            caption = f"{prefix} - {fig.label} {suffix}".strip()
        if skip_images:
            blocks.append(
                RenderBlock(
                    kind="pending",
                    caption=caption,
                    pending=True,
                    note="Figure pending (skip_images)",
                )
            )
            continue
        blocks.append(
            RenderBlock(
                kind="figure",
                caption=caption,
                slot=fig.rel_path,
                image_path=str(fig.path),
            )
        )
    return blocks


def _resolve_image(images: dict[str, Any], slot: str) -> Path | None:
    if not slot:
        return None
    val = images.get(slot)
    if val is None:
        return None
    if isinstance(val, Path):
        return val if val.exists() else None
    if isinstance(val, str):
        p = Path(val)
        return p if p.exists() else None
    path = getattr(val, "path", None)
    if path:
        p = Path(path)
        return p if p.exists() else None
    return None


def _render_template(template: str, env: dict[str, Any]) -> str:
    if not template:
        return ""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        val = _resolve_path(env, key)
        if val is None:
            return ""
        return _fmt(val)

    return re.sub(r"\{([^}]+)\}", repl, template)


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-4:
            return str(int(round(value)))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)
