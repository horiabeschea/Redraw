"""Say-it history tests: partial-then-completed answers pass.

grade() sends earlier attempts in the same check so the model grades what
the child has said so far, not just the latest line. The stubbed backend
captures the prompt (no API calls); cache tests use a temporary directory.

Usage (from repo root): .venv/bin/python src/app/test_sayit.py
Exit nonzero on failure.
"""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

import app.backends as backends
from app.sayit import grade

KEY = ("Must contain: the sun heats the lake water; heat turns water into "
       "invisible vapor. Partial credit: mentions the sun heating. "
       "-> What does the heat turn the water into?")
OK = {"verdict": "ok", "hint": "",
      "explanation": "All ideas present across attempts."}

SEEN = {}


def fake_backend(answer):
    def run(client, model, prompt, schema, name):
        SEEN["prompt"] = prompt
        return dict(answer), {"model": model}
    return run


def main():
    real = backends.create_structured
    try:
        with tempfile.TemporaryDirectory() as tmp:
            backends.create_structured = fake_backend(OK)
            d, cached = grade("client", "water becomes vapor", KEY, None,
                              tmp, history=["the sun heats the lake"])
            assert d["verdict"] == "ok" and not cached, "cumulative ok"
            assert "the sun heats the lake" in SEEN["prompt"], \
                "prior attempt in prompt"
            assert "water becomes vapor" in SEEN["prompt"], \
                "latest answer in prompt"
            assert "across all" in SEEN["prompt"], "combined grading rule"
            files = os.listdir(tmp)
            assert len(files) == 1, "graded answer cached"
            d2, cached2 = grade(None, "water becomes vapor", KEY, None,
                                tmp, history=["the sun heats the lake"])
            assert cached2 and d2["verdict"] == "ok", "history replay cached"
            d3, _ = grade("client", "water becomes vapor", KEY, None, tmp,
                           refresh=True, history=["something else"])
            assert len(os.listdir(tmp)) == 2, "cache keyed by history"
            backends.create_structured = fake_backend(OK)
            d4, _ = grade("client", "water becomes vapor", KEY, None, tmp,
                           refresh=True)
            assert "Earlier attempts" not in SEEN["prompt"], \
                "no history section when empty"
    finally:
        backends.create_structured = real
    key = json.dumps({"v": 4, "a": "x", "k": KEY, "m": None, "h": [],
                      "model": "muse-spark-1.3"}, sort_keys=True)
    assert len(key) > 0, "v4 cache key shape"
    print("say-it history ok: prompt, cache, replay, keying")


if __name__ == "__main__":
    main()
