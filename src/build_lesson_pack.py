"""Build the water-cycle lesson pack with everything cached locally.

Layout (repo root):
  lessons/water-cycle.md            the brief (input)
  lessons/.cache/wonder_pack_raw.json   FULL raw text API response (replay cache)
  lessons/water-cycle.json          the parsed lesson pack (5 steps)
  scenes/step<N>/<world>/image.png      generated scene
  scenes/step<N>/<world>/prompt.txt     prompt that produced it
  scenes/step<N>/<world>/meta.json      image API metadata (model, size, ...)

Replay rule: if a cached/completed artifact exists it is reused and NO API
call is made, so re-running this script costs nothing. Use --refresh-text /
--refresh-images to spend credits again deliberately.

Usage (from repo root):
  set -a; source .env; set +a
  .venv/bin/python src/build_lesson_pack.py [--no-images] [--refresh-text]
      [--refresh-images] [--world NAME] [--step N]
"""

import argparse
import base64
import json
import os
import sys
import urllib.request

from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOPIC = "water-cycle"
BRIEF_PATH = os.path.join(ROOT, "lessons", "water-cycle.md")
CACHE_TEXT_PATH = os.path.join(ROOT, "lessons", ".cache", "wonder_pack_raw.json")
PACK_PATH = os.path.join(ROOT, "lessons", "water-cycle.json")
SCENES_DIR = os.path.join(ROOT, "scenes")

STEP_NAMES = ["evaporation", "vapor_rises", "condensation",
              "precipitation", "collection"]
WORLDS = ["dinosaur_valley", "block_world"]

WORLD_STYLE = {
    "dinosaur_valley": ("a warm prehistoric valley with a lake, volcanoes in "
                        "the distance, ferns and friendly plant-eating "
                        "dinosaurs"),
    "block_world": ("a world built from cubic blocks, with blocky hills, a "
                    "block lake, square clouds and blocky trees"),
}
WORLD_BACK = {
    "dinosaur_valley": "hills and volcanoes",
    "block_world": "blocky hills",
}

STEP_SCHEMA = {
    "type": "object",
    "properties": {
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
                 "analogies", "tap_question", "say_it", "image_prompts"],
    "additionalProperties": False,
}

# strict must stay False: strict mode rejects the free-form analogies /
# image_prompts maps (their keys differ per world).
PACK_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": STEP_SCHEMA,
                  "minItems": 5, "maxItems": 5},
    },
    "required": ["steps"],
    "additionalProperties": False,
}


def load_brief():
    with open(BRIEF_PATH, encoding="utf-8") as f:
        return f.read()


def get_text_pack(client, refresh=False):
    """Return (pack_dict, from_cache). One API call on cache miss only."""
    if os.path.exists(CACHE_TEXT_PATH) and not refresh:
        with open(CACHE_TEXT_PATH, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"cache hit: {CACHE_TEXT_PATH} (no API call)")
        parsed = cache["parsed"]
        from_cache = True
    else:
        print("cache miss: calling muse-wonder-1.0 for all 5 steps ...")
        resp = client.responses.create(
            model="muse-wonder-1.0",
            reasoning={"effort": "medium"},
            input=load_brief(),
            text={"format": {"type": "json_schema", "name": "lesson_pack",
                             "strict": False, "schema": PACK_SCHEMA}},
        )
        parsed = json.loads(resp.output_text)
        assert len(parsed["steps"]) == 5, "expected 5 steps"
        os.makedirs(os.path.dirname(CACHE_TEXT_PATH), exist_ok=True)
        with open(CACHE_TEXT_PATH, "w", encoding="utf-8") as f:
            json.dump({"response": json.loads(resp.model_dump_json()),
                       "parsed": parsed}, f, indent=2)
        print(f"cached full raw response: {CACHE_TEXT_PATH}")
        usage = resp.usage
        if usage is not None:
            print(f"usage: in={usage.input_tokens} out={usage.output_tokens} "
                  f"total={usage.total_tokens}")
        from_cache = False
    pack = {"topic": TOPIC, "steps": parsed["steps"]}
    for i, name in enumerate(STEP_NAMES):
        pack["steps"][i]["step"] = i + 1
        pack["steps"][i]["step_name"] = name
    with open(PACK_PATH, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, ensure_ascii=False)
    print(f"wrote {PACK_PATH}")
    return pack, from_cache


def load_pack():
    """Replay without any API call: read the saved pack from disk."""
    with open(PACK_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_image_prompt(step, world):
    target = step["tap_question"]["target_noun"]
    change = step["image_prompts"][world]
    return (
        f"{WORLD_STYLE[world]}. Same fixed scene in every step: lake at left, "
        f"sun top right, {WORLD_BACK[world]} at the back, a river at the "
        f"right. Step change for this picture: {change} "
        f"Show the {target} large, separate from other objects and "
        f"unobstructed. Calm, soft colours. No scary elements, no predators, "
        f"no fighting, no dangerous weather. No text, letters, numbers, "
        f"labels or logos. No human faces. Animals only as small friendly "
        f"background details."
    )


def save_image_data(data, path):
    """Save image bytes; fix the extension to the real format (the image
    API returns WebP bytes). Returns (final_path, info)."""
    payload = data.b64_json if data.b64_json else None
    if payload is None and data.url:
        with urllib.request.urlopen(data.url) as r:
            raw = r.read()
        info = {"saved_from": "url"}
    else:
        raw = base64.b64decode(payload)
        info = {"saved_from": "b64_json"}
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        final = os.path.splitext(path)[0] + ".webp"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        final = os.path.splitext(path)[0] + ".png"
    else:
        final = path
    with open(final, "wb") as f:
        f.write(raw)
    info["format"] = os.path.splitext(final)[1].lstrip(".")
    return final, info


def existing_image(d):
    for name in ("image.webp", "image.png"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(d, "image.webp")


def get_images(client, pack, refresh=False, only_world=None, only_step=None,
               no_images=False):
    if no_images:
        return
    for i, step in enumerate(pack["steps"]):
        n = i + 1
        if only_step is not None and n != only_step:
            continue
        for world in WORLDS:
            if only_world is not None and world != only_world:
                continue
            d = os.path.join(SCENES_DIR, f"step{n}", world)
            img_path = existing_image(d)
            if os.path.exists(img_path) and not refresh:
                print(f"cache hit: {img_path} (no API call)")
                continue
            prompt = build_image_prompt(step, world)
            print(f"generating: step{n}/{world} ...")
            img = client.images.generate(
                model="muse-image-1.0",
                prompt=prompt,
                size="1024x1024",
            )
            data = img.data[0]
            os.makedirs(d, exist_ok=True)
            img_path, saved = save_image_data(
                data, os.path.join(d, "image.webp"))
            with open(os.path.join(d, "prompt.txt"), "w",
                      encoding="utf-8") as f:
                f.write(prompt)
            meta = {"model": "muse-image-1.0", "size": "1024x1024",
                    "saved_from": saved["saved_from"],
                    "format": saved["format"]}
            revised = getattr(data, "revised_prompt", None)
            if revised:
                meta["revised_prompt"] = revised
            with open(os.path.join(d, "meta.json"), "w",
                      encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            print(f"wrote {img_path} "
                  f"({os.path.getsize(img_path)} bytes)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-text", action="store_true")
    ap.add_argument("--refresh-images", action="store_true")
    ap.add_argument("--world", default=None, choices=WORLDS)
    ap.add_argument("--step", default=None, type=int, choices=[1, 2, 3, 4, 5])
    ap.add_argument("--no-images", action="store_true")
    args = ap.parse_args(argv)
    client = OpenAI(base_url="https://api.meta.ai/v1",
                    api_key=os.environ["MODEL_API_KEY"])
    pack, _ = get_text_pack(client, refresh=args.refresh_text)
    get_images(client, pack, refresh=args.refresh_images,
               only_world=args.world, only_step=args.step,
               no_images=args.no_images)
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
