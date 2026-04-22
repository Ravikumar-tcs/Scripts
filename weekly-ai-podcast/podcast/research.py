from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from anthropic import Anthropic

from . import config

BUCKETS = ("new_ai_implementations", "new_or_updated_llms", "us_insurer_ai", "global_insurer_ai")
BUCKET_LABELS = {
    "new_ai_implementations": "New AI implementations",
    "new_or_updated_llms": "New / updated LLMs",
    "us_insurer_ai": "US insurer AI",
    "global_insurer_ai": "Global insurer AI",
}

RESEARCH_MODEL = "claude-opus-4-5"
VALIDATE_MODEL = "claude-sonnet-4-5"


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of the model's response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in response:\n{text[:500]}")
    return json.loads(text[start : end + 1])


def _text_from_content(content_blocks) -> str:
    parts = []
    for block in content_blocks:
        # SDK returns objects; fall back to dict for raw responses
        block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if block_type == "text":
            parts.append(getattr(block, "text", None) or block.get("text", ""))
    return "\n".join(parts)


def run_research(*, today: date | None = None) -> dict:
    today = today or config.episode_date()
    week_start = config.week_start(today)

    prompt = config.load_prompt("research.md").format(
        today=today.isoformat(),
        week_start=week_start.isoformat(),
    )

    client = Anthropic(api_key=config.load_settings().anthropic_api_key)

    response = client.messages.create(
        model=RESEARCH_MODEL,
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": prompt}],
    )

    text = _text_from_content(response.content)
    findings = _extract_json(text)
    _shape_check(findings)
    return findings


def validate_findings(findings: dict, *, today: date | None = None) -> dict:
    today = today or config.episode_date()
    week_start = config.week_start(today)
    prompt = config.load_prompt("validate.md").format(week_start=week_start.isoformat())

    client = Anthropic(api_key=config.load_settings().anthropic_api_key)
    response = client.messages.create(
        model=VALIDATE_MODEL,
        max_tokens=4000,
        messages=[
            {"role": "user", "content": f"{prompt}\n\nFindings JSON:\n{json.dumps(findings, indent=2)}"}
        ],
    )
    validated = _extract_json(_text_from_content(response.content))
    _shape_check(validated)
    return _dedupe(validated)


def _shape_check(obj: dict) -> None:
    missing = [b for b in BUCKETS if b not in obj]
    if missing:
        raise ValueError(f"Findings JSON missing buckets: {missing}")
    for bucket in BUCKETS:
        if not isinstance(obj[bucket], list):
            raise ValueError(f"Bucket {bucket} is not a list")


def _dedupe(obj: dict) -> dict:
    seen: set[str] = set()
    out: dict = {}
    for bucket in BUCKETS:
        kept = []
        for item in obj.get(bucket, []):
            key = (item.get("source_url") or item.get("headline") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(item)
        out[bucket] = kept
    return out


def write_artifacts(findings: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "findings.json").write_text(json.dumps(findings, indent=2))
    (out_dir / "sources.md").write_text(render_sources(findings))


def render_sources(findings: dict) -> str:
    lines = ["# Sources", ""]
    for bucket in BUCKETS:
        items = findings.get(bucket, [])
        if not items:
            continue
        lines.append(f"## {BUCKET_LABELS[bucket]}")
        lines.append("")
        for item in items:
            lines.append(
                f"- [{item['headline']}]({item['source_url']}) — "
                f"*{item['source_title']}*, {item['published_at']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def research_and_validate(out_dir: Path | None = None, *, today: date | None = None) -> dict:
    today = today or config.episode_date()
    raw = run_research(today=today)
    validated = validate_findings(raw, today=today)
    if out_dir:
        write_artifacts(validated, out_dir)
    return validated
