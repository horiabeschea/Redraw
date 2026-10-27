"""Redraw lesson server (standard library only).

Serves the lesson screen and the golden set offline:
  /                     the lesson screen
  /app.js, /styles.css  page assets
  /api/pack             lessons/water-cycle/pack.json
  /assets/<step>/<world>/<file>   scene files (image/simpler/mask/prompts)

Planned endpoints (added with later plan steps, same route table shape):
  POST /api/policy   adaptation decisions (Muse Spark 1.3)
  POST /api/sayit    say-it grading (Muse Spark 1.3)
  WS   /api/voice    Voice Transcribe proxy

NOTE: the decided stack is FastAPI on Modal (D4/D15). PyPI is unreachable
from the dev environment, so local serving uses this stdlib adapter with an
identical route layout; the handlers port one-to-one to FastAPI on deploy.

Usage: .venv/bin/python src/app/server.py [--port 8000]
"""

import argparse
import json
import mimetypes
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.policy import decide

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
LESSON_DIR = os.path.join(ROOT, "lessons", "water-cycle")
CACHE_DIR = os.path.join(LESSON_DIR, ".cache")
LATENCY_LOG = os.path.join(CACHE_DIR, "latency.jsonl")
BACKEND = os.environ.get("REDRAW_BACKEND", "meta")

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
        if url.path in ("/app.js", "/styles.css"):
            return self._send_file(_safe_join(
                STATIC_DIR, url.path.lstrip("/")) or "")
        if url.path == "/api/pack":
            return self._send_file(os.path.join(LESSON_DIR, "pack.json"))
        if url.path == "/api/backend":
            return self._send(200, json.dumps({"backend": BACKEND}),
                              "application/json")
        if url.path.startswith("/assets/"):
            path = _safe_join(SCENES_DIR, *url.path[len("/assets/"):].split("/"))
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
                    model=backend_models()["sayit_model"])
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
        if url.path != "/api/policy":
            return self._send(404, "not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(
                int(self.headers.get("Content-Length", 0))) or b"{}")
            t0 = time.monotonic()
            decision, from_cache = decide(
                get_client(), body["signal"], body["step"], body["learner"],
                CACHE_DIR, model=backend_models()["policy_model"])
            ms = int((time.monotonic() - t0) * 1000)
            with open(LATENCY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({"route": "policy", "ms": ms,
                                    "cached": from_cache}) + "\n")
            return self._send(200, json.dumps({"decision": decision,
                                              "ms": ms,
                                              "cached": from_cache}),
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
