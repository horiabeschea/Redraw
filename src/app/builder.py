"""Lesson Builder core: topic-parameterized pack generation.

Layers (each depends on one preference, cached separately):
  core      topic only        Wonder + verifier, versioned file
  captions  level + terms     Spark from the core (app.captions)
  analogies world             presets in the core call; custom via Spark+checker
  images    world only        Image edits from the opening scene (D26),
                              fresh generations only as fallback, then SAM
  live      signal only       Spark rewriting the cached caption (app.policy)

Lesson dir layout (lessons/<slug>/):
  brief.md, pack.json (carries topic, slug, version), .cache/, scenes/

No network imports here: API clients are injected by callers, so every
path is unit-testable offline with stubs. Cache rule everywhere: an
existing artifact is reused and no API call is made.
"""

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.contracts import validate  # noqa: E402

WONDER_MODEL = "muse-wonder-1.0"
IMAGE_MODEL = "muse-image-1.0"
SAM_MODEL = "sam-3.1"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")

# Generic style descriptions only: never a brand, title or character.
PRESET_WORLDS = {
    "dinosaur_valley": ("a warm prehistoric valley with a lake, volcanoes "
                        "in the distance, ferns and friendly plant-eating "
                        "dinosaurs"),
    "block_world": ("a world built from cubic blocks, with blocky hills, "
                    "a block lake, square clouds and blocky trees"),
    "space_world": ("quiet outer space with round friendly planets, soft "
                    "stars and a small round moon"),
    "ocean_world": ("a calm shallow sea with soft waves, coral shapes, "
                    "small friendly fish and light rays in the water"),
    "train_world": ("a green valley with a looping toy-like railway, "
                    "small friendly trains, bridges and tunnels"),
    "robot_world": ("a tidy workshop of small boxy helper robots, soft "
                    "lamps, gears and shelves with jars"),
}

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "step": {"type": "integer", "minimum": 1, "maximum": 5},
        "step_name": {"type": "string"},
        "key_terms": {"type": "array", "items": {"type": "string"}},
        "caption": {"type": "string"},
        "simpler_caption": {"type": "string"},
        "misconception": {"type": "string"},
        "correction": {"type": "string"},
        "analogies": {"type": "object",
                      "additionalProperties": {"type": "string"}},
        "tap_question": {"type": "object", "properties": {
            "prompt": {"type": "string"}, "target_noun": {"type": "string"}},
            "required": ["prompt", "target_noun"],
            "additionalProperties": False},
        "say_it": {"type": "object", "properties": {
            "prompt": {"type": "string"}, "answer_key": {"type": "string"}},
            "required": ["prompt", "answer_key"],
            "additionalProperties": False},
        "image_prompts": {"type": "object",
                          "additionalProperties": {"type": "string"}},
    },
    "required": ["caption", "simpler_caption", "misconception", "correction",
                 "analogies", "tap_question", "say_it", "image_prompts",
                 "step", "step_name"],
    "additionalProperties": False,
}

# NOTE: key_terms stays optional so committed packs built before it
# validate unchanged; builders always write it for new topics.
PACK_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": STEP_SCHEMA,
                  "minItems": 5, "maxItems": 5},
    },
    "required": ["steps"],
    "additionalProperties": False,
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer", "minimum": 1},
                    "accurate": {"type": "string",
                                 "enum": ["yes", "no", "unsure"]},
                    "issue": {"type": "string"},
                },
                "required": ["step", "accurate", "issue"],
                "additionalProperties": False,
            },
            "minItems": 1,
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

ANALOGY_SCHEMA = {
    "type": "object",
    "properties": {
        "analogies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "integer", "minimum": 1},
                    "text": {"type": "string"},
                },
                "required": ["step", "text"],
                "additionalProperties": False,
            },
            "minItems": 1,
        },
    },
    "required": ["analogies"],
    "additionalProperties": False,
}


def valid_slug(slug):
    return bool(slug and SLUG_RE.match(slug))


def lesson_paths(root, slug):
    lesson_dir = os.path.join(root, "lessons", slug)
    return {"dir": lesson_dir,
            "brief": os.path.join(lesson_dir, "brief.md"),
            "pack": os.path.join(lesson_dir, "pack.json"),
            "cache": os.path.join(lesson_dir, ".cache"),
            "scenes": os.path.join(lesson_dir, "scenes")}


def fill_template(topic, facts, tiers, worlds):
    """Build the Wonder brief for a parent-chosen topic.

    tiers: {"max_words": N, "longest": M, "new_terms": K} for the
    standard tier; the simpler tier derives from it. worlds: list of
    preset world ids; every world gets an analogy in the one core call.
    """
    simpler_max = max(3, tiers["max_words"] - 5)
    world_lines = "\n".join(
        f'- "{w}": {PRESET_WORLDS[w]}.' for w in worlds)
    fact_lines = "\n".join(f"- {f.strip()}" for f in facts if f.strip())
    return f"""You are building a lesson pack for a child's learning app. Follow every constraint
exactly. Return only JSON matching the supplied schema.

LEARNER
- Age: {tiers.get("age", 8)} years
- Reading level, tier "standard": max {tiers["max_words"]} words per sentence, longest
  sentence allowed {tiers["longest"]} words, everyday words only, one idea per sentence.
- Tier "simpler": max {simpler_max} words per sentence, at most 2 sentences,
  concrete nouns and active verbs, no new terms.
- New science words per step: at most {tiers["new_terms"]}. Introduce the word after the
  idea, never before. Define it in the same breath using a picture word.
- This child can lose interest when text is long, abstract or repetitive. Prefer
  showing over telling. Never use a tone that suggests the child did something wrong.

TOPIC AND SCOPE
- Topic: {topic}. Derive exactly 5 ordered steps from the facts below.
  Name each step with a short snake_case step_name.
- Stay strictly within the facts below. Do not add facts, numbers or examples that
  are not listed or directly implied.

FACTS (ground truth, chosen by the parent)
{fact_lines}

INTEREST WORLDS (generic style descriptions only)
{world_lines}
- Never mention or imply any brand, game title, film, character or logo.

FOR EACH STEP, PRODUCE
1. key_terms: the 1-3 science words this step teaches (plain words or short phrases).
2. caption (tier standard) and simpler_caption (tier simpler).
3. misconception: one specific belief children commonly hold about this step.
4. correction: a one-sentence, kind correction in tier standard.
5. analogies: one per interest world, 1-2 short sentences, scientifically correct
   in every detail. If an analogy cannot be exact, leave it out and say so in
   "notes".
6. tap_question: a prompt in tier simpler, and a target_noun that is a single
   concrete, large, visible object in the picture.
7. say_it: a prompt asking the child to explain the step in their own words, and an
   answer_key listing the 2-3 ideas an acceptable answer must contain, plus 1-2
   common partial answers and how to respond kindly.
8. image_prompts: one per world.

IMAGE PROMPT RULES
- First describe a fixed layout for every step of a world (the "scene bible",
  named places for the important objects). Each step's prompt describes only
  what changes, so later steps can be made by editing the previous picture.
- The target_noun must appear large, separate from other objects, and unobstructed.
- Calm, soft colours. No scary elements, no predators, no fighting, no weather
  that looks dangerous.
- No text, letters, numbers, labels or logos in the picture.
- No human faces. Animals and creatures only as small friendly background details.

SELF-CHECK BEFORE ANSWERING
- Every caption obeys its word limits.
- Each step has at most {tiers["new_terms"]} new science term(s), listed in key_terms.
- No analogy states anything untrue about the topic.
- No brand names anywhere.
- Every target_noun is named in its image prompt."""


def _wonder_call(client, brief, schema, name, cache_path, refresh=False,
                 model=WONDER_MODEL):
    """One Wonder structured call with full-raw-response caching."""
    if os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)["parsed"], True
    resp = client.responses.create(
        model=model, reasoning={"effort": "medium"}, input=brief,
        text={"format": {"type": "json_schema", "name": name,
                         "strict": False, "schema": schema}})
    parsed = json.loads(resp.output_text)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"response": json.loads(resp.model_dump_json()),
                   "parsed": parsed}, f, indent=2)
    return parsed, False


def build_core(client, paths, slug, topic, facts, tiers, worlds,
               refresh=False):
    """Wonder core call for a new topic. Returns (pack, verdicts, cached).

    Writes brief.md and pack.json (version 1). Raises ValueError when the
    model output fails PACK_SCHEMA: the parent sees an error, never a
    half-built lesson.
    """
    brief = fill_template(topic, facts, tiers, worlds)
    os.makedirs(paths["dir"], exist_ok=True)
    with open(paths["brief"], "w", encoding="utf-8") as f:
        f.write(brief)
    parsed, cached = _wonder_call(
        client, brief, PACK_SCHEMA, "lesson_pack",
        os.path.join(paths["cache"], "wonder_pack_raw.json"),
        refresh=refresh)
    if len(parsed["steps"]) != 5:
        raise ValueError("expected 5 steps from the lesson call")
    pack = {"topic": topic, "slug": slug, "version": 1,
            "worlds": list(worlds), "steps": parsed["steps"]}
    for i, s in enumerate(pack["steps"]):
        s["step"] = i + 1
        s.setdefault("key_terms", [])
    validate(PACK_SCHEMA, {"steps": pack["steps"]})
    with open(paths["pack"], "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, ensure_ascii=False)
    verdicts = verify_pack(client, paths, refresh=refresh)
    return pack, verdicts, cached


def _brief_facts(brief_path):
    with open(brief_path, encoding="utf-8") as f:
        brief = f.read()
    if "INTEREST WORLDS" in brief:
        facts = brief.split("FACTS", 1)[1].split("INTEREST WORLDS")[0]
    else:
        facts = brief.split("FACTS", 1)[1]
    return facts.strip().strip("()").strip()


def verify_pack(client, paths, worlds=None, refresh=False):
    """Second Wonder pass over the pack's analogies. Returns verdicts.

    worlds limits the verdicts to one custom world (used after a custom
    analogy lands); None checks everything.
    """
    with open(paths["pack"], encoding="utf-8") as f:
        pack = json.load(f)
    lines = ["You are a science accuracy checker for a children's lesson.",
             "FACTS (ground truth, from the lesson brief):",
             _brief_facts(paths["brief"]),
             "ANALOGIES TO CHECK (one block per step):"]
    for s in pack["steps"]:
        lines.append(f"Step {s['step']} ({s['step_name']}): "
                     f"caption: {s['caption']}")
        for world, text in s["analogies"].items():
            if worlds is not None and world not in worlds:
                continue
            lines.append(f"  [{world}] {text}")
    lines.append("For each step, say whether its analogies state anything "
                 "untrue about the lesson topic. If unsure, say 'unsure' "
                 "and explain in 'issue'. Return only JSON.")
    cache_path = os.path.join(paths["cache"], "verifier_raw.json")
    if worlds is not None:
        cache_path = os.path.join(
            paths["cache"],
            f"verifier_{'_'.join(sorted(worlds))}_raw.json")
    parsed, _ = _wonder_call(client, "\n".join(lines), VERDICT_SCHEMA,
                             "verdicts", cache_path, refresh=refresh)
    return parsed["verdicts"]


def glossary_for(pack):
    """Topic glossary for the caption code checks.

    Prefers the core's key_terms; packs built before key_terms existed
    fall back to deriving terms from step names (water-cycle behavior).
    """
    terms = set()
    for s in pack["steps"]:
        for t in s.get("key_terms") or []:
            terms.add(t.lower())
    if not terms:
        for s in pack["steps"]:
            name = s.get("step_name", "").replace("_", " ")
            terms.add(name)
            terms.add(name.split()[0])
    return sorted(terms)


def build_custom_analogy(text_client, text_model, pack, world, description):
    """Spark analogies for a parent-described world, one structured call.

    Returns {step_number: text}. The caller merges them into the pack and
    re-runs verify_pack for this world before a child ever sees them.
    """
    from app.backends import create_structured
    core = "\n".join(
        f"Step {s['step']} ({s['step_name']}): {s['caption']}"
        for s in pack["steps"])
    out, _ = create_structured(
        text_client, text_model,
        ("Write a 1-2 sentence analogy for each lesson step, set in this "
         "world. Scientifically exact in every detail; everyday words; "
         "never mention brands.\n"
         f"World: {description}\nSteps:\n{core}"),
        ANALOGY_SCHEMA, "analogies")
    return {a["step"]: a["text"] for a in out["analogies"]}


def build_image_prompt(step, world, worlds):
    """Full image prompt: world style + scene bible + step change."""
    target = step["tap_question"]["target_noun"]
    change = step["image_prompts"][world]
    return (
        f"{worlds[world]}. Same fixed scene in every step of this world. "
        f"Step change for this picture: {change} "
        f"Show the {target} large, separate from other objects and "
        f"unobstructed. Calm, soft colours. No scary elements, no predators, "
        f"no fighting, no dangerous weather. No text, letters, numbers, "
        f"labels or logos. No human faces. Animals only as small friendly "
        f"background details."
    )


def save_image_bytes(raw, path):
    """Save image bytes; fix the extension to the real format."""
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        final = os.path.splitext(path)[0] + ".webp"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        final = os.path.splitext(path)[0] + ".png"
    else:
        final = path
    with open(final, "wb") as f:
        f.write(raw)
    return final


def _read_image_bytes(data):
    import base64
    if getattr(data, "b64_json", None):
        return base64.b64decode(data.b64_json)
    if getattr(data, "url", None):
        import urllib.request
        with urllib.request.urlopen(data.url) as r:
            return r.read()
    raise ValueError("image result has neither b64_json nor url")


def get_scene_image(img_client, paths, step, world, worlds, prior_path=None,
                    refresh=False, variant="normal"):
    """Image for one scene. Returns (path, method).

    D26: steps after the opening scene are edits of the previous picture.
    The edit call is attempted first; any failure falls back to an
    independent generation and the method is recorded in meta.json, so a
    missing edit endpoint degrades visibly instead of silently.
    """
    import time
    d = os.path.join(paths["scenes"], f"step{step['step']}", world)
    name = "image.webp" if variant == "normal" else "simpler.webp"
    img_path = os.path.join(d, name)
    if os.path.exists(img_path) and not refresh:
        return img_path, "cache"
    prompt = build_image_prompt(step, world, worlds)
    if variant == "simpler":
        prompt += (" Simplified variant of the same scene: fewer details, "
                   "larger shapes, less clutter, same layout and colours.")
    method = "generate"
    if prior_path and os.path.exists(prior_path) and variant == "normal":
        try:
            with open(prior_path, "rb") as f:
                edit = img_client.images.edit(
                    model=IMAGE_MODEL, image=[f],
                    prompt=("Same scene, only this changes: "
                            f"{step['image_prompts'][world]}"))
            raw = _read_image_bytes(edit.data[0])
            method = "edit"
        except Exception:  # noqa: BLE001 (edit endpoint optional)
            img = img_client.images.generate(
                model=IMAGE_MODEL, prompt=prompt, size="1024x1024")
            raw = _read_image_bytes(img.data[0])
    else:
        # Retry once on transient failures; then the caller sees the error.
        last = None
        for _ in (1, 2):
            try:
                img = img_client.images.generate(
                    model=IMAGE_MODEL, prompt=prompt, size="1024x1024")
                raw = _read_image_bytes(img.data[0])
                last = None
                break
            except Exception as e:  # noqa: BLE001 (transient, one retry)
                last = e
                time.sleep(2)
        if last is not None:
            raise last
    os.makedirs(d, exist_ok=True)
    final = save_image_bytes(raw, img_path)
    prompt_name = ("prompt.txt" if variant == "normal"
                   else "prompt_simpler.txt")
    with open(os.path.join(d, prompt_name), "w", encoding="utf-8") as f:
        f.write(prompt)
    meta_path = os.path.join(d, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    entry = {"model": IMAGE_MODEL, "method": method, "size": "1024x1024",
             "image": os.path.basename(final)}
    if variant == "normal":
        meta.update(entry)
    else:
        meta["simpler"] = entry
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return final, method
