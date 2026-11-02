"""Unit tests for the parent report: aggregation, kind check, fallback.

No API calls: model paths stub app.backends.create_structured, and the
report path never touches the network or the disk.

Usage (from repo root): .venv/bin/python src/app/test_report.py
Exit nonzero on failure.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

import app.backends as backends
from app.contracts import PARENT_REPORT_SCHEMA, validate
from app.report import aggregate, generate, kind_check, rule_fallback

COUNT = [0]


def check(cond, msg):
    COUNT[0] += 1
    if not cond:
        raise AssertionError(f"report test failed: {msg}")


ENTRIES = [
    {"kind": "stuck", "step": "Step 1", "title": "Simpler words",
     "world": "dinosaur_valley"},
    {"kind": "stuck", "step": "Step 1", "title": "Asked a grown-up",
     "world": "dinosaur_valley"},
    {"kind": "tap", "step": "Step 1", "title": "Tapped near the lake",
     "world": "dinosaur_valley"},
    {"kind": "tap", "step": "Step 1", "title": "Tapped the lake: correct",
     "world": "dinosaur_valley"},
    {"kind": "say_it", "step": "Step 1", "title": "Said it right",
     "world": "dinosaur_valley"},
    {"kind": "bored", "step": "Step 2", "title": "Made it harder",
     "world": "block_world"},
    {"kind": "tap", "step": "Step 2", "title": "Tapped the cloud: correct",
     "world": "block_world"},
    {"kind": "ready", "step": "Step 3", "title": "Started the check",
     "world": "block_world"},
    {"kind": "fallback", "step": "Step 3", "title": "World fallback",
     "world": "block_world"},
    {"kind": "tap", "step": "Broken", "title": "Tapped the x: correct",
     "world": "block_world"},
    {"kind": "tap", "title": "Tapped the x: correct", "world": "block_world"},
]
CONCEPTS = {1: "evaporation", 2: "condensation", 3: "rain"}
MASTERED = ["evaporation"]

SNAPSHOT = {"entries": ENTRIES, "mastered": MASTERED, "current_step": 3,
            "concepts": CONCEPTS}


def test_aggregate():
    agg = aggregate(ENTRIES, MASTERED, 3, CONCEPTS)
    check(agg["mastered_concepts"] == ["evaporation"], "mastered passthrough")
    by_step = {s["step"]: s for s in agg["stuck_steps"]}
    check(set(by_step) == {1, 2, 3}, "one row per seen step")
    s1 = by_step[1]
    check(s1["concept"] == "evaporation", "concept resolved from map")
    check(s1["stuck_signals"] == 2, "stuck counted per step")
    check(s1["support_flag"] == "grown_up_asked", "grown-up flag detected")
    check(s1["outcome"] == "mastered", "mastered outcome")
    check(by_step[2]["outcome"] == "moved_on", "past unmastered moves on")
    check(by_step[3]["outcome"] == "still_exploring", "current step open")
    check(by_step[2]["stuck_signals"] == 0, "bored is not stuck")
    fit = {w["world"]: w for w in agg["world_fit"]}
    check(fit["dinosaur_valley"] == {"world": "dinosaur_valley",
                                     "checks_passed": 2, "checks_total": 3},
          "world checks counted once each")
    check(fit["block_world"] == {"world": "block_world",
                                 "checks_passed": 1, "checks_total": 1},
          "second world counted")
    print("aggregate ok: steps, flags, outcomes, world fit")


def test_aggregate_names_fallback():
    agg = aggregate(ENTRIES, [], 1, None)
    by_step = {s["step"]: s for s in agg["stuck_steps"]}
    check(by_step[1]["concept"] == "step 1", "concept falls back to step N")
    check(by_step[1]["outcome"] == "still_exploring", "step 1 still open")
    print("aggregate ok: missing concept map")


def test_kind_check():
    clean = {"strengths": ["Tapped with care."],
             "growth_areas": ["Step 2 needed extra explanations."],
             "try_at_home": ["Replay the scene together."]}
    check(kind_check(clean), "kind wording passes")
    for bad in ("Your child is slow.", "Wrong taps again.",
                "Signs of ADHD.", "She keeps failing."):
        dirty = dict(clean, growth_areas=[bad])
        check(not kind_check(dirty), f"judgment caught: {bad}")
    print("kind check ok: clean passes, judgment fails closed")


def test_fallback():
    agg = aggregate(ENTRIES, MASTERED, 3, CONCEPTS)
    first = rule_fallback(agg)
    check(first.get("fallback") is True, "fallback flagged")
    validate(PARENT_REPORT_SCHEMA,
             {k: v for k, v in first.items() if k != "fallback"})
    check(kind_check(first), "template never judges")
    check(rule_fallback(agg) == first, "template deterministic")
    check(any("evaporation" in s for s in first["strengths"]),
          "mastered concept named")
    check(any("grown" in s or "Step 1" in s for s in first["growth_areas"]),
          "stuck step surfaced")
    print("fallback ok: schema-valid, deterministic, kind")


def fake_backend(payload):
    def run(client, model, input_text, schema, name,
            reasoning_effort="low"):
        check("evaporation" in input_text, "facts reach the prompt")
        return dict(payload), True
    return run


def test_generate_paths():
    agg = aggregate(ENTRIES, MASTERED, 3, CONCEPTS)
    good = rule_fallback(agg)
    del good["fallback"]
    real = backends.create_structured
    try:
        backends.create_structured = fake_backend(good)
        out, _ = generate("client", SNAPSHOT, {"age": "7-8"})
        check(out == good, "good model output passes through")
        mean = dict(good, strengths=["Your child is slow at tapping."])
        backends.create_structured = fake_backend(mean)
        out, _ = generate("client", SNAPSHOT)
        check(out.get("fallback") is True, "judgmental output rejected")
        backends.create_structured = fake_backend({"mastered_concepts": []})
        out, _ = generate("client", SNAPSHOT)
        check(out.get("fallback") is True, "invalid schema rejected")
    finally:
        backends.create_structured = real
    out, _ = generate(None, SNAPSHOT)
    check(out.get("fallback") is True, "no client uses the template")
    print("generate ok: passthrough, judgment and schema fall back, offline")
    print(f"report tests ok: {COUNT[0]} assertions")


def main():
    test_aggregate()
    test_aggregate_names_fallback()
    test_kind_check()
    test_fallback()
    test_generate_paths()


if __name__ == "__main__":
    main()
