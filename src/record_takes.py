"""Scripted demo takes: real app, real model calls. Videos -> video_frames/.

Every take shows a styled cursor that glides between controls, and each
tap carries a short floating caption (also saved as sidecar .srt files,
so captions can be toggled at edit time instead of being burned in).
Interaction states the headless camera cannot reach (live-mic transcript
bubble) are out of scope; see video_frames/vo_fixes.md.

Usage (from repo root, server running with keys in another shell):
  .venv/Scripts/python.exe src/app/server.py       # server first
  .venv/Scripts/python.exe src/record_takes.py     # all takes

Only the take names given on the command line run; with no names, all run.
REDRAW_URL overrides the default http://127.0.0.1:8000.
Exit nonzero if any take fails (its partial video is still kept).
"""

import json
import os
import shutil
import sys
import time
import traceback

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("REDRAW_URL", "http://127.0.0.1:8000")
OUT = os.path.join(ROOT, "video_frames")
META = json.load(open(os.path.join(
    ROOT, "lessons", "water-cycle", "scenes", "step1",
    "dinosaur_valley", "meta.json"), encoding="utf-8"))
LAKE = META["masks"]["lake"]["box"]

FACTS = [
    "Magma is hot melted rock under the ground.",
    "Lava is magma that reaches the surface.",
    "Volcanoes erupt lava, ash and gas.",
    "Lava cools into solid rock.",
    "Some eruptions explode, others flow gently.",
]

SESSION = {
    "saved_at": 0,
    "current_step": 3,
    "mastered": ["evaporation"],
    "concepts": {"1": "evaporation", "2": "vapor_rises",
                 "3": "condensation"},
    "entries": [
        {"kind": "stuck", "step": 1, "title": "Simpler words",
         "world": "dinosaur_valley"},
        {"kind": "tap", "step": 1, "title": "Tapped the lake: correct",
         "world": "dinosaur_valley"},
        {"kind": "bored", "step": 2, "title": "Raised the challenge",
         "world": "block_world"},
    ],
}

# Deterministic take cursor: the native arrow is hidden and replaced by a
# teal dot that glides between controls; tap captions ride beside it.
CURSOR_JS = """(() => {
  if (window.__takeCursor) return; window.__takeCursor = true;
  const install = () => {
  const dot = document.createElement("div");
  dot.id = "take-cursor";
  dot.style.cssText = "position:fixed;z-index:999999;width:18px;height:18px;"
    + "border-radius:50%;background:#C9461F;border:3px solid #fff;"
    + "box-shadow:0 1px 6px rgba(0,0,0,.4);pointer-events:none;"
    + "left:640px;top:400px;transform:translate(-50%,-50%);";
  document.body.appendChild(dot);
  const cap = document.createElement("div");
  cap.id = "take-caption";
  cap.style.cssText = "position:fixed;z-index:999999;pointer-events:none;"
    + "display:none;background:rgba(20,30,40,.88);color:#fff;"
    + "font:600 15px system-ui,sans-serif;padding:8px 12px;"
    + "border-radius:10px;max-width:340px;white-space:nowrap;";
  document.body.appendChild(cap);
  window.__takeTo = (x, y) => {
    dot.style.left = x + "px"; dot.style.top = y + "px";
    if (cap.style.display === "block") {
      cap.style.left = (x + 18) + "px"; cap.style.top = (y + 18) + "px";
    }
  };
  window.__takeSay = (text, ms) => {
    const r = dot.getBoundingClientRect();
    cap.textContent = text; cap.style.display = "block";
    cap.style.left = (r.left + 18) + "px";
    cap.style.top = (r.top + 18) + "px";
    clearTimeout(window.__takeT);
    window.__takeT = setTimeout(() => { cap.style.display = "none"; },
                                ms || 1600);
  };
  document.addEventListener("mousemove", (e) => window.__takeTo(e.clientX,
                                                               e.clientY));
  const st = document.createElement("style");
  st.textContent = "*{cursor:none !important}";
  document.head.appendChild(st);
  };
  if (document.body) install();
  else document.addEventListener("DOMContentLoaded", install);
})();"""

results = []


def run(name, fn):
    try:
        fn()
        results.append((name, "ok"))
        print("TAKE OK:", name, flush=True)
    except Exception:
        traceback.print_exc()
        results.append((name, "FAILED"))
        print("TAKE FAILED:", name, flush=True)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=OUT,
            record_video_size={"width": 1280, "height": 800})

        only = set(sys.argv[1:])
        pos = [640.0, 400.0]

        def arm(page):
            page.add_init_script(CURSOR_JS)

        def glide(page, x, y, steps=16, pause=0.035):
            x0, y0 = pos
            for i in range(1, steps + 1):
                xi = x0 + (x - x0) * i / steps
                yi = y0 + (y - y0) * i / steps
                page.mouse.move(xi, yi)
                time.sleep(pause)
            pos[0], pos[1] = float(x), float(y)

        def tap_at(page, x, y, label, say_ms=1700):
            glide(page, x, y)
            page.evaluate("(t) => window.__takeSay(t, %d)" % say_ms, label)
            time.sleep(0.35)
            page.mouse.down()
            time.sleep(0.12)
            page.mouse.up()

        def click_sel(page, sel, label, say_ms=1700):
            page.wait_for_selector(sel, state="visible")
            b = page.locator(sel).bounding_box()
            tap_at(page, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2,
                   label, say_ms)

        def center_of(page, sel):
            b = page.locator(sel).bounding_box()
            return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)

        def wait_ready(page):
            # The pack (caption) can arrive before the scene image
            # decodes; takes must open on a rendered picture.
            page.wait_for_selector("#scene", state="visible")
            page.wait_for_function(
                "(() => { const i = document.getElementById(\"scene\");"
                " return i && i.complete && i.naturalWidth > 0; })()",
                timeout=30000)

        def take(name, url, actions, seed_session=False):
            if only and name not in only:
                return

            def fn():
                page = ctx.new_page()
                try:
                    arm(page)
                    if seed_session:
                        page.add_init_script(
                            "localStorage.setItem('redraw.session', %s);"
                            % json.dumps(json.dumps(SESSION)))
                        page.goto(url, wait_until="networkidle")
                    else:
                        page.goto(url, wait_until="networkidle")
                    actions(page)
                    time.sleep(2)
                finally:
                    path = page.video.path()
                    page.close()
                    target = os.path.join(OUT, name + ".webm")
                    if os.path.exists(target):
                        os.remove(target)
                    shutil.move(path, target)
            run(name, fn)

        def home_hold(page):
            wait_ready(page)
            page.wait_for_function(
                "document.getElementById('caption').textContent.length > 10")
            x, y = center_of(page, "#scene")
            glide(page, x, y, steps=20)
            page.evaluate("window.__takeSay('Step 1, dinosaur valley', 2200)")
            time.sleep(4)

        take("take1_home_load", BASE + "/", home_hold)

        def setup_tour(page):
            page.wait_for_selector("#modes", state="visible")
            time.sleep(1)
            for y in (400, 900, 1400, 400):
                page.evaluate("window.scrollTo(0, %d)" % y)
                x, _ = pos
                glide(page, x, 400, steps=8, pause=0.05)
                time.sleep(0.8)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)
        take("take2_setup_tour", BASE + "/setup", setup_tour)

        def stuck(page):
            wait_ready(page)
            time.sleep(1)
            click_sel(page, 'button.signal[data-signal="stuck"]',
                      "I don't get it — explain it simpler")
            # Jury panel is hidden in child view: wait attached, not visible.
            page.wait_for_selector("#timeline li:not(.empty)",
                                   state="attached", timeout=45000)
            time.sleep(5)
        take("take3_stuck_redraw", BASE + "/", stuck)

        def tap_lake(page):
            wait_ready(page)
            time.sleep(1)
            click_sel(page, "#gotit", "Got it — quiz me")
            time.sleep(1)
            box = page.evaluate("""() => {
                const img = document.getElementById('scene');
                const r = img.getBoundingClientRect();
                return {x: r.x, y: r.y, w: r.width, h: r.height,
                        nw: img.naturalWidth, nh: img.naturalHeight};
            }""")
            cx = (LAKE["left"] + LAKE["right"]) / 2
            cy = (LAKE["top"] + LAKE["bottom"]) / 2
            tap_at(page, box["x"] + cx / box["nw"] * box["w"],
                   box["y"] + cy / box["nh"] * box["h"], "Tap the lake",
                   say_ms=2200)
            page.wait_for_selector("#verdict-bubble:not(.hidden)",
                                   timeout=20000)
            time.sleep(4)
        take("take4_tap_lake", BASE + "/", tap_lake)

        def bored(page):
            wait_ready(page)
            time.sleep(1)
            click_sel(page, 'button.signal[data-signal="bored"]',
                      "Boring! — give me a challenge")
            page.wait_for_selector("#timeline li:not(.empty)",
                                   state="attached", timeout=45000)
            time.sleep(5)
        take("take5_bored_challenge", BASE + "/", bored)

        def timeline(page):
            wait_ready(page)
            time.sleep(1)
            click_sel(page, 'button.signal[data-signal="stuck"]',
                      "I don't get it — explain it simpler")
            page.wait_for_selector("#timeline li:not(.empty)",
                                   state="attached", timeout=45000)
            click_sel(page, "#jurytoggle",
                      "Jury overlay — why it changed")
            time.sleep(1)
            page.wait_for_selector("#timeline li:not(.empty)",
                                   state="visible", timeout=15000)
            page.evaluate(
                "document.getElementById('timeline').scrollIntoView()")
            time.sleep(4)
        take("take6_why_timeline", BASE + "/", timeline)

        def builder(page):
            page.wait_for_selector("#buildbtn", state="visible")
            page.evaluate(
                "document.getElementById('topic').scrollIntoView("
                "{block: 'center'})")
            time.sleep(1)
            page.fill("#topic", "volcanoes")
            page.fill("#topicfacts", "\n".join(FACTS))
            x, y = center_of(page, "#buildbtn")
            glide(page, x, y)
            page.evaluate("window.__takeSay("
                          "'Build the volcanoes lesson', 2200)")
            time.sleep(0.6)
            page.locator("#buildbtn").click()
            page.wait_for_function(
                "document.getElementById('buildout').textContent"
                ".trim().length > 0", timeout=300000)
            time.sleep(4)
            page.screenshot(path=os.path.join(OUT, "take7_builder_done.png"))
        take("take7_builder_volcanoes", BASE + "/setup", builder)

        def private(page):
            page.wait_for_selector("#modes", state="visible")
            time.sleep(1)
            b = page.locator("#modes >> text=Private mode").bounding_box()
            glide(page, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            page.evaluate("window.__takeSay("
                          "'Private mode — stays on open weights', 2200)")
            time.sleep(0.6)
            page.locator("#modes >> text=Private mode").click()
            time.sleep(3)
            b = page.locator("#modes >> text=Standard").bounding_box()
            glide(page, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
            page.locator("#modes >> text=Standard").click()
            time.sleep(2)
        take("take8_private_toggle", BASE + "/setup", private)

        def report(page):
            page.wait_for_selector("#reportbtn", state="visible")
            page.evaluate(
                "document.getElementById('reportbtn').scrollIntoView("
                "{block: 'center'})")
            time.sleep(1)
            x, y = center_of(page, "#reportbtn")
            glide(page, x, y)
            page.evaluate("window.__takeSay("
                          "'Build the parent report', 2200)")
            time.sleep(0.6)
            page.locator("#reportbtn").click()
            page.wait_for_function(
                "document.getElementById('reportout').textContent"
                ".trim().length > 0", timeout=60000)
            time.sleep(4)
        take("take9_parent_report", BASE + "/setup", report, seed_session=True)

        browser.close()

    print("RESULTS:", results)
    if any(s != "ok" for _, s in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
