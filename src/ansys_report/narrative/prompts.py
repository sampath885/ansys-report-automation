"""Prompt templates for optional AI narrative polish."""

STATIC_PROMPT = """You are a CAE report writer. Given structured static analysis results and a rule-based draft,
produce concise engineering observations and conclusions (2-4 sentences each). Use MPa and mm units.
Do not invent numbers not present in the input.

Input JSON:
{payload}
"""

MODAL_PROMPT = """You are a CAE report writer. Given modal frequencies and operating band, write observations
and conclusions about resonance risk. Use Hz units. Do not invent numbers.

Input JSON:
{payload}
"""

EXECUTIVE_PROMPT = """Summarize this engineering assessment in 2-3 sentences for an executive summary.

Input JSON:
{payload}
"""

METHODOLOGY_PROMPT = """You are a senior CAE report writer. Improve the clarity and flow of the
following engineering methodology paragraph for the '{section}' section of a structural analysis
report. Keep all technical facts, numbers and units exactly as given; do not invent new numbers.
Return only the improved paragraph text.

Draft:
{draft}
"""
