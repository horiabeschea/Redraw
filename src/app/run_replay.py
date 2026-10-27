"""Run the 20-turn policy replay. Bar: >=18/20 intended strategies.

Turn decisions cache under lessons/water-cycle/.cache/policy_*.json,
so reruns are free. --refresh spends credits again. --fallback-only runs
the rule fallback with no client (no API).

Usage (from repo root):
  set -a; source .env; set +a
  .venv/bin/python src/app/run_replay.py [--refresh] [--fallback-only]
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.policy import decide

CACHE_DIR = os.path.join(ROOT, "lessons", "water-cycle", ".cache")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--fallback-only", action="store_true")
    args = ap.parse_args(argv)
    with open(os.path.join(ROOT, "src", "app", "replay_turns.json"),
              encoding="utf-8") as f:
        turns = json.load(f)
    client = None
    if not args.fallback_only:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.meta.ai/v1",
                        api_key=os.environ["MODEL_API_KEY"])
    hits, passed = 0, 0
    for i, t in enumerate(turns):
        decision, from_cache = decide(client, t["signal"], t["step"],
                                     t["learner"], CACHE_DIR,
                                     refresh=args.refresh)
        hits += from_cache
        ok = decision["strategy"] == t["expected"]
        passed += ok
        flag = "fallback" if decision.pop("fallback", False) else "model"
        print(f"turn{i + 1:02d} {t['signal']:7s} -> {decision['strategy']:17s} "
              f"expected {t['expected']:17s} {'OK' if ok else 'MISS'} [{flag}]")
    print(f"replay: {passed}/{len(turns)} (bar 18/20), {hits} cache hits")
    if passed < 18:
        raise SystemExit("replay below bar")
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
