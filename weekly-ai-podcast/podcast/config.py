from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
PROMPT_DIR = CONFIG_DIR / "prompts"
EPISODES_DIR = REPO_ROOT / "episodes"
SHIPPED_DIR = REPO_ROOT / "shipped"
ASSETS_DIR = REPO_ROOT / "assets"

load_dotenv(REPO_ROOT / ".env", override=False)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    elevenlabs_api_key: str
    smtp_user: str
    smtp_app_password: str
    smtp_host: str
    smtp_port: int
    reviewer_email: str


def load_settings(*, require_all: bool = True) -> Settings:
    def get(name: str, default: str = "") -> str:
        value = os.environ.get(name, default)
        if require_all and not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value

    return Settings(
        anthropic_api_key=get("ANTHROPIC_API_KEY"),
        elevenlabs_api_key=get("ELEVENLABS_API_KEY"),
        smtp_user=get("SMTP_USER"),
        smtp_app_password=get("SMTP_APP_PASSWORD"),
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        reviewer_email=get("REVIEWER_EMAIL"),
    )


def load_voices() -> dict[str, str]:
    with (CONFIG_DIR / "voices.yaml").open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "interviewer" not in data or "amtrust" not in data:
        raise RuntimeError("config/voices.yaml must define both 'interviewer' and 'amtrust' voice ids")
    return {"interviewer": data["interviewer"], "amtrust": data["amtrust"]}


def load_recipients() -> list[str]:
    """Return the recipient list. Falls back to [SMTP_USER] if the file is empty."""
    with (CONFIG_DIR / "recipients.yaml").open() as f:
        data = yaml.safe_load(f) or {}
    recipients = data.get("recipients") or []
    recipients = [r.strip() for r in recipients if isinstance(r, str) and r.strip()]
    if not recipients:
        fallback = os.environ.get("SMTP_USER", "").strip()
        if fallback:
            recipients = [fallback]
    return recipients


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text()


def episode_date(today: date | None = None) -> date:
    """Return the episode date as the Friday of the current week (US/Eastern enough)."""
    today = today or datetime.now(timezone.utc).date()
    # Friday = weekday 4. Walk forward to the nearest Friday, including today if Friday.
    days_ahead = (4 - today.weekday()) % 7
    return today + timedelta(days=days_ahead)


def week_start(today: date | None = None) -> date:
    """Start of the 7-day research window = 7 days before today."""
    today = today or datetime.now(timezone.utc).date()
    return today - timedelta(days=7)


def episode_dir(when: date | None = None) -> Path:
    when = when or episode_date()
    return EPISODES_DIR / when.isoformat()
