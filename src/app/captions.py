"""Setup-time captions: rewrite pack captions to the child's level.

One structured Muse Spark 1.3 call rewrites all 5 steps (standard +
simpler caption) from the lesson core for a setup profile:

  {"age_band", "max_words_per_sentence", "longest_sentence",
   "new_terms_per_step", "worlds", "calm"}

Code checks (no second model): sentence word limits, glossary-term count
never worse than the core and within the brief cap, and the step's key
term still present. Retry once, then fall back to the cached core text.

Cache: .cache/captions_<pack-version>_<level>_<terms>.json, so reruns and
replays cost nothing. The lesson version is a hash of the pack core, so a
pack edit never reuses stale captions.
"""

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

LESSON_DIR = os.path.join(ROOT, "lessons", "water-cycle")
CACHE_DIR = os.path.join(LESSON_DIR, ".cache")

LEVELS = {
    "short": {"max_words_per_sentence": 6, "longest_sentence": 6},
    "medium": {"max_words_per_sentence": 10, "longest_sentence": 10},
    "longer": {"max_words_per_sentence": 14, "longest_sentence": 14},
}

GLOSSARY = ["water vapor", "evaporation", "condensation", "precipitation",
            "collection", "vapor"]

BANNED = ["invisible air", "water air", "sucks up", "suck up",
          "disappears", "vanishes"]

CAPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "captions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer", "minimum": 1, "maximum": 5},
                    "caption": {"type": "string"},
                    "simpler_caption": {"type": "string"},
                },
                "required": ["step", "caption", "simpler_caption"],
                "additionalProperties": False,
            },
            "minItems": 5,
            "maxItems": 5,
        },
    },
    "required": ["captions"],
    "additionalProperties": False,
}


def pack_version(pack):
    core = json.dumps([{"step": s["step"], "step_name": s["step_name"],
                        "caption": s["caption"],
                        "simpler_caption": s["simpler_caption"]}
                       for s in pack["steps"]], sort_keys=True)
    return hashlib.sha256(core.encode()).hexdigest()[:8]


def profile_for(level, terms, worlds=None, age_band="7-8", calm=True):
    lv = LEVELS[level]
    return {"age_band": age_band,
            "max_words_per_sentence": lv["max_words_per_sentence"],
            "longest_sentence": lv["longest_sentence"],
            "new_terms_per_step": terms,
            "worlds": worlds or ["dinosaur_valley", "block_world"],
            "calm": calm}


def sentences(text):
    return [m.strip() for m in re.split(r"[.!?]+", text) if m.strip()]


def glossary_hits(text):
    lowered = " " + re.sub(r"[^a-z ]", " ", text.lower()) + " "
    lowered = re.sub(r"\s+", " ", lowered)
    return {g for g in GLOSSARY if f" {g} " in lowered}


def check_step(original, rewritten, profile):
    """Return a list of violations (empty means pass)."""
    problems = []
    for field in ("caption", "simpler_caption"):
        for sent in sentences(rewritten[field]):
            n = len(sent.split())
            if n > profile["longest_sentence"]:
                problems.append(f"{field}: longest-sentence breach ({n})")
            if n > profile["max_words_per_sentence"]:
                problems.append(f"{field}: sentence too long ({n})")
    new_terms = glossary_hits(rewritten["caption"]) | glossary_hits(
        rewritten["simpler_caption"])
    old_terms = glossary_hits(original["caption"]) | glossary_hits(
        original["simpler_caption"])
    added = new_terms - old_terms
    if added:
        problems.append(f"new glossary terms added: {sorted(added)}")
    if len(new_terms) > 3:
        problems.append(f"over brief term cap: {sorted(new_terms)}")
    key = original["step_name"].replace("_", " ").split()[0]
    if key not in (rewritten["caption"] + " " +
                   rewritten["simpler_caption"]).lower():
        problems.append(f"key term {key!r} lost")
    lowered = (rewritten["caption"] + " " +
               rewritten["simpler_caption"]).lower()
    for phrase in BANNED:
        if phrase in lowered:
            problems.append(f"banned phrase {phrase!r} (verifier lesson)")
    return problems


def rewrite_captions(client, pack, profile, model=None, refresh=False):
    version = pack_version(pack)
    slug = (f"captions_{version}_{profile['max_words_per_sentence']}"
            f"_{profile['new_terms_per_step']}.json")
    cache_path = os.path.join(CACHE_DIR, slug)
    if os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f), True
    from app.backends import create_structured
    core = "\n".join(
        f"Step {s['step']} ({s['step_name']}): {s['caption']} "
        f"Simpler: {s['simpler_caption']}" for s in pack["steps"])
    prompt = (
        "Rewrite each step's two captions for this child profile. "
        "Change wording only: no new facts, keep every science term the "
        "core already uses, keep the step's key term. Never write these "
        "phrases, they are scientifically wrong: "
        + ", ".join(f"'{b}'" for b in BANNED) + ".\n"
        f"Profile: {json.dumps(profile)}\nCore:\n{core}")
    originals = {s["step"]: s for s in pack["steps"]}
    if client is None:
        result = {"profile": profile, "pack_version": version,
                  "fallback": True, "offline": True,
                  "captions": [{"step": s["step"], "caption": s["caption"],
                                "simpler_caption": s["simpler_caption"]}
                               for s in pack["steps"]]}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return result, False
    last_problems = []
    for _attempt in (1, 2):
        out, _ = create_structured(
            client, model or "muse-spark-1.3", prompt, CAPTION_SCHEMA,
            "captions")
        by_step = {c["step"]: c for c in out["captions"]}
        last_problems = []
        for n, orig in originals.items():
            last_problems += [f"step{n}: {p}" for p in
                              check_step(orig, by_step[n], profile)]
        if not last_problems:
            result = {"profile": profile, "pack_version": version,
                      "captions": out["captions"]}
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            return result, False
        prompt += ("\nPrevious try failed these checks, fix them: "
                   + "; ".join(last_problems))
    result = {"profile": profile, "pack_version": version, "fallback": True,
              "captions": [{"step": s["step"], "caption": s["caption"],
                            "simpler_caption": s["simpler_caption"]}
                           for s in pack["steps"]]}
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result, False
