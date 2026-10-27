"""State-machine replay: transition table + policy allow-list.

Phase A (no API): every row of replay_turns.json (the spreadsheet's Replay
sheet) is checked against policy.TRANSITIONS via next_state_for. Must be
20/20; any miss means code and sheet disagree.

Phase B (credit-safe): one decide() call per model-resolved event, asserting
the strategy lands inside the allowed set for (state, event). Turn decisions
cache under lessons/water-cycle/.cache/policy_*.json, so reruns are free.
--refresh spends credits again. --fallback-only runs the rule fallback with
no client (no API); then each strategy must equal the first allowed entry.

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

from app.policy import allowed_for, decide, next_state_for

CACHE_DIR = os.path.join(ROOT, "lessons", "water-cycle", ".cache")

STEP = {"step": 2, "step_name": "vapor_rises"}
LEARNER = {"current_step": 2, "world": "dinosaur_valley",
           "mastered": ["evaporation"], "stuck_count": 0, "bored_count": 0}

POLICY_TURNS = [
    ("PRESENT", "stuck"),
    ("SIMPLER", "stuck"),
    ("SIMPLEST", "stuck"),
    ("PRESENT", "bored"),
    ("CHALLENGE", "bored"),
    ("SIMPLER", "bored"),
    ("PRESENT", "explore"),
]


def phase_a(turns):
    passed = 0
    for i, t in enumerate(turns):
        got = next_state_for(t["start"], t["event"])
        ok = got == t["expected"]
        passed += ok
        print(f"turn{i + 1:02d} {t['start']:9s} + {t['event']:16s} "
              f"-> {got:9s} expected {t['expected']:9s} "
              f"{'OK' if ok else 'MISS'}")
    print(f"transitions: {passed}/{len(turns)} (bar {len(turns)}/{len(turns)})")
    return passed == len(turns)


def phase_b(client, refresh, fallback_only):
    passed = 0
    for fsm_state, signal in POLICY_TURNS:
        allowed, _ = allowed_for(fsm_state, signal)
        decision, from_cache = decide(client, signal, STEP, LEARNER,
                                     CACHE_DIR, refresh=refresh,
                                     fsm_state=fsm_state)
        strategy = decision["strategy"]
        ok = (strategy == allowed[0] if fallback_only
              else strategy in allowed)
        passed += ok
        flag = "fallback" if decision.pop("fallback", False) else "model"
        print(f"{fsm_state:9s} + {signal:7s} -> {strategy:17s} "
              f"allowed {allowed} {'OK' if ok else 'MISS'} "
              f"[{flag}{' cached' if from_cache else ''}]")
    print(f"policy: {passed}/{len(POLICY_TURNS)} "
          f"(bar {len(POLICY_TURNS)}/{len(POLICY_TURNS)})")
    return passed == len(POLICY_TURNS)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--fallback-only", action="store_true")
    args = ap.parse_args(argv)
    with open(os.path.join(ROOT, "src", "app", "replay_turns.json"),
              encoding="utf-8") as f:
        turns = json.load(f)
    ok_a = phase_a(turns)
    client = None
    if not args.fallback_only:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.meta.ai/v1",
                        api_key=os.environ["MODEL_API_KEY"])
    ok_b = phase_b(client, args.refresh, args.fallback_only)
    if not (ok_a and ok_b):
        raise SystemExit("replay below bar")
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
