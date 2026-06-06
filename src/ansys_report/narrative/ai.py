"""Optional AI narrative polish via Anthropic or OpenAI."""

from __future__ import annotations

import json
import logging
import os

from ansys_report.models import Narrative
from ansys_report.narrative import prompts

logger = logging.getLogger(__name__)


def polish_narrative(draft: Narrative, payload: dict, prompt_template: str) -> Narrative:
    """Return AI-polished narrative or the draft on any failure."""
    try:
        text = _call_llm(prompt_template.format(payload=json.dumps(payload, default=str)))
        if not text:
            return draft
        lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
        return Narrative(
            executive_summary=lines[0] if lines else draft.executive_summary,
            observations=lines[1:-1] if len(lines) > 2 else draft.observations,
            conclusions=[lines[-1]] if lines else draft.conclusions,
            recommendations=draft.recommendations,
            verdict=draft.verdict,
            source="ai",
        )
    except Exception as exc:
        logger.warning("AI narrative failed; using rule-based text: %s", exc)
        return draft


def _call_llm(prompt: str) -> str | None:
    if key := os.getenv("ANTHROPIC_API_KEY"):
        return _anthropic(prompt, key)
    if key := os.getenv("OPENAI_API_KEY"):
        return _openai(prompt, key)
    return None


def _anthropic(prompt: str, api_key: str) -> str | None:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except ImportError:
        logger.debug("anthropic package not installed")
        return None


def _openai(prompt: str, api_key: str) -> str | None:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )
        return resp.choices[0].message.content
    except ImportError:
        logger.debug("openai package not installed")
        return None
