"""Geometry tests for tap grading: fixed inside/outside points per hotspot.

Usage (from repo root): .venv/bin/python src/app/test_grading.py
Exit nonzero on failure. No API calls, no framework.
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

from app.grading import (grade_tap, mask_path_for, point_in_box,
                         read_png_gray)

LESSON_DIR = os.path.join(ROOT, "lessons", "water-cycle")
W, H = 1600, 1600  # all scene images are 1600x1600 media pixels


def scene_point(entry, mask, want_inside):
    box = entry["box"]
    if entry.get("mask_png") and mask is not None:
        pixels, mw, mh = mask
        white = next(i for i, v in enumerate(pixels) if v > 0)
        black = next((i for i, v in enumerate(pixels) if v == 0), None)
        row, col = divmod(white, mw)
        sx = (box["right"] - box["left"]) / mw
        sy = (box["bottom"] - box["top"]) / mh
        inside = (box["left"] + (col + 0.5) * sx,
                  box["top"] + (row + 0.5) * sy)
        if want_inside or black is None:
            return inside
        row, col = divmod(black, mw)
        return (box["left"] + (col + 0.5) * sx,
                box["top"] + (row + 0.5) * sy)
    cx = (box["left"] + box["right"]) / 2
    cy = (box["top"] + box["bottom"]) / 2
    if want_inside:
        return cx, cy
    for corner in ((5, 5), (W - 5, 5), (5, H - 5), (W - 5, H - 5)):
        if not point_in_box(box, *corner):
            return corner
    raise AssertionError("box covers every corner")


def main():
    pack = json.load(open(os.path.join(LESSON_DIR, "pack.json"),
                           encoding="utf-8"))
    checked = 0
    for s in pack["steps"]:
        noun = s["tap_question"]["target_noun"]
        for world in ("dinosaur_valley", "block_world"):
            d = os.path.join(LESSON_DIR, "scenes", f"step{s['step']}", world)
            meta = json.load(open(os.path.join(d, "meta.json"),
                                  encoding="utf-8"))
            for key, img in (("masks", "image.webp"),
                             ("masks_simpler", "simpler.webp")):
                entry = meta.get(key, {}).get(noun)
                assert entry and entry.get("box"), f"{d} {key}.{noun}"
                mask = None
                if mask_path_for(entry):
                    mp = os.path.join(d, mask_path_for(entry))
                    assert os.path.exists(mp), mp
                    mask = read_png_gray(mp)
                xi, yi = scene_point(entry, mask, True)
                ok, msg = grade_tap(entry, noun, xi, yi, mask)
                assert ok, f"{d} {key}: inside point failed"
                assert noun in msg, f"{d} {key}: message names noun"
                xo, yo = scene_point(entry, mask, False)
                ok, msg = grade_tap(entry, noun, xo, yo, mask)
                assert not ok, f"{d} {key}: outside point passed"
                assert "Not quite" in msg, f"{d} {key}: kind message"
                checked += 1
    print(f"tap grading ok: {checked} hotspots x inside/outside")
    dilated = 0
    for mp in sorted(glob.glob(os.path.join(LESSON_DIR, "scenes", "step*",
                                            "*", "meta.json"))):
        d = os.path.dirname(mp)
        meta = json.load(open(mp, encoding="utf-8"))
        for key in ("masks", "masks_simpler"):
            for noun, entry in meta.get(key, {}).items():
                if not entry.get("mask_dilated_png"):
                    continue
                raw, _, _ = read_png_gray(os.path.join(d, entry["mask_png"]))
                wide, _, _ = read_png_gray(
                    os.path.join(d, entry["mask_dilated_png"]))
                assert all(w >= r for w, r in zip(wide, raw)), (mp, noun)
                assert sum(wide) > sum(raw), (mp, noun)
                dilated += 1
    print(f"dilation ok: {dilated} masks grown, none shrunk")


if __name__ == "__main__":
    sys.exit(main())
