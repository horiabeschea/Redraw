"""Adaptation policy: Muse Spark 1.3 with structured output, rule fallback.

decide(client, signal, step, learner, cache_dir=None, refresh=False)
returns an AdaptationDecision dict. On any model failure (or when client is
None) it falls back to deterministic rules, flagged with "fallback": true.

Cache rule (credit safety): one cache file per (signal, step, strategy
context) input hash. Replay hits cache; only new inputs spend credits.
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


def rule_fallback(signal, step, learner=None):
    learner = learner or {}
    if signal == "stuck":
        strategy = ("redraw_simpler" if step.get("stuck_count", 0) >= 2
                    else "simplify_language")
    elif signal == "bored":
        strategy = ("raise_challenge" if learner.get("bored_count", 0) >= 2
                    else "switch_to_tap_game")
    else:
        strategy = "advance"
    return {"signal": signal, "strategy": strategy,
            "target_concept": step.get("step_name", "water cycle"),
            "reason": f"Fallback rule for {signal}.",
            "fallback": True}


def decide(client, signal, step, learner, cache_dir=None, refresh=False):
    key = json.dumps({"signal": signal, "step": step, "learner": learner},
                     sort_keys=True)
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    cache_path = (os.path.join(cache_dir, f"policy_{digest}.json")
                  if cache_dir else None)
    if cache_path and os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f), True
    if client is None:
        return rule_fallback(signal, step, learner), False
    try:
        resp = client.responses.create(
            model=MODEL,
            reasoning={"effort": "low"},
            input=("You are the adaptation policy for a child's water-cycle "
                    "lesson. The child steers with explicit signals only.\n"
                    f"Signal: {signal}\nStep: {json.dumps(step)}\n"
                    f"Learner: {json.dumps(learner)}\n"
                    "Pick the strategy that fits: stuck needs easier "
                    "(simplify_language first, redraw_simpler if stuck "
                    "persists); the first bored signal gets "
                    "switch_to_tap_game, but bored_count 2 or more means "
                    "raise_challenge; got_it advances. "
                    "Reason in one plain sentence."),
            text={"format": {"type": "json_schema", "name": "decision",
                             "strict": True,
                             "schema": ADAPTATION_DECISION_SCHEMA}},
        )
        decision = json.loads(resp.output_text)
        validate(ADAPTATION_DECISION_SCHEMA, decision)
    except Exception:
        decision = rule_fallback(signal, step, learner)
        return decision, False
    if cache_path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(decision, f, indent=2)
    return decision, False
