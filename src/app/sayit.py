"""Say-it grading: Muse Spark 1.3 against the step answer key.

grade(client, answer, answer_key, cache_dir=None, refresh=False) returns
{verdict: "ok"|"not_yet", hint, explanation}. The model never says "wrong":
partial answers get "not_yet" plus a kind hint. On any failure (or client
None) a deterministic keyword-overlap fallback answers instead.

Cache rule (credit safety): one file per answer hash. Proof reruns are free.
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.contracts import validate

SAYIT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ok", "not_yet"]},
        "hint": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["verdict", "hint", "explanation"],
    "additionalProperties": False,
}


def rule_fallback(answer, answer_key):
    ideas = [i.strip() for i in
             answer_key.split("Must contain:")[-1].split("Partial")[0].split(";")]
    hits = sum(1 for idea in ideas if any(
        w in answer.lower() for w in idea.lower().split() if len(w) > 3))
    if hits >= 2:
        return {"verdict": "ok", "hint": "",
                "explanation": "That covers it. Well said."}
    partial = answer_key.split("->")[-1].strip() if "->" in answer_key else \
        "Good start. What happens next?"
    return {"verdict": "not_yet", "hint": partial,
            "explanation": "Not yet - keep going."}


def grade(client, answer, answer_key, misconception=None, cache_dir=None,
          refresh=False, model=None):
    model = model or "muse-spark-1.3"
    digest = hashlib.sha256(
        json.dumps({"v": 3, "a": answer, "k": answer_key, "m": misconception,
                    "model": model},
                   sort_keys=True).encode()).hexdigest()[:16]
    cache_path = (os.path.join(cache_dir, f"sayit_{digest}.json")
                  if cache_dir else None)
    if cache_path and os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f), True
    if client is None:
        return rule_fallback(answer, answer_key), False
    try:
        from app.backends import create_structured
        veto = (f"Children often believe this lie: '{misconception}'. "
                f"Any answer stating it gets 'not_yet'." if misconception
                else "")
        out, _ = create_structured(
            client, model,
            ("Grade a child's spoken answer against the answer key. "
             "Verdict 'ok' ONLY if every required idea appears in any "
             "words; a partial answer with one idea missing gets "
             "'not_yet'. " + veto + " Never say 'wrong'. The "
             "explanation is a one-sentence note for the reviewer log and "
             "is never shown to the child; the hint is the only text the "
             "child sees: one kind question leading forward.\n"
             f"Answer key: {answer_key}\nChild: {answer}"),
            SAYIT_SCHEMA, "sayit")
    except Exception:
        out = rule_fallback(answer, answer_key)
        return out, False
    if cache_path:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    return out, False
