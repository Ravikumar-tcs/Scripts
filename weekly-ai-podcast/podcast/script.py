from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from anthropic import Anthropic

from . import config
from .research import BUCKETS, BUCKET_LABELS, render_sources

SCRIPT_MODEL = "claude-opus-4-5"
WORD_CAP = 750
WORD_FLOOR = 450


def count_words(turns: list[dict]) -> int:
    return sum(len(t.get("text", "").split()) for t in turns)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in script response:\n{text[:500]}")
    return json.loads(text[start : end + 1])


def _text_from_content(content_blocks) -> str:
    parts = []
    for block in content_blocks:
        block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if block_type == "text":
            parts.append(getattr(block, "text", None) or block.get("text", ""))
    return "\n".join(parts)


def _validate_script(script: dict) -> None:
    turns = script.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("Script must have a non-empty 'turns' list")

    last_speaker = None
    for i, turn in enumerate(turns):
        speaker = turn.get("speaker")
        text = turn.get("text", "").strip()
        if speaker not in {"interviewer", "amtrust"}:
            raise ValueError(f"Turn {i} has invalid speaker: {speaker!r}")
        if not text:
            raise ValueError(f"Turn {i} is empty")
        if speaker == last_speaker:
            raise ValueError(f"Turn {i} repeats speaker {speaker!r}")
        last_speaker = speaker

    words = count_words(turns)
    if words > WORD_CAP:
        raise ValueError(f"Script is {words} words, exceeds cap of {WORD_CAP}")
    if words < WORD_FLOOR:
        raise ValueError(f"Script is only {words} words, below floor of {WORD_FLOOR}")


def week_label(when: date) -> str:
    return f"Week of {when.strftime('%B %-d, %Y')}"


def generate_script(findings: dict, *, when: date | None = None) -> dict:
    when = when or config.episode_date()
    label = week_label(when)

    prompt = config.load_prompt("script.md").format(
        week_label=label,
        findings_json=json.dumps(findings, indent=2),
    )

    client = Anthropic(api_key=config.load_settings().anthropic_api_key)
    response = client.messages.create(
        model=SCRIPT_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    script = _extract_json(_text_from_content(response.content))
    script.setdefault("week_label", label)
    _validate_script(script)
    return script


def render_script_md(script: dict, findings: dict) -> str:
    lines = [f"# {script['week_label']}", ""]
    for turn in script["turns"]:
        speaker = "Interviewer" if turn["speaker"] == "interviewer" else "AmTrustAIGenius"
        lines.append(f"**{speaker}:** {turn['text']}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Sources cited this week")
    lines.append("")
    lines.append(render_sources(findings).split("\n", 2)[-1])
    return "\n".join(lines)


def write_artifacts(script: dict, findings: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "script.json").write_text(json.dumps(script, indent=2))
    (out_dir / "script.md").write_text(render_script_md(script, findings))
