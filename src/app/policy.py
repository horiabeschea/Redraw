"""Adaptation policy: per-step state machine + Muse Spark 1.3, rule fallback.

The frontend owns the machine state per step (PRESENT, SIMPLER, SIMPLEST,
SUPPORT, CHALLENGE, EXPLORE, TAP_CHECK, SAY_CHECK) and sends it with each
call. The rules below produce the allowed strategies for (state, signal);
Spark picks inside that set, and any pick outside it is rejected in favor of
the first allowed strategy. Tap/say outcomes are fully deterministic (one
allowed member) and are executed client-side without a model call.

decide(client, signal, step, learner, cache_dir=None, refresh=False,
       model=None, fsm_state="PRESENT")
returns (decision, from_cache). On any model failure (or when client is
None) it falls back to the first allowed strategy, flagged "fallback": true.

Cache rule (credit safety): one cache file per (signal, step, learner,
fsm_state, model) input hash. Replay hits cache; only new inputs spend.
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.contracts import ADAPTATION_DECISION_SCHEMA, validate

MODEL = "muse-spark-1.3"

STRATEGIES = ADAPTATION_DECISION_SCHEMA["properties"]["strategy"]["enum"]

# (state, event) -> {to, allowed, note}. Mirrors
# Redraw_policy_state_machine.xlsx (Transitions sheet, v2 with back_to_*
# exit events). allowed = strategies Spark may pick, in preference order;
# None means the event is fully deterministic and resolved client-side with
# no model call.
TRANSITIONS = {
    ("PRESENT", "stuck"): {"to": "SIMPLER", "allowed": ["simplify_language"],
                           "note": "stuck+1; simplify_level=1"},
    ("SIMPLER", "stuck"): {"to": "SIMPLEST",
                           "allowed": ["redraw_simpler", "simplify_max"],
                           "note": "stuck+1; simplify_level=2"},
    ("SIMPLEST", "stuck"): {"to": "SUPPORT", "allowed": ["offer_support"],
                            "note": "stuck+1; flag step for parent report"},
    ("PRESENT", "bored"): {"to": "CHALLENGE", "allowed": ["raise_challenge"],
                           "note": "bored+1; challenge_level=1"},
    ("CHALLENGE", "bored"): {"to": "TAP_CHECK",
                             "allowed": ["switch_to_tap_game"],
                             "note": "bored+1; straight to the check"},
    ("SIMPLER", "bored"): {"to": "EXPLORE",
                           "allowed": ["switch_to_tap_game"],
                           "note": "bored while simplified: variety, not harder"},
    ("SIMPLEST", "bored"): {"to": "EXPLORE",
                            "allowed": ["switch_to_tap_game"],
                            "note": "bored while simplified: variety, not harder"},
    ("CHALLENGE", "stuck"): {"to": "SIMPLER",
                             "allowed": ["simplify_language"], "note": ""},
    ("EXPLORE", "stuck"): {"to": "SIMPLER",
                           "allowed": ["simplify_language"], "note": ""},
    ("EXPLORE", "bored"): {"to": "CHALLENGE",
                           "allowed": ["raise_challenge"], "note": ""},
    ("TAP_CHECK", "tap_correct"): {"to": "SAY_CHECK", "allowed": None,
        "note": "ADVANCE instead if the step has no say-it; misses=0"},
    ("TAP_CHECK", "tap_miss"): {"to": "TAP_CHECK", "allowed": None,
                                "note": "misses+1; show hint"},
    ("TAP_CHECK", "tap_miss_limit"): {"to": "SAY_CHECK", "allowed": None,
        "note": "reveal answer; log 'reveal'; continue"},
    ("SAY_CHECK", "say_ok"): {"to": "ADVANCE", "allowed": None, "note": ""},
    ("SAY_CHECK", "say_partial"): {"to": "SAY_CHECK", "allowed": None,
                                   "note": "say_tries+1"},
    ("SAY_CHECK", "say_partial_limit"): {"to": "ADVANCE", "allowed": None,
                                         "note": "say_tries+1; move on"},
    ("ADVANCE", "next"): {"to": "PRESENT", "allowed": None,
                          "note": "reset counters; carry-over; prefetched step"},
    ("SUPPORT", "next"): {"to": "ADVANCE", "allowed": None, "note": "move on"},
    ("PRESENT", "ready"): {"to": "TAP_CHECK", "allowed": None,
                           "note": "Got-it button, voice, or object tap; not capped"},
    ("SIMPLER", "ready"): {"to": "TAP_CHECK", "allowed": None,
                           "note": "Got-it button, voice, or object tap; not capped"},
    ("SIMPLEST", "ready"): {"to": "TAP_CHECK", "allowed": None,
                            "note": "Got-it button, voice, or object tap; not capped"},
}

# Teaching states from which explore opens the detour.
for _s in ("PRESENT", "SIMPLER", "SIMPLEST", "CHALLENGE",
           "TAP_CHECK", "SAY_CHECK"):
    TRANSITIONS[(_s, "explore")] = {"to": "EXPLORE",
                                   "allowed": ["switch_to_tap_game"],
                                   "note": "child-led detour; no grading"}

# EXPLORE exit: back_to_<origin> returns to the entry state, counters
# unchanged. The client resolves "back" to the recorded origin event.
for _s in ("PRESENT", "SIMPLER", "SIMPLEST", "CHALLENGE",
           "TAP_CHECK", "SAY_CHECK"):
    TRANSITIONS[("EXPLORE", f"back_to_{_s}")] = {
        "to": _s, "allowed": None, "note": "counters unchanged"}

# All nine sheet states; used by the coverage test.
STATES = ("PRESENT", "SIMPLER", "SIMPLEST", "SUPPORT", "CHALLENGE",
          "EXPLORE", "TAP_CHECK", "SAY_CHECK", "ADVANCE")

# Gap-fills: the sheet is silent here; values are deliberate, not sheet rows.
# Kept explicit so the unit test can pin them separately.
GAP_FILLS = {
    ("CHALLENGE", "stuck"): {"to": "SIMPLER",
                             "allowed": ["simplify_language"]},
    ("EXPLORE", "stuck"): {"to": "SIMPLER",
                           "allowed": ["simplify_language"]},
    ("EXPLORE", "bored"): {"to": "CHALLENGE",
                           "allowed": ["raise_challenge"]},
    ("EXPLORE", "explore"): {"to": "EXPLORE",
                             "allowed": ["switch_to_tap_game"]},
    ("CHALLENGE", "ready"): {"to": "TAP_CHECK", "allowed": None},
    ("CHALLENGE", "say_ok"): {"to": "ADVANCE", "allowed": None},
    ("CHALLENGE", "say_partial"): {"to": "CHALLENGE", "allowed": None},
    ("CHALLENGE", "say_partial_limit"): {"to": "ADVANCE", "allowed": None},
}
TRANSITIONS.update(GAP_FILLS)

# Events resolved by a model call (Spark picks inside allowed).
POLICY_EVENTS = ("stuck", "bored", "explore")


def allowed_for(fsm_state, signal):
    """(allowed strategies, next state) for (state, signal)."""
    hit = TRANSITIONS.get((fsm_state, signal))
    if hit and hit["allowed"]:
        return list(hit["allowed"]), hit["to"]
    if hit:
        return [], hit["to"]
    return ["simplify_language"], fsm_state


def next_state_for(fsm_state, event, has_sayit=True):
    """Next machine state for (state, event)."""
    if (fsm_state, event) == ("TAP_CHECK", "tap_correct") and not has_sayit:
        return "ADVANCE"
    hit = TRANSITIONS.get((fsm_state, event))
    return hit["to"] if hit else fsm_state


def rule_fallback(signal, step, learner=None, allowed=None):
    learner = learner or {}
    allowed = allowed or ["simplify_language"]
    return {"signal": signal, "strategy": allowed[0],
            "target_concept": step.get("step_name", "water cycle"),
            "reason": f"Fallback rule for {signal}.",
            "fallback": True}


def decide(client, signal, step, learner, cache_dir=None, refresh=False,
           model=None, fsm_state="PRESENT"):
    model = model or MODEL
    allowed, _ = allowed_for(fsm_state, signal)
    if signal not in POLICY_EVENTS or not allowed:
        allowed = ["simplify_language"]
    key = json.dumps({"signal": signal, "step": step, "learner": learner,
                      "fsm_state": fsm_state, "model": model}, sort_keys=True)
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    cache_path = (os.path.join(cache_dir, f"policy_{digest}.json")
                  if cache_dir else None)
    if cache_path and os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            decision = json.load(f)
        decision["strategy"] = (decision["strategy"] if decision.get(
            "strategy") in allowed else allowed[0])
        return decision, True
    if client is None:
        decision = rule_fallback(signal, step, learner, allowed)
        return decision, False
    try:
        from app.backends import create_structured
        decision, _ = create_structured(
            client, model,
            ("You are the adaptation policy for a child's water-cycle "
             "lesson. The child steers with explicit signals only.\n"
             f"Signal: {signal}\nStep: {json.dumps(step)}\n"
             f"Learner: {json.dumps(learner)}\n"
             f"Machine state: {fsm_state}\n"
             f"Pick exactly one of these strategies: {', '.join(allowed)}. "
             "Reason in one plain sentence."),
            ADAPTATION_DECISION_SCHEMA, "decision")
        validate(ADAPTATION_DECISION_SCHEMA, decision)
    except Exception:
        decision = rule_fallback(signal, step, learner, allowed)
        return decision, False
    if decision.get("strategy") not in allowed:
        decision = rule_fallback(signal, step, learner, allowed)
        decision["reason"] = ("Model picked outside the allowed set, "
                              "used first allowed strategy.")
        return decision, False
    decision.pop("fallback", None)
    if cache_path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(decision, f, indent=2)
    return decision, False
