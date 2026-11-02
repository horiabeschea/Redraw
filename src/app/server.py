"""Redraw lesson server (standard library only).

Serves the lesson screen and the golden set offline:
  /                     the lesson screen (jury overlay + grown-ups gate)
  /setup                parent setup (settings kept in browser localStorage)
  /app.js, /setup.js, /styles.css  page assets
  /api/pack             lessons/water-cycle/pack.json
  /assets/<step>/<world>/<file>   scene files (image/simpler/mask/prompts)

Planned endpoints (added with later plan steps, same route table shape):
  POST /api/policy   adaptation decisions (Muse Spark 1.3)
  POST /api/sayit    say-it grading (Muse Spark 1.3)
  WS   /api/voice    Voice Transcribe proxy
  POST /api/report  parent report (Muse Spark 1.3, offline template fallback)

NOTE: the decided stack is FastAPI on Modal (D4/D15). PyPI is unreachable
from the dev environment, so local serving uses this stdlib adapter with an
identical route layout; the handlers port one-to-one to FastAPI on deploy.

Usage: .venv/bin/python src/app/server.py [--port 8000]
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.policy import decide, next_state_for

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
LESSON_DIR = os.path.join(ROOT, "lessons", "water-cycle")
CACHE_DIR = os.path.join(LESSON_DIR, ".cache")
LATENCY_LOG = os.path.join(CACHE_DIR, "latency.jsonl")
BACKEND = os.environ.get("REDRAW_BACKEND", "meta")


def _needs_meta():
    if BACKEND != "meta":
        raise ValueError("needs Standard mode: switch back from Private "
                         "mode for this build step")

_clients = {}


def get_client():
    from app.backends import BACKENDS, get_client as make_client
    if BACKEND not in _clients:
        _clients[BACKEND] = make_client(BACKEND)
    return _clients[BACKEND]


def backend_models():
    from app.backends import BACKENDS
    return BACKENDS[BACKEND]
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SCENES_DIR = os.path.join(LESSON_DIR, "scenes")


def _safe_join(base, *parts):
    path = os.path.normpath(os.path.join(base, *parts))
    if path != base and not path.startswith(base + os.sep):
        return None
    return path


class Handler(BaseHTTPRequestHandler):
    server_version = "RedrawLesson/0.1"

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        ctype, _ = mimetypes.guess_type(path)
        if path.endswith(".webp"):
            ctype = "image/webp"
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            return self._send(404, "not found", "text/plain")
        self._send(200, body, ctype or "application/octet-stream")

    def do_GET(self):  # noqa: N802 (stdlib handler naming)
        url = urlparse(self.path)
        if url.path == "/":
            return self._send_file(os.path.join(STATIC_DIR, "index.html"))
        if url.path == "/setup":
            return self._send_file(os.path.join(STATIC_DIR, "setup.html"))
        if url.path in ("/app.js", "/setup.js", "/styles.css"):
            return self._send_file(_safe_join(
                STATIC_DIR, url.path.lstrip("/")) or "")
        if url.path == "/api/packs":
            try:
                from app.builder import lesson_paths, valid_slug
                out = []
                base = os.path.join(ROOT, "lessons")
                for slug in sorted(os.listdir(base)):
                    if not valid_slug(slug):
                        continue
                    pack_file = lesson_paths(ROOT, slug)["pack"]
                    if not os.path.isfile(pack_file):
                        continue
                    with open(pack_file, encoding="utf-8") as f:
                        pack = json.load(f)
                    out.append({"slug": slug,
                                "topic": pack.get("topic", slug),
                                "steps": len(pack.get("steps", [])),
                                "version": pack.get("version", 1)})
                return self._send(200, json.dumps({"packs": out}),
                                  "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/pack":
            try:
                from app.builder import lesson_paths, valid_slug
                from urllib.parse import parse_qs
                q = parse_qs(urlparse(self.path).query)
                slug = q.get("topic", ["water-cycle"])[0]
                if not valid_slug(slug):
                    raise ValueError("unknown lesson topic")
                pack_file = lesson_paths(ROOT, slug)["pack"]
                if not os.path.isfile(pack_file):
                    raise ValueError("unknown lesson topic")
                return self._send_file(pack_file)
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/captions":
            try:
                from app.builder import (glossary_for, lesson_paths,
                                         valid_slug)
                from app.captions import profile_for, rewrite_captions
                from urllib.parse import parse_qs
                q = parse_qs(urlparse(self.path).query)
                level = q.get("level", ["medium"])[0]
                terms = int(q.get("terms", ["1"])[0])
                if level not in ("short", "medium", "longer"):
                    raise ValueError("level must be short|medium|longer")
                slug = q.get("topic", ["water-cycle"])[0]
                if not valid_slug(slug):
                    raise ValueError("unknown lesson topic")
                lp = lesson_paths(ROOT, slug)
                pack = json.load(open(os.path.join(lp["pack"]),
                                      encoding="utf-8"))
                profile = profile_for(level, terms)
                out, hit = rewrite_captions(
                    get_client(), pack, profile,
                    model=backend_models()["policy_model"],
                    lesson_dir=lp["dir"],
                    glossary=glossary_for(pack))
                return self._send(200, json.dumps(
                    {"captions": out["captions"], "cached": hit,
                     "fallback": out.get("fallback", False)}),
                    "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/backend":
            return self._send(200, json.dumps({"backend": BACKEND}),
                              "application/json")
        if url.path.startswith("/assets/"):
            parts = url.path[len("/assets/"):].split("/")
            if len(parts) < 2:
                return self._send(404, "not found", "text/plain")
            from app.builder import lesson_paths, valid_slug
            if not valid_slug(parts[0]):
                return self._send(404, "not found", "text/plain")
            scenes = lesson_paths(ROOT, parts[0])["scenes"]
            path = _safe_join(scenes, *parts[1:])
            if path and os.path.isfile(path):
                return self._send_file(path)
            return self._send(404, "not found", "text/plain")
        return self._send(404, "not found", "text/plain")

    def log_message(self, *args):
        pass

    def _parse_voice(self):
        ctype = self.headers.get("Content-Type", "")
        boundary = ctype.split("boundary=")[-1].strip().encode()
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        chunks = body.split(b"--" + boundary)
        audio = None
        for chunk in chunks:
            if b'name="audio"' in chunk:
                audio = chunk.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
        if not audio:
            raise ValueError("no audio part")
        return audio

    def do_POST(self):  # noqa: N802 (stdlib handler naming)
        url = urlparse(self.path)
        if url.path == "/api/backend":
            global BACKEND
            try:
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                if body.get("backend") not in ("meta", "baseten"):
                    raise ValueError("backend must be meta or baseten")
                BACKEND = body["backend"]
                return self._send(200, json.dumps({"backend": BACKEND}),
                                  "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/voice":
            try:
                from app.voice import phrase_to_signal, transcribe_wav
                audio = self._parse_voice()
                t0 = time.monotonic()
                out, from_cache = transcribe_wav(audio, cache_dir=CACHE_DIR)
                ms = int((time.monotonic() - t0) * 1000)
                with open(LATENCY_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"route": "voice", "ms": ms,
                                        "cached": from_cache}) + "\n")
                return self._send(200, json.dumps(
                    {"text": out["text"],
                     "signal": phrase_to_signal(out["text"]),
                     "ms": ms, "cached": from_cache}), "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/sayit":
            try:
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                from app.sayit import grade
                pack = json.load(open(os.path.join(LESSON_DIR, "pack.json"),
                                      encoding="utf-8"))
                steps = {s["step"]: s for s in pack["steps"]}
                s = steps[body["step"]]
                t0 = time.monotonic()
                out, from_cache = grade(
                    get_client(), body["answer"], s["say_it"]["answer_key"],
                    s["misconception"], CACHE_DIR,
                    model=backend_models()["sayit_model"],
                    history=body.get("history"))
                ms = int((time.monotonic() - t0) * 1000)
                with open(LATENCY_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"route": "sayit", "ms": ms,
                                        "cached": from_cache}) + "\n")
                return self._send(200, json.dumps(
                    {"result": out, "ms": ms, "cached": from_cache}),
                    "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/report":
            try:
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                from app.report import generate
                t0 = time.monotonic()
                snapshot = {"entries": (body.get("entries") or [])[:200],
                            "mastered": body.get("mastered") or [],
                            "current_step": body.get("current_step", 1),
                            "concepts": body.get("concepts") or {}}
                out, _ = generate(
                    get_client(), snapshot, body.get("profile") or {},
                    model=backend_models().get("policy_model"))
                ms = int((time.monotonic() - t0) * 1000)
                with open(LATENCY_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"route": "report", "ms": ms,
                                        "cached": False}) + "\n")
                return self._send(200, json.dumps(
                    {"result": out, "ms": ms,
                     "fallback": bool(out.get("fallback"))}),
                    "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/build-core":
            # Wonder core + verifier for a parent-chosen topic. Standard
            # mode only: there is no open-weights Wonder equivalent.
            try:
                _needs_meta()
                from app.builder import (PRESET_WORLDS, build_core,
                                         lesson_paths, valid_slug)
                from app.captions import LEVELS
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                slug = body.get("slug", "")
                topic = (body.get("topic") or "").strip()
                facts = [str(f).strip() for f in (body.get("facts") or [])
                         if str(f).strip()]
                if not valid_slug(slug):
                    raise ValueError("bad lesson slug")
                if not topic or len(facts) < 3:
                    raise ValueError(
                        "a topic and at least 3 facts are required")
                worlds = [w for w in (body.get("worlds") or [])
                          if w in PRESET_WORLDS]
                if not worlds:
                    worlds = ["dinosaur_valley", "block_world"]
                profile = body.get("profile") or {}
                level = profile.get("level", "medium")
                if level not in LEVELS:
                    raise ValueError("level must be short|medium|longer")
                lv = LEVELS[level]
                age = str(profile.get("age", "7-8")).split("\u2013")[0]
                age = int(age.split("-")[0]) if age.split("-")[0].isdigit() \
                    else 8
                tiers = {"age": age,
                         "max_words": lv["max_words_per_sentence"],
                         "longest": lv["longest_sentence"],
                         "new_terms": int(profile.get("terms", 1))}
                lp = lesson_paths(ROOT, slug)
                os.makedirs(lp["dir"], exist_ok=True)
                client = get_client()
                if client is None:
                    raise ValueError("MODEL_API_KEY is missing")
                t0 = time.monotonic()
                pack, verdicts, cached = build_core(
                    client, lp, slug, topic, facts, tiers, worlds)
                ms = int((time.monotonic() - t0) * 1000)
                with open(LATENCY_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"route": "build-core", "ms": ms,
                                        "cached": cached}) + "\n")
                return self._send(200, json.dumps(
                    {"pack": pack, "verdicts": verdicts, "cached": cached}),
                    "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/verify":
            # Re-run the Wonder verifier after a parent edits wording.
            try:
                _needs_meta()
                from app.builder import lesson_paths, valid_slug, verify_pack
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                slug = body.get("slug", "")
                if not valid_slug(slug):
                    raise ValueError("bad lesson slug")
                lp = lesson_paths(ROOT, slug)
                if not os.path.isfile(lp["pack"]):
                    raise ValueError("unknown lesson topic")
                client = get_client()
                if client is None:
                    raise ValueError("MODEL_API_KEY is missing")
                verdicts = verify_pack(client, lp, refresh=True)
                return self._send(200, json.dumps({"verdicts": verdicts}),
                                  "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/analogy":
            # Custom-world analogies (Spark) merged into the pack, then
            # verifier-checked for that world before returning. Standard
            # mode only: the checker needs Wonder.
            try:
                _needs_meta()
                from app.builder import (build_custom_analogy, lesson_paths,
                                         valid_slug, verify_pack)
                from app.contracts import validate
                from app.builder import PACK_SCHEMA
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                slug = body.get("slug", "")
                world = body.get("world", "")
                description = (body.get("description") or "").strip()
                if not valid_slug(slug):
                    raise ValueError("bad lesson slug")
                if not re.match(r"^[a-z0-9_]{1,40}$", world):
                    raise ValueError("bad world id")
                if not description:
                    raise ValueError("a world description is required")
                lp = lesson_paths(ROOT, slug)
                with open(lp["pack"], encoding="utf-8") as f:
                    pack = json.load(f)
                client = get_client()
                if client is None:
                    raise ValueError("MODEL_API_KEY is missing")
                texts = build_custom_analogy(
                    client, backend_models()["policy_model"], pack, world,
                    description)
                for s in pack["steps"]:
                    s["analogies"][world] = texts[s["step"]]
                validate(PACK_SCHEMA, {"steps": pack["steps"]})
                verdicts = verify_pack(client, lp, worlds=[world],
                                       refresh=True)
                if any(v["accurate"] == "no" for v in verdicts):
                    raise ValueError("checker rejected the new analogies: "
                                     + "; ".join(
                                         v["issue"] for v in verdicts
                                         if v["accurate"] == "no"))
                with open(lp["pack"], "w", encoding="utf-8") as f:
                    json.dump(pack, f, indent=2, ensure_ascii=False)
                return self._send(200, json.dumps(
                    {"pack": pack, "verdicts": verdicts}),
                    "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path == "/api/build-scenes":
            # Images (D26 edits-first) + SAM masks for chosen worlds.
            # Synchronous: build one world first, the rest after.
            try:
                _needs_meta()
                from app.builder import (PRESET_WORLDS, get_scene_image,
                                         lesson_paths, valid_slug)
                from app.sam_segment import segment_scene
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                slug = body.get("slug", "")
                if not valid_slug(slug):
                    raise ValueError("bad lesson slug")
                lp = lesson_paths(ROOT, slug)
                with open(lp["pack"], encoding="utf-8") as f:
                    pack = json.load(f)
                worlds = [w for w in (body.get("worlds") or [])
                          if w in PRESET_WORLDS]
                if not worlds:
                    raise ValueError("at least one world is required")
                steps = [s for s in pack["steps"]
                         if not body.get("steps")
                         or s["step"] in body["steps"]]
                client = get_client()
                if client is None:
                    raise ValueError("MODEL_API_KEY is missing")
                t0 = time.monotonic()
                out = []
                for world in worlds:
                    prior = None
                    for s in steps:
                        img, method = get_scene_image(
                            client, lp, s, world, PRESET_WORLDS,
                            prior_path=prior)
                        prior = img
                        sam = segment_scene(
                            client, lp["dir"], lp["cache"], s["step"],
                            s["tap_question"]["target_noun"], world)
                        out.append({"step": s["step"], "world": world,
                                    "image": os.path.basename(img),
                                    "method": method, "sam": sam})
                ms = int((time.monotonic() - t0) * 1000)
                with open(LATENCY_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"route": "build-scenes", "ms": ms,
                                        "cached": False}) + "\n")
                return self._send(200, json.dumps({"scenes": out}),
                                  "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path.startswith("/api/packs/"):
            # Persist a reviewed pack (validated, version-bumped).
            try:
                from app.builder import (PACK_SCHEMA, lesson_paths,
                                         valid_slug)
                from app.contracts import validate
                slug = url.path[len("/api/packs/"):]
                if not valid_slug(slug):
                    raise ValueError("bad lesson slug")
                body = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                pack = body.get("pack")
                if not isinstance(pack, dict):
                    raise ValueError("pack object required")
                validate(PACK_SCHEMA, {"steps": pack.get("steps")})
                lp = lesson_paths(ROOT, slug)
                os.makedirs(lp["dir"], exist_ok=True)
                if body.get("brief") is not None:
                    with open(lp["brief"], "w", encoding="utf-8") as f:
                        f.write(str(body["brief"]))
                version = 1
                if os.path.isfile(lp["pack"]):
                    with open(lp["pack"], encoding="utf-8") as f:
                        try:
                            version = int(json.load(f).get("version", 0)) + 1
                        except (ValueError, TypeError):
                            version = 1
                pack["slug"] = slug
                pack["version"] = version
                with open(lp["pack"], "w", encoding="utf-8") as f:
                    json.dump(pack, f, indent=2, ensure_ascii=False)
                return self._send(200, json.dumps(
                    {"slug": slug, "version": version}),
                    "application/json")
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}),
                                  "application/json")
        if url.path != "/api/policy":
            return self._send(404, "not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(
                int(self.headers.get("Content-Length", 0))) or b"{}")
            t0 = time.monotonic()
            fsm_state = (body.get("fsm") or {}).get("state", "PRESENT")
            decision, from_cache = decide(
                get_client(), body["signal"], body["step"], body["learner"],
                CACHE_DIR, model=backend_models()["policy_model"],
                fsm_state=fsm_state)
            ms = int((time.monotonic() - t0) * 1000)
            with open(LATENCY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"route": "policy", "ms": ms,
                                    "cached": from_cache}) + "\n")
            return self._send(200, json.dumps({"decision": decision,
                                              "ms": ms,
                                              "cached": from_cache,
                                              "fsm_state": fsm_state,
                                              "next_state": next_state_for(
                                                  fsm_state, body["signal"])}),
                              "application/json")
        except Exception as e:
            return self._send(400, json.dumps({"error": str(e)}),
                              "application/json")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Redraw lesson at http://127.0.0.1:{args.port}/ (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
