"""Segment scene hotspots with SAM 3.1 (one request per noun).

For each scene in lessons/water-cycle/scenes/step<N>/<world>/ and each
noun, requests a concept segmentation, decodes the masks with the vendored
official decoder, keeps the largest-area match, and saves mask_<noun>.png
plus box metadata into the scene's meta.json.

Cache rule (credit safety): lessons/water-cycle/.cache/sam_<n>_<world>_<noun>.json
holds the FULL raw output text. On cache hit there is NO API call.
Use --refresh to spend credits again deliberately.

Usage (from repo root):
  set -a; source .env; set +a
  .venv/bin/python src/app/sam_segment.py [--step N] [--world NAME]
      [--noun NOUN] [--refresh]
"""

import argparse
import base64
import json
import os
import re
import struct
import sys
import zlib

from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.vendor_meta_sam import SegmentationMask, decode_mask_to_raster

LESSON_DIR = os.path.join(ROOT, "lessons", "water-cycle")
CACHE_DIR = os.path.join(LESSON_DIR, ".cache")
WORLDS = ["dinosaur_valley", "block_world"]

BOX_RE = re.compile(r"(\d+)<\|box;([^|]*)\|><\|mask;([^|]*)\|>")


def parse_fields(text):
    out = {}
    for part in text.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_records(output_text):
    """Return [(object_id, box_dict, h, w, payload)] for frame <0f>."""
    records = []
    for line in output_text.splitlines():
        line = line.strip()
        if not line.startswith("<0f>"):
            continue
        for obj_id, box_text, mask_text in BOX_RE.findall(line):
            box = parse_fields(box_text)
            mask = parse_fields(mask_text)
            data = mask["data"].split(",")
            records.append((obj_id, box, int(data[0]), int(data[1]),
                            ",".join(data[2:])))
    return records


def webp_size(path):
    with open(path, "rb") as f:
        head = f.read(30)
    assert head[:4] == b"RIFF" and head[8:12] == b"WEBP", "not a webp"
    if head[12:16] == b"VP8X":
        w = int.from_bytes(head[24:27], "little") + 1
        h = int.from_bytes(head[27:30], "little") + 1
        return w, h
    raise ValueError("unsupported webp chunk, expected VP8X")


def write_png_gray(path, pixels, width, height):
    """pixels: bytes of 0/255, row-major. Pure stdlib PNG writer."""
    raw = b"".join(b"\x00" + bytes(pixels[y * width:(y + 1) * width])
                   for y in range(height))

    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(
            ">I", zlib.crc32(c))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0,
                                        0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def segment_one(client, image_path, noun, cache_path, refresh=False):
    if os.path.exists(cache_path) and not refresh:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"cache hit: {cache_path} (no API call)")
        return cache["output_text"]
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    resp = client.responses.create(
        model="sam-3.1",
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": noun},
            {"type": "input_image",
             "image_url": f"data:image/webp;base64,{b64}"},
        ]}],
    )
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"noun": noun, "image": os.path.basename(image_path),
                   "output_text": resp.output_text,
                   "usage": (resp.usage.model_dump()
                             if resp.usage else None)}, f, indent=2)
    print(f"cached: {cache_path}")
    return resp.output_text


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=None)
    ap.add_argument("--world", default=None, choices=WORLDS)
    ap.add_argument("--noun", default=None)
    ap.add_argument("--concept", default=None,
                    help="override concept prompt text (cached separately)")
    ap.add_argument("--image", default="image.webp")
    ap.add_argument("--mask-key", default="masks")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)
    with open(os.path.join(LESSON_DIR, "pack.json"), encoding="utf-8") as f:
        pack = json.load(f)
    client = OpenAI(base_url="https://api.meta.ai/v1",
                    api_key=os.environ["MODEL_API_KEY"])
    for s in pack["steps"]:
        n = s["step"]
        if args.step is not None and n != args.step:
            continue
        noun = args.noun or s["tap_question"]["target_noun"]
        for world in WORLDS:
            if args.world is not None and world != args.world:
                continue
            d = os.path.join(LESSON_DIR, "scenes", f"step{n}", world)
            img_path = os.path.join(d, args.image)
            if not os.path.exists(img_path):
                if args.image == "image.webp":
                    legacy = os.path.join(d, "image.png")
                    if os.path.exists(legacy):
                        img_path = legacy
            if not os.path.exists(img_path):
                print(f"skip step{n}/{world}: no {args.image}")
                continue
            iw, ih = webp_size(img_path)
            concept = args.concept or noun
            slug = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_")
            tag = os.path.splitext(os.path.basename(img_path))[0]
            cache_path = os.path.join(
                CACHE_DIR, f"sam_{tag}_step{n}_{world}_{noun}_{slug}.json")
            if not args.refresh and tag == "image":
                for legacy_name in [
                    f"sam_step{n}_{world}_{noun}_{slug}.json",
                    f"sam_step{n}_{world}_{noun}.json",
                ]:
                    legacy = os.path.join(CACHE_DIR, legacy_name)
                    if (legacy != cache_path and os.path.exists(legacy)
                            and not os.path.exists(cache_path)):
                        os.rename(legacy, cache_path)
            text = segment_one(client, img_path, concept, cache_path,
                               refresh=args.refresh)
            records = parse_records(text)
            print(f"step{n}/{world} '{noun}': {len(records)} match(es)")
            best, best_area = None, -1
            for obj_id, box, mh, mw, payload in records:
                enc = "lossless" if payload.startswith("~") else "one_bit"
                raster = decode_mask_to_raster(SegmentationMask(
                    encoding=enc, payload=payload, width=mw, height=mh))
                area = sum(raster)
                if area > best_area:
                    best, best_area = (obj_id, box, mh, mw, raster), area
            meta_path = os.path.join(d, "meta.json")
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            masks = meta.get(args.mask_key, {})
            existing = masks.get(noun)
            if best is None:
                if existing and existing.get("box"):
                    print(f"  kept existing {existing.get('source')} box")
                    continue
                masks[noun] = {"source": "sam-3.1", "matches": 0,
                               "mask_png": None}
            else:
                obj_id, box, mh, mw, raster = best
                png_name = (f"mask_{noun}.png"
                            if tag == "image" else f"{tag}_mask_{noun}.png")
                write_png_gray(os.path.join(d, png_name),
                               bytes(255 if v else 0 for v in raster), mw, mh)
                masks[noun] = {
                    "source": "sam-3.1", "matches": len(records),
                    "object_id": obj_id, "mask_png": png_name,
                    "raster": [mh, mw], "image": [iw, ih],
                    "box": {"left": int(box["x1"]), "top": int(box["y1"]),
                            "right": int(box["x2"]) + 1,
                            "bottom": int(box["y2"]) + 1},
                    "coverage": best_area / (mw * mh),
                }
                print(f"  box={masks[noun]['box']} raster={mw}x{mh} "
                      f"coverage={masks[noun]['coverage']:.2f}")
            meta[args.mask_key] = masks
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
    print("done.")


if __name__ == "__main__":
    sys.exit(main())
