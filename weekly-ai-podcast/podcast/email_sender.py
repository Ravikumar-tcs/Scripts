from __future__ import annotations

import json
import smtplib
from datetime import date, datetime, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path

from . import config
from .research import BUCKETS, BUCKET_LABELS


def _three_sentence_summary(findings: dict) -> str:
    """Cheap deterministic summary — no LLM call needed for the email preface."""
    counts = {b: len(findings.get(b, [])) for b in BUCKETS}
    total = sum(counts.values())
    parts = []
    parts.append(f"This week's brief covers {total} developments across AI and insurance.")

    leading = max(BUCKETS, key=lambda b: counts[b])
    if counts[leading]:
        parts.append(
            f"Most activity was in {BUCKET_LABELS[leading].lower()} ({counts[leading]} items)."
        )

    insurer_total = counts["us_insurer_ai"] + counts["global_insurer_ai"]
    if insurer_total:
        parts.append(
            f"Insurer-specific AI announcements: {counts['us_insurer_ai']} US, "
            f"{counts['global_insurer_ai']} global."
        )
    else:
        parts.append("No insurer-specific AI announcements surfaced this week.")

    return " ".join(parts)


def build_html_body(findings: dict, summary: str) -> str:
    lines = ["<html><body>", f"<p>{escape(summary)}</p>"]
    for bucket in BUCKETS:
        items = findings.get(bucket, [])
        if not items:
            continue
        lines.append(f"<h3>{escape(BUCKET_LABELS[bucket])}</h3><ul>")
        for item in items:
            lines.append(
                f'<li><a href="{escape(item["source_url"])}">{escape(item["headline"])}</a>'
                f' — <em>{escape(item["source_title"])}</em>, {escape(item["published_at"])}</li>'
            )
        lines.append("</ul>")
    lines.append("</body></html>")
    return "\n".join(lines)


def build_text_body(findings: dict, summary: str) -> str:
    lines = [summary, ""]
    for bucket in BUCKETS:
        items = findings.get(bucket, [])
        if not items:
            continue
        lines.append(BUCKET_LABELS[bucket])
        for item in items:
            lines.append(
                f"- {item['headline']} ({item['source_title']}, {item['published_at']})"
            )
            lines.append(f"  {item['source_url']}")
        lines.append("")
    return "\n".join(lines)


def _send_one(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    attachment_path: Path | None,
    settings: config.Settings,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if attachment_path:
        data = attachment_path.read_bytes()
        msg.add_attachment(
            data, maintype="audio", subtype="mpeg", filename=attachment_path.name
        )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_app_password)
        server.send_message(msg)


def send_episode(
    *,
    when: date,
    findings: dict,
    attachment_path: Path,
    recipients: list[str] | None = None,
) -> dict:
    settings = config.load_settings()
    recipients = recipients if recipients is not None else config.load_recipients()
    if not recipients:
        raise RuntimeError("No recipients configured and SMTP_USER fallback is empty")

    subject = f"AI & Insurance Weekly — {when.strftime('%B %-d, %Y')}"
    summary = _three_sentence_summary(findings)
    html_body = build_html_body(findings, summary)
    text_body = build_text_body(findings, summary)

    log = {"sent_at": datetime.now(timezone.utc).isoformat(), "results": []}
    for to in recipients:
        try:
            _send_one(
                to=to,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                attachment_path=attachment_path,
                settings=settings,
            )
            log["results"].append({"to": to, "status": "ok"})
        except Exception as e:
            log["results"].append({"to": to, "status": "error", "error": str(e)})
    return log


def send_reviewer_notice(
    *,
    when: date,
    pr_url: str,
    artifact_url: str,
    script_preview: str,
) -> None:
    settings = config.load_settings()
    subject = f"[Review needed] AI & Insurance Weekly — {when.strftime('%B %-d, %Y')}"
    text_body = (
        f"The weekly episode draft is ready for review.\n\n"
        f"PR: {pr_url}\n"
        f"Episode audio (workflow artifact): {artifact_url}\n\n"
        f"If it looks good, label the PR `approved-ready-to-ship`. "
        f"The ship workflow runs Friday 9 AM EST.\n\n"
        f"Script preview:\n\n{script_preview}\n"
    )
    html_body = (
        "<html><body>"
        "<p>The weekly episode draft is ready for review.</p>"
        f'<p><strong>PR:</strong> <a href="{escape(pr_url)}">{escape(pr_url)}</a><br>'
        f'<strong>Episode audio:</strong> <a href="{escape(artifact_url)}">workflow artifact</a></p>'
        "<p>If it looks good, label the PR <code>approved-ready-to-ship</code>. "
        "The ship workflow runs Friday 9 AM EST.</p>"
        f"<pre>{escape(script_preview)}</pre>"
        "</body></html>"
    )
    _send_one(
        to=settings.reviewer_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        attachment_path=None,
        settings=settings,
    )


def append_shipped_log(when: date, log: dict) -> Path:
    config.SHIPPED_DIR.mkdir(parents=True, exist_ok=True)
    path = config.SHIPPED_DIR / f"{when.isoformat()}.json"
    path.write_text(json.dumps(log, indent=2))
    return path
