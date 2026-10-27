"""Say-it proof: 5 correct + 5 wrong paraphrases per step. Bar: 45/50.

Results cache per answer hash, so reruns are free. --refresh re-spends.
--fallback-only uses the keyword rule (no API).

Usage (from repo root):
  set -a; source .env; set +a
  .venv/bin/python src/app/run_sayit.py [--refresh] [--fallback-only]
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.sayit import grade

CACHE_DIR = os.path.join(ROOT, "lessons", "water-cycle", ".cache")
BAR = 45


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--fallback-only", action="store_true")
    args = ap.parse_args(argv)
    pack = json.load(open(os.path.join(ROOT, "lessons", "water-cycle",
                                       "pack.json"), encoding="utf-8"))
    keys = {s["step"]: (s["say_it"]["answer_key"], s["misconception"])
            for s in pack["steps"]}
    cases = json.load(open(os.path.join(ROOT, "src", "app", "sayit_cases.json"),
                           encoding="utf-8"))
    client = None
    if not args.fallback_only:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.meta.ai/v1",
                        api_key=os.environ["MODEL_API_KEY"])
    passed, hits = 0, 0
    for i, c in enumerate(cases):
        key, misc = keys[c["step"]]
        out, hit = grade(client, c["answer"], key, misc, CACHE_DIR,
                         refresh=args.refresh)
        hits += hit
        ok = out["verdict"] == c["expected"]
        passed += ok
        if not ok or "wrong" in out.get("explanation", "").lower():
            print(f"case{i + 1:02d} step{c['step']} want {c['expected']:7s} "
                  f"got {out['verdict']:7s} {'OK' if ok else 'MISS'}")
        assert "wrong" not in (out.get("hint", "") + out.get("explanation", "")
                               ).lower(), f"case{i + 1}: says 'wrong'"
    print(f"say-it: {passed}/{len(cases)} (bar {BAR}/{len(cases)}), "
          f"{hits} cache hits; never says 'wrong' ok")
    if passed < BAR:
        raise SystemExit("say-it below bar")
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
