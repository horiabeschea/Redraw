"""Voice mapping tests: 10 child-spoken phrases must map to signals.

Usage (from repo root): .venv/bin/python src/app/test_voice.py
Exit nonzero on failure. No API calls (mapping only; transcription calls
need real speech audio, unavailable in this environment).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.voice import KEYWORDS, phrase_to_signal

CASES = [
    ("I don't get it", "stuck"),
    ("I dont get it", "stuck"),
    ("This is confusing", "stuck"),
    ("Too hard for me", "stuck"),
    ("It's boring", "bored"),
    ("Do it again", "bored"),
    ("Show me", "got_it"),
    ("I got it!", "got_it"),
    ("Next please", "got_it"),
    ("What's evaporation?", None),  # content question, not a signal
]


def main():
    for text, expected in CASES:
        got = phrase_to_signal(text)
        assert got == expected, f"{text!r}: got {got}, want {expected}"
    assert "evaporation" in KEYWORDS and len(KEYWORDS) >= 5
    print(f"voice mapping ok: {len(CASES)}/{len(CASES)} phrases")


if __name__ == "__main__":
    sys.exit(main())
