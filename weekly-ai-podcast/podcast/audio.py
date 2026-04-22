from __future__ import annotations

import io
import json
from pathlib import Path

from elevenlabs.client import ElevenLabs
from pydub import AudioSegment

from . import config

MODEL_ID = "eleven_turbo_v2_5"
OUTPUT_FORMAT = "mp3_44100_64"
GAP_MS = 350


def _synthesize_turn(client: ElevenLabs, voice_id: str, text: str) -> AudioSegment:
    stream = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        output_format=OUTPUT_FORMAT,
    )
    buf = io.BytesIO()
    for chunk in stream:
        if chunk:
            buf.write(chunk)
    buf.seek(0)
    return AudioSegment.from_file(buf, format="mp3")


def synthesize_script(script: dict, out_path: Path, *, include_intro: bool = True) -> Path:
    voices = config.load_voices()
    settings = config.load_settings()
    client = ElevenLabs(api_key=settings.elevenlabs_api_key)

    pieces: list[AudioSegment] = []

    intro_path = config.ASSETS_DIR / "intro.mp3"
    if include_intro and intro_path.exists():
        pieces.append(AudioSegment.from_file(intro_path))

    gap = AudioSegment.silent(duration=GAP_MS)

    for i, turn in enumerate(script["turns"]):
        voice_id = voices[turn["speaker"]]
        segment = _synthesize_turn(client, voice_id, turn["text"])
        if pieces:
            pieces.append(gap)
        pieces.append(segment)

    if not pieces:
        raise RuntimeError("No audio segments produced")

    episode = pieces[0]
    for p in pieces[1:]:
        episode += p

    out_path.parent.mkdir(parents=True, exist_ok=True)
    episode.export(out_path, format="mp3", bitrate="64k", parameters=["-ac", "1"])
    return out_path


def synthesize_silent_stub(script: dict, out_path: Path) -> Path:
    """Offline/dry-run path: 1 second of silence per 20 words, no API calls."""
    total_words = sum(len(t.get("text", "").split()) for t in script["turns"])
    duration_ms = max(3000, int((total_words / 20.0) * 1000))
    silent = AudioSegment.silent(duration=duration_ms)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    silent.export(out_path, format="mp3", bitrate="64k", parameters=["-ac", "1"])
    return out_path


def load_script(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)
