"""Verifier pass: a second Muse Wonder call checks every pack analogy for
scientific accuracy against the brief's FACTS.

Cache rule (credit safety): lessons/water-cycle/.cache/verifier_raw.json
holds the FULL raw response. On cache hit there is NO API call.
Use --refresh to spend credits again deliberately.

Usage (from repo root):
  set -a; source .env; set +a
  .venv/bin/python src/verify_pack.py [--refresh]
"""

import argparse
import json
import os
import sys

from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LESSON_DIR = os.path.join(ROOT, "lessons", "water-cycle")
CACHE_PATH = os.path.join(LESSON_DIR, ".cache", "verifier_raw.json")

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer", "minimum": 1, "maximum": 5},
                    "accurate": {"type": "string",
                                 "enum": ["yes", "no", "unsure"]},
                    "issue": {"type": "string"},
                },
                "required": ["step", "accurate", "issue"],
                "additionalProperties": False,
            },
            "minItems": 5,
            "maxItems": 5,
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


def build_prompt(pack):
    lines = ["You are a science accuracy checker for a children's lesson.",
             "FACTS (ground truth, from the lesson brief):"]
    with open(os.path.join(LESSON_DIR, "brief.md"), encoding="utf-8") as f:
        brief = f.read()
    facts = brief.split("FACTS (ground truth)")[1].split(
        "INTEREST WORLDS")[0].strip()
    lines.append(facts)
    lines.append("ANALOGIES TO CHECK (one block per step):")
    for s in pack["steps"]:
        lines.append(f"Step {s['step']} ({s['step_name']}): "
                     f"caption: {s['caption']}")
        for world, text in s["analogies"].items():
            lines.append(f"  [{world}] {text}")
    lines.append("For each step, say whether its analogies state anything "
                 "untrue about water, heat or clouds. If unsure, say "
                 "'unsure' and explain in 'issue'. Return only JSON.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    with open(os.path.join(LESSON_DIR, "pack.json"), encoding="utf-8") as f:
        pack = json.load(f)
    if os.path.exists(CACHE_PATH) and not args.refresh:
        with open(CACHE_PATH, encoding="utf-8") as f:
            parsed = json.load(f)["parsed"]
        print(f"cache hit: {CACHE_PATH} (no API call)")
    else:
        print("cache miss: calling muse-wonder-1.0 verifier ...")
        client = OpenAI(base_url="https://api.meta.ai/v1",
                        api_key=os.environ["MODEL_API_KEY"])
        resp = client.responses.create(
            model="muse-wonder-1.0",
            reasoning={"effort": "medium"},
            input=build_prompt(pack),
            text={"format": {"type": "json_schema", "name": "verdicts",
                             "strict": False, "schema": VERDICT_SCHEMA}},
        )
        parsed = json.loads(resp.output_text)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"response": json.loads(resp.model_dump_json()),
                       "parsed": parsed}, f, indent=2)
        print(f"cached full raw response: {CACHE_PATH}")
        if resp.usage is not None:
            print(f"usage: in={resp.usage.input_tokens} "
                  f"out={resp.usage.output_tokens} "
                  f"total={resp.usage.total_tokens}")
    for v in parsed["verdicts"]:
        print(f"step{v['step']}: {v['accurate']} - {v['issue']}")
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
