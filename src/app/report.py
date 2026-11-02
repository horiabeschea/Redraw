"""Parent report: session aggregates plus Muse Spark 1.3 summary.

aggregate(entries, mastered, current_step) folds the lesson page's timeline
entries ({kind, step, title, world}) into per-step counts and per-world
check outcomes. No transcripts cross this boundary: only outcome counts,
the mastered list, and the profile reach the model.

generate(client, snapshot, profile, model) asks Spark for the semi-structured
report (facts plus kind, behavior-framed suggestions) via create_structured,
validates it, and runs the banned-word check. Any failure -- no client, model
error, schema violation, judgmental wording -- falls back to the
deterministic template from rule_fallback, flagged "fallback": True.

Like the policy and say-it paths, the report is never cached: every session
payload is unique. Nothing is written to disk.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.contracts import PARENT_REPORT_SCHEMA, validate

MODEL = "muse-spark-1.3"
MAX_ENTRIES = 200

# Wording that judges the child instead of describing the lesson, plus
# anything resembling a diagnosis. Matched case-insensitively against the
# report's free-text fields; on a hit the model output is discarded in
# favor of the template (fail closed).
BANNED_WORDS = ("wrong", "bad", "slow", "lazy", "stupid", "dumb", "behind",
                "fail", "disorder", "diagnos", "adhd", "autis", "disab")


def _step_no(entry):
    try:
        return int(str(entry.get("step", "")).replace("Step ", ""))
    except (ValueError, TypeError):
        return None


def _tap_outcome(title):
    t = title or ""
    if ": correct" in t or t.startswith("Found the"):
        return "ok"
    if "missed three times" in t or t.startswith("Tapped near"):
        return "miss"
    return None


def _say_outcome(title):
    t = title or ""
    if t.startswith("Said it right"):
        return "ok"
    if t.startswith(("Gave a hint", "Moved on", "Answer kept")):
        return "try"
    return None


def _world_hit(worlds, world, passed):
    if not world:
        return
    w = worlds.setdefault(world, {"passed": 0, "total": 0})
    w["total"] += 1
    if passed:
        w["passed"] += 1


def aggregate(entries, mastered, current_step, concepts=None):
    """Fold raw timeline entries into per-step and per-world counts.

    concepts maps step number -> step_name so mastered steps resolve to
    their concept; without it steps fall back to "step N".
    """
    steps = {}
    worlds = {}
    names = {int(k): v for k, v in dict(concepts or {}).items()}

    def bucket(step):
        return steps.setdefault(step, {
            "step": step, "stuck": 0, "bored": 0,
            "taps_ok": 0, "taps_miss": 0, "say_ok": 0, "say_try": 0,
            "worlds": set(), "support": False})

    for entry in (entries or [])[:MAX_ENTRIES]:
        step = _step_no(entry)
        if step is None:
            continue
        bkt = bucket(step)
        kind = entry.get("kind", "")
        title = entry.get("title", "")
        world = entry.get("world")
        if world:
            bkt["worlds"].add(world)
        if kind == "stuck":
            bkt["stuck"] += 1
            if title == "Asked a grown-up":
                bkt["support"] = True
        elif kind == "bored":
            bkt["bored"] += 1
        elif kind == "tap":
            out = _tap_outcome(title)
            if out == "ok":
                bkt["taps_ok"] += 1
                _world_hit(worlds, world, True)
            elif out == "miss":
                bkt["taps_miss"] += 1
                _world_hit(worlds, world, False)
        elif kind == "say_it":
            out = _say_outcome(title)
            if out == "ok":
                bkt["say_ok"] += 1
                _world_hit(worlds, world, True)
            elif out == "try":
                bkt["say_try"] += 1
                _world_hit(worlds, world, False)

    mastered = list(mastered or [])
    stuck_steps = []
    for step in sorted(steps):
        bkt = steps[step]
        concept = names.get(step, f"step {step}")
        if concept in mastered:
            outcome = "mastered"
        elif step >= (current_step or 1):
            outcome = "still_exploring"
        else:
            outcome = "moved_on"
        stuck_steps.append({
            "step": step,
            "concept": concept,
            "stuck_signals": bkt["stuck"],
            "support_flag": ("grown_up_asked" if bkt["support"] else "none"),
            "outcome": outcome,
        })
    world_fit = [{"world": w,
                  "checks_passed": worlds[w]["passed"],
                  "checks_total": worlds[w]["total"]}
                 for w in sorted(worlds)]
    return {"mastered_concepts": mastered,
            "stuck_steps": stuck_steps,
            "world_fit": world_fit}


def _kind_text(report):
    return " ".join(report.get("strengths", []) +
                    report.get("growth_areas", []) +
                    report.get("try_at_home", [])).lower()


def kind_check(report):
    """True when no free-text field judges the child."""
    text = _kind_text(report)
    return not any(w in text for w in BANNED_WORDS)


def rule_fallback(agg):
    """Deterministic offline summary from the aggregates. Never judges."""
    mastered = agg["mastered_concepts"]
    stuck = [s for s in agg["stuck_steps"] if s["stuck_signals"] > 0]
    strengths = ([f"Mastered {len(mastered)} "
                  f"{'concept' if len(mastered) == 1 else 'concepts'}: "
                  f"{', '.join(mastered)}."] if mastered else
                 ["Finished the lesson run; every completed check is logged."])
    growth = ([f"Step {s['step']} needed {s['stuck_signals']} "
               f"{'extra explanation' if s['stuck_signals'] == 1 else 'extra explanations'} "
               "before moving on; replaying that scene together helps."
               for s in stuck] or
              ["No step needed extra explanations this time."])
    ideas = agg["world_fit"]
    best = max(ideas, key=lambda w: (w["checks_total"] > 0,
                                     w["checks_passed"] / max(w["checks_total"], 1)),
               default=None)
    if best and best["checks_total"]:
        growth.append(f"Checks clicked most in the {best['world']} world "
                      f"({best['checks_passed']}/{best['checks_total']}); "
                      "more scenes there reinforce the pattern.")
    report = {"mastered_concepts": mastered,
              "stuck_steps": agg["stuck_steps"],
              "world_fit": agg["world_fit"],
              "strengths": strengths,
              "growth_areas": growth,
              "try_at_home": [
                  "Replay the stuck scene and let your child narrate it."],
              "fallback": True}
    return report


def generate(client, snapshot, profile=None, model=None):
    """One Spark call for the parent report, or the offline template."""
    profile = profile or {}
    model = model or MODEL
    agg = aggregate(snapshot.get("entries"), snapshot.get("mastered"),
                    snapshot.get("current_step", 1),
                    snapshot.get("concepts"))
    if client is None:
        return rule_fallback(agg), False
    try:
        from app.backends import create_structured
        out, _ = create_structured(
            client, model,
            ("Write a short parent report for a child's water-cycle lesson. "
             "Describe what happened in the lesson, never what the child is: "
             "no judgmental words (wrong, bad, slow, lazy), no diagnoses, "
             "no medical claims. Growth areas name lesson moments that needed "
             "extra explanations; every growth area needs one concrete "
             "try-at-home activity.\n"
             f"Session facts: {json.dumps(agg)}\n"
             f"Reading level: age {profile.get('age', '7-8')}, "
             f"sentence tier {profile.get('level', 'medium')}. "
             "Keep each sentence short."),
            PARENT_REPORT_SCHEMA, "parent_report")
        validate(PARENT_REPORT_SCHEMA, out)
        if not kind_check(out):
            raise ValueError("report wording failed the kind check")
    except Exception:  # noqa: BLE001 (any failure -> offline template)
        return rule_fallback(agg), False
    return out, False
