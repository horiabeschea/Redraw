"""Unit tests for the lesson state machine: every possible transition.

Mirrors Redraw_policy_state_machine.xlsx (Transitions sheet, v2): each
sheet row is asserted as (start state, event) -> next state, plus the
allowed strategy set for model-resolved events. Deliberate gap-fills
(policy.GAP_FILLS, where the sheet is silent) are pinned separately from
sheet rows. No API calls: model paths use a stubbed structured-output
backend, cache tests use a temporary directory.

Usage (from repo root): .venv/bin/python src/app/test_policy.py
Exit nonzero on failure.
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

import app.backends as backends
from app.contracts import ADAPTATION_DECISION_SCHEMA
from app.policy import (GAP_FILLS, STATES, TRANSITIONS, allowed_for, decide,
                        next_state_for)

STRATEGY_ENUM = ADAPTATION_DECISION_SCHEMA["properties"]["strategy"]["enum"]

STEP = {"step": 2, "step_name": "vapor_rises"}
LEARNER = {"current_step": 2, "world": "dinosaur_valley",
           "mastered": ["evaporation"], "stuck_count": 0, "bored_count": 0}

# Every Transitions-sheet row: (start, event, next state, allowed or None).
SHEET_ROWS = [
    ("PRESENT", "stuck", "SIMPLER", ["simplify_language"]),
    ("SIMPLER", "stuck", "SIMPLEST", ["redraw_simpler", "simplify_max"]),
    ("SIMPLEST", "stuck", "SUPPORT", ["offer_support"]),
    ("PRESENT", "bored", "CHALLENGE", ["raise_challenge"]),
    ("CHALLENGE", "bored", "TAP_CHECK", ["switch_to_tap_game"]),
    ("SIMPLER", "bored", "EXPLORE", ["switch_to_tap_game"]),
    ("SIMPLEST", "bored", "EXPLORE", ["switch_to_tap_game"]),
    ("PRESENT", "explore", "EXPLORE", ["switch_to_tap_game"]),
    ("SIMPLER", "explore", "EXPLORE", ["switch_to_tap_game"]),
    ("SIMPLEST", "explore", "EXPLORE", ["switch_to_tap_game"]),
    ("CHALLENGE", "explore", "EXPLORE", ["switch_to_tap_game"]),
    ("TAP_CHECK", "explore", "EXPLORE", ["switch_to_tap_game"]),
    ("SAY_CHECK", "explore", "EXPLORE", ["switch_to_tap_game"]),
    ("TAP_CHECK", "tap_correct", "SAY_CHECK", None),
    ("TAP_CHECK", "tap_miss", "TAP_CHECK", None),
    ("TAP_CHECK", "tap_miss_limit", "SAY_CHECK", None),
    ("SAY_CHECK", "say_ok", "ADVANCE", None),
    ("SAY_CHECK", "say_partial", "SAY_CHECK", None),
    ("SAY_CHECK", "say_partial_limit", "ADVANCE", None),
    ("ADVANCE", "next", "PRESENT", None),
    ("SUPPORT", "next", "ADVANCE", None),
    ("PRESENT", "ready", "TAP_CHECK", None),
    ("SIMPLER", "ready", "TAP_CHECK", None),
    ("SIMPLEST", "ready", "TAP_CHECK", None),
    ("EXPLORE", "back_to_PRESENT", "PRESENT", None),
    ("EXPLORE", "back_to_SIMPLER", "SIMPLER", None),
    ("EXPLORE", "back_to_SIMPLEST", "SIMPLEST", None),
    ("EXPLORE", "back_to_CHALLENGE", "CHALLENGE", None),
    ("EXPLORE", "back_to_TAP_CHECK", "TAP_CHECK", None),
    ("EXPLORE", "back_to_SAY_CHECK", "SAY_CHECK", None),
]

# Deliberate extras where the sheet is silent (mirrored in app.js FSM_NEXT).
GAP_ROWS = [
    ("CHALLENGE", "stuck", "SIMPLER", ["simplify_language"]),
    ("EXPLORE", "stuck", "SIMPLER", ["simplify_language"]),
    ("EXPLORE", "bored", "CHALLENGE", ["raise_challenge"]),
    ("EXPLORE", "explore", "EXPLORE", ["switch_to_tap_game"]),
    ("CHALLENGE", "ready", "TAP_CHECK", None),
    ("CHALLENGE", "say_ok", "ADVANCE", None),
    ("CHALLENGE", "say_partial", "CHALLENGE", None),
    ("CHALLENGE", "say_partial_limit", "ADVANCE", None),
]

COUNT = [0]


def check(cond, label):
    COUNT[0] += 1
    assert cond, f"FAIL: {label}"


def fake_backend(answer):
    def run(client, model, prompt, schema, name):
        return dict(answer), {"model": model}
    return run


def main():
    real = backends.create_structured
    try:
        # 1. Every sheet row resolves to the specified next state + allowed.
        for start, event, to, allowed in SHEET_ROWS:
            check(next_state_for(start, event) == to,
                  f"{start}+{event} -> {to}")
            got_allowed, got_to = allowed_for(start, event)
            check(got_to == to, f"{start}+{event} allowed_for state")
            if allowed is None:
                check(got_allowed == [], f"{start}+{event} deterministic")
            else:
                check(got_allowed == allowed, f"{start}+{event} allowed set")
                check(set(allowed) <= set(STRATEGY_ENUM),
                      f"{start}+{event} allowed in enum")
        print(f"sheet rows ok: {len(SHEET_ROWS)}/30 transitions")

        # 2. Gap-fills are exactly the documented set, nothing more or less.
        check(set(GAP_FILLS) == {(s, e) for s, e, _, _ in GAP_ROWS},
              "gap-fill keys pinned")
        for start, event, to, allowed in GAP_ROWS:
            check(next_state_for(start, event) == to,
                  f"gap {start}+{event} -> {to}")
            got_allowed, _ = allowed_for(start, event)
            check((got_allowed or []) == (allowed or []),
                  f"gap {start}+{event} allowed")
        print(f"gap-fills ok: {len(GAP_ROWS)} documented extras")

        # 3. Unknown states/events fall back safely (stay, simplify words).
        check(next_state_for("BOGUS", "stuck") == "BOGUS", "unknown state stays")
        check(next_state_for("PRESENT", "bogus") == "PRESENT",
              "unknown event stays")
        check(allowed_for("BOGUS", "stuck") == (["simplify_language"], "BOGUS"),
              "unknown state default")
        check(next_state_for("TAP_CHECK", "tap_correct", has_sayit=False)
              == "ADVANCE", "tap_correct without say-it advances")
        print("defaults ok: unknown input never leaves the machine")

        # 4. All nine sheet states appear as a source or destination.
        covered = {s for k in TRANSITIONS for s in (k[0], TRANSITIONS[k]["to"])}
        check(set(STATES) <= covered, "all nine states covered")
        check(len(STATES) == 9, "nine states")
        print("states ok: 9/9 covered")

        # 5. Rule fallback returns the first allowed strategy, flagged.
        policy_rows = [(s, e) for s, e, _, a in SHEET_ROWS + GAP_ROWS
                       if a]
        check(len(policy_rows) == 17, "17 model-resolved combinations")
        with tempfile.TemporaryDirectory() as tmp:
            for start, event in policy_rows:
                allowed, _ = allowed_for(start, event)
                d, cached = decide(None, event, STEP, LEARNER, tmp,
                                   fsm_state=start)
                check(d["strategy"] == allowed[0] and not cached
                      and d.get("fallback") is True,
                      f"fallback {start}+{event} -> {allowed[0]}")
        print(f"fallback ok: {len(policy_rows)}/17 first-allowed")

        # 6. Model paths: allowed caches, disallowed/invalid falls back.
        good = {"signal": "stuck", "strategy": "simplify_max",
                "target_concept": "vapor_rises", "reason": "One idea only."}
        with tempfile.TemporaryDirectory() as tmp:
            backends.create_structured = fake_backend(good)
            d, cached = decide("client", "stuck", STEP, LEARNER, tmp,
                               fsm_state="SIMPLER")
            check(d["strategy"] == "simplify_max" and not cached,
                  "model pick inside allowed")
            files = os.listdir(tmp)
            check(len(files) == 1, "model decision cached to one file")
            d2, cached2 = decide(None, "stuck", STEP, LEARNER, tmp,
                                 fsm_state="SIMPLER")
            check(cached2 and d2["strategy"] == "simplify_max",
                  "replay hits cache, no client needed")
            backends.create_structured = fake_backend(
                {**good, "strategy": "raise_challenge"})
            before = set(os.listdir(tmp))
            d3, cached3 = decide("client", "stuck", STEP, LEARNER, tmp,
                                 refresh=True, fsm_state="SIMPLER")
            check(d3["strategy"] == "redraw_simpler" and not cached3
                  and d3.get("fallback") is True
                  and set(os.listdir(tmp)) == before,
                  "disallowed pick rejected, not cached")
            backends.create_structured = fake_backend({"strategy": "advance"})
            d4, _ = decide("client", "stuck", STEP, LEARNER, tmp,
                           refresh=True, fsm_state="SIMPLER")
            check(d4.get("fallback") is True, "invalid schema falls back")
            backends.create_structured = fake_backend(
                {**good, "strategy": "simplify_language"})
            decide("client", "stuck", STEP, LEARNER, tmp, fsm_state="PRESENT")
            check(len(os.listdir(tmp)) == 2, "cache keyed by fsm state")
        print("model paths ok: cache, reject, invalid, keying")
    finally:
        backends.create_structured = real
    print(f"policy tests ok: {COUNT[0]} assertions")


if __name__ == "__main__":
    main()
