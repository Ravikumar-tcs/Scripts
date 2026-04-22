import json
from pathlib import Path

import pytest

from podcast import script


FIXTURE = Path(__file__).parent / "fixtures" / "mini_script.json"


def _load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def test_mini_script_is_under_cap():
    sc = _load(FIXTURE)
    assert script.count_words(sc["turns"]) <= script.WORD_CAP


def test_validate_rejects_over_cap():
    turns = [{"speaker": "interviewer" if i % 2 == 0 else "amtrust", "text": "word " * 50}
             for i in range(20)]
    sc = {"week_label": "test", "turns": turns}
    assert script.count_words(sc["turns"]) > script.WORD_CAP
    with pytest.raises(ValueError, match="exceeds cap"):
        script._validate_script(sc)


def test_validate_rejects_consecutive_same_speaker():
    sc = {
        "week_label": "test",
        "turns": [
            {"speaker": "interviewer", "text": "one " * 100},
            {"speaker": "interviewer", "text": "two " * 100},
            {"speaker": "amtrust", "text": "three " * 300},
        ],
    }
    with pytest.raises(ValueError, match="repeats speaker"):
        script._validate_script(sc)


def test_validate_rejects_unknown_speaker():
    sc = {
        "week_label": "test",
        "turns": [
            {"speaker": "interviewer", "text": "one " * 300},
            {"speaker": "narrator", "text": "two " * 300},
        ],
    }
    with pytest.raises(ValueError, match="invalid speaker"):
        script._validate_script(sc)


def test_validate_rejects_under_floor():
    sc = {
        "week_label": "test",
        "turns": [
            {"speaker": "interviewer", "text": "too short"},
            {"speaker": "amtrust", "text": "also short"},
        ],
    }
    with pytest.raises(ValueError, match="below floor"):
        script._validate_script(sc)
