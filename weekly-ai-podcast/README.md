# Weekly AI Podcast

A ~5-minute weekly audio brief on the past week's AI/LLM news, with emphasis on how US and global insurers are shipping AI features. Styled as an interview between a host and the "AmTrustAIGenius" persona. Delivered every Friday 9:00 AM EST by email.

Built with the Anthropic API (web search + script writing), ElevenLabs (two-voice TTS), and GitHub Actions (cron + review gate + delivery).

## Pipeline

```
Thu 18:00 EST  generate.yml  →  research → validate → script → audio
                                 → open PR with episode branch + artifact
                                 → email reviewer

 (human labels PR `approved-ready-to-ship`)

Fri 09:00 EST  ship.yml      →  find approved PR → download artifact
                                 → Gmail SMTP send with MP3 attached
                                 → merge PR, append shipped log
```

## Required GitHub Actions secrets

| Secret                | Purpose                                       |
| --------------------- | --------------------------------------------- |
| `ANTHROPIC_API_KEY`   | Claude API for research + script generation  |
| `ELEVENLABS_API_KEY`  | Two-voice TTS                                 |
| `SMTP_USER`           | Gmail address (From, and fallback To)         |
| `SMTP_APP_PASSWORD`   | Gmail 16-char App Password                    |
| `REVIEWER_EMAIL`      | Where the Thursday-night review email lands   |

See `.env.example` for the local-dev variable set.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill values
pytest                # unit tests
python -m podcast generate --dry-run     # offline, uses fixture findings
python -m podcast research               # live: writes episodes/<date>/findings.json
python -m podcast audio --script tests/fixtures/mini_script.json
```

## Layout

- `podcast/` — Python package (research, script, audio, email, PR, CLI)
- `config/` — `voices.yaml`, `recipients.yaml`, and prompt templates
- `.github/workflows/` — the two cron workflows
- `episodes/YYYY-MM-DD/` — committed per-week `script.md`, `sources.md`, `findings.json`
- `shipped/YYYY-MM-DD.json` — per-week delivery log
- `tests/` — unit tests and fixtures
- `assets/intro.mp3` — 3-second intro sting (silent placeholder; swap later)
