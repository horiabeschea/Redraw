"""Validate the lesson pack and sample decisions against the contracts.

Usage (from repo root): .venv/bin/python src/app/check_contracts.py
Exit nonzero on the first violation. No API calls.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.contracts import (ADAPTATION_DECISION_SCHEMA, LEARNER_STATE_SCHEMA,
                            validate)
from build_lesson_pack import PACK_SCHEMA


def main():
    pack_path = os.path.join(ROOT, "lessons", "water-cycle", "pack.json")
    with open(pack_path, encoding="utf-8") as f:
        pack = json.load(f)
    validate(PACK_SCHEMA, {"steps": pack["steps"]})
    print(f"pack ok: {pack_path} ({len(pack['steps'])} steps)")

    dec_path = os.path.join(ROOT, "src", "app", "sample_decisions.json")
    with open(dec_path, encoding="utf-8") as f:
        decisions = json.load(f)
    seen = set()
    for i, d in enumerate(decisions):
        validate(ADAPTATION_DECISION_SCHEMA, d)
        seen.add(d["strategy"])
    print(f"decisions ok: {dec_path} ({len(decisions)} samples)")

    learner = {"current_step": 1, "world": "dinosaur_valley", "mastered": [],
               "stuck_count": 0, "bored_count": 0}
    validate(LEARNER_STATE_SCHEMA, learner)
    print("learner-state ok: blank initial state validates")

    missing = (set(ADAPTATION_DECISION_SCHEMA["properties"]["strategy"]["enum"])
               - seen)
    if missing:
        raise ValueError(f"strategies without a sample: {sorted(missing)}")
    print("coverage ok: every strategy has a sample decision")


if __name__ == "__main__":
    sys.exit(main())
