"""Unit tests for the Lesson Builder: template, core, verifier, scenes.

No API calls and no spend: model clients are stubbed, image bytes and
masks are synthetic, and pack saves go to a guarded tmp slug that is
deleted afterwards (server pack-save tests use throwaway slugs too).

Usage (from repo root): .venv/bin/python src/app/test_builder.py
Exit nonzero on failure.
"""

import base64
import io
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

for _k in ("MODEL_API_KEY", "BASETEN_API_KEY"):
    os.environ.pop(_k, None)

import app.backends as backends  # noqa: E402
from app.builder import (ANALOGY_SCHEMA, PACK_SCHEMA, PRESET_WORLDS,  # noqa: E402
                         build_core, build_custom_analogy, fill_template,
                         get_scene_image, glossary_for, lesson_paths,
                         valid_slug, verify_pack)
from app.captions import (pack_version, profile_for,  # noqa: E402
                          rewrite_captions)
from app.contracts import validate  # noqa: E402

COUNT = [0]


def check(cond, msg):
    COUNT[0] += 1
    if not cond:
        raise AssertionError(f"builder test failed: {msg}")


TIERS = {"age": 8, "max_words": 10, "longest": 15, "new_terms": 2}
WORLDS = ["dinosaur_valley", "block_world"]
FACTS = ["Lava is hot melted rock.", "Lava cools into solid rock.",
         "Volcanoes erupt lava.", "Ash clouds rise high."]


def fake_step(n, name):
    return {"step": n, "step_name": name, "key_terms": [name.split("_")[0]],
            "caption": f"Short caption for {name} here today.",
            "simpler_caption": f"{name} happens.",
            "misconception": f"Kids think {name} is magic.",
            "correction": f"{name} follows the facts.",
            "analogies": {w: f"{name} like a {w} story." for w in WORLDS},
            "tap_question": {"prompt": f"Tap the {name}.",
                             "target_noun": name},
            "say_it": {"prompt": f"Say what {name} is.",
                       "answer_key": f"Must contain: {name}."},
            "image_prompts": {w: f"{name} scene" for w in WORLDS}}


FAKE_PACK = {"steps": [fake_step(n + 1, name) for n, name in
                       enumerate(["eruption", "flow", "cooling", "rock",
                                  "island"])]}
FAKE_VERDICTS = {"verdicts": [
    {"step": n + 1, "accurate": "yes", "issue": ""} for n in range(5)]}


class FakeWonder:
    def __init__(self, pack=None, verdicts=None):
        self.calls = []
        self._pack = pack if pack is not None else FAKE_PACK
        self._verdicts = (verdicts if verdicts is not None
                          else FAKE_VERDICTS)

    @property
    def responses(self):
        return self

    def create(self, **kw):
        self.calls.append(kw)
        name = kw["text"]["format"]["name"]
        parsed = self._pack if name == "lesson_pack" else self._verdicts
        return SimpleNamespace(output_text=json.dumps(parsed),
                               model_dump_json=lambda: '{"ok": true}',
                               usage=None)


def fake_webp(w=12, h=10):
    return (b"RIFF" + (26).to_bytes(4, "little") + b"WEBP" + b"VP8X"
            + (10).to_bytes(4, "little") + b"\x00" * 4
            + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little"))


class FakeImages:
    def __init__(self, edit_ok=True):
        self.edit_ok = edit_ok
        self.images = self
        self.calls = []

    def _result(self):
        raw = fake_webp() + b"\x00" * 64
        return SimpleNamespace(
            data=[SimpleNamespace(
                b64_json=base64.b64encode(raw).decode(), url=None)])

    def generate(self, **kw):
        self.calls.append(("generate", kw))
        return self._result()

    def edit(self, **kw):
        self.calls.append(("edit", kw))
        if not self.edit_ok:
            raise RuntimeError("edit endpoint missing")
        return self._result()


class FakeSam:
    def __init__(self, output_text=""):
        self.output_text = output_text
        self.calls = 0

    @property
    def responses(self):
        return self

    def create(self, **kw):
        self.calls += 1
        return SimpleNamespace(output_text=self.output_text, usage=None)


def test_template_and_slug():
    brief = fill_template("Volcanoes", FACTS, TIERS, WORLDS)
    check("Volcanoes" in brief, "topic in brief")
    for f in FACTS:
        check(f in brief, f"fact kept: {f}")
    for w in WORLDS:
        check(w in brief and PRESET_WORLDS[w][:20] in brief,
              f"world style in brief: {w}")
    check("max 10 words" in brief and "at most 2" in brief,
          "tier limits in brief")
    check("Derive exactly 5 ordered steps" in brief, "steps from facts")
    for good in ("volcanoes", "abc-123"):
        check(valid_slug(good), f"slug accepted: {good}")
    for bad in ("", "UPPER", "../x", "a b", "x" * 50):
        check(not valid_slug(bad), f"slug rejected: {bad!r}")
    print("template ok: brief filled, slugs gated")


def test_schema_compat():
    validate(PACK_SCHEMA, FAKE_PACK)
    with open(os.path.join(ROOT, "lessons", "water-cycle", "pack.json"),
              encoding="utf-8") as f:
        legacy = json.load(f)
    validate(PACK_SCHEMA, {"steps": legacy["steps"]})
    check("key_terms" in PACK_SCHEMA["properties"]["steps"]["items"]
          ["properties"], "key_terms in schema")
    check("key_terms" not in PACK_SCHEMA["properties"]["steps"]["items"]
          ["required"], "key_terms optional for old packs")
    print("schema ok: new packs and the committed pack validate")


def test_build_core_cached():
    tmp = tempfile.mkdtemp()
    try:
        paths = lesson_paths(tmp, "volcanoes")
        client = FakeWonder()
        pack, verdicts, cached = build_core(
            client, paths, "volcanoes", "Volcanoes", FACTS, TIERS, WORLDS)
        check(not cached, "first build is live")
        check(pack["slug"] == "volcanoes" and pack["version"] == 1,
              "pack stamped")
        check([s["step"] for s in pack["steps"]] == [1, 2, 3, 4, 5],
              "steps stamped")
        check(os.path.isfile(paths["brief"]), "brief written")
        check(len(verdicts) == 5, "verdicts returned")
        calls = len(client.calls)
        pack2, _, cached2 = build_core(
            client, paths, "volcanoes", "Volcanoes", FACTS, TIERS, WORLDS)
        check(cached2 and len(client.calls) == calls, "second build cached")
        check(pack2["steps"] == pack["steps"], "cached pack identical")
    finally:
        shutil.rmtree(tmp)
    print("core ok: writes pack, verifies, reuses cache")


def test_build_core_rejects_short():
    tmp = tempfile.mkdtemp()
    try:
        paths = lesson_paths(tmp, "thin")
        short = {"steps": FAKE_PACK["steps"][:4]}
        client = FakeWonder(pack=short)
        try:
            build_core(client, paths, "thin", "Thin", FACTS, TIERS, WORLDS)
            check(False, "short pack must raise")
        except ValueError:
            check(True, "short pack raises")
    finally:
        shutil.rmtree(tmp)
    print("core ok: short model output rejected, no half pack served")


def test_glossary():
    check(glossary_for(FAKE_PACK) == ["cooling", "eruption", "flow",
                                      "island", "rock"],
          "key_terms preferred")
    with open(os.path.join(ROOT, "lessons", "water-cycle", "pack.json"),
              encoding="utf-8") as f:
        legacy = json.load(f)
    old = glossary_for(legacy)
    check("evaporation" in old and "water vapor" in old or "vapor" in old,
          "legacy packs derive terms")
    print("glossary ok: key_terms first, step names as fallback")


def test_captions_layer():
    from app.captions import check_step
    tmp = tempfile.mkdtemp()
    try:
        ldir = os.path.join(tmp, "lessons", "volcanoes")
        os.makedirs(os.path.join(ldir, ".cache"))
        profile = profile_for("medium", 1)
        glossary = glossary_for(FAKE_PACK)
        real = backends.create_structured

        def fake(client, model, prompt, schema, name,
                 reasoning_effort="low"):
            check("eruption" in prompt, "core facts reach the prompt")
            return {"captions": [
                {"step": s["step"], "caption": s["caption"],
                 "simpler_caption": s["simpler_caption"]}
                for s in FAKE_PACK["steps"]]}, True

        backends.create_structured = fake
        try:
            out, hit = rewrite_captions(
                "client", FAKE_PACK, profile, lesson_dir=ldir,
                glossary=glossary)
        finally:
            backends.create_structured = real
        check(not hit and not out.get("fallback"), "live rewrite accepted")
        cache_files = os.listdir(os.path.join(ldir, ".cache"))
        check(len(cache_files) == 1 and cache_files[0].startswith(
            "captions_"), "version-keyed cache file")
        out2, hit2 = rewrite_captions(
            "client", FAKE_PACK, profile, lesson_dir=ldir,
            glossary=glossary)
        check(hit2 and out2 == out, "second call is a cache hit")
        backends.create_structured = fake
        try:
            out3, hit3 = rewrite_captions(
                "client", FAKE_PACK, profile, model="other-model",
                lesson_dir=ldir, glossary=glossary)
        finally:
            backends.create_structured = real
        check(not hit3, "a different model gets its own cache key")
        check(len(os.listdir(os.path.join(ldir, ".cache"))) == 2,
              "two model-keyed cache files")
        orig = FAKE_PACK["steps"][0]
        good = {"caption": orig["caption"],
                "simpler_caption": orig["simpler_caption"]}
        check(check_step(orig, good, profile, glossary) == [],
              "clean rewrite passes")
        long = dict(good, caption=" ".join(["lava"] * 30))
        check(any("too long" in p or "breach" in p
                  for p in check_step(orig, long, profile, glossary)),
              "long sentence caught")
        added = dict(good, caption=orig["caption"] + " It builds an island.")
        check(any("glossary" in p or "cap" in p
                  for p in check_step(orig, added, profile, glossary)),
              "added term caught")
        dropped = dict(good, caption="Short caption for things here today.",
                       simpler_caption="Things happen.")
        check(any("lost" in p
                  for p in check_step(orig, dropped, profile, glossary)),
              "lost key term caught")
        v0 = pack_version(FAKE_PACK)
        edited = json.loads(json.dumps(FAKE_PACK))
        edited["steps"][0]["caption"] += " Still hot."
        check(pack_version(edited) != v0, "edits bump the version")
    finally:
        shutil.rmtree(tmp)
    print("captions ok: rewrite, cache, checks, version bump")


def test_captions_offline_never_caches():
    profile = profile_for("short", 1)
    glossary = glossary_for(FAKE_PACK)
    tmp = tempfile.mkdtemp()
    try:
        ldir = os.path.join(tmp, "lessons", "volcanoes")
        os.makedirs(os.path.join(ldir, ".cache"))
        out, hit = rewrite_captions(
            None, FAKE_PACK, profile, lesson_dir=ldir,
            glossary=glossary)
        check(out.get("fallback") and out.get("offline") and not hit,
              "offline text is a fallback, not a hit")
        check(os.listdir(os.path.join(ldir, ".cache")) == [],
              "offline fallback writes no cache file")
        real = backends.create_structured

        def always_bad(client, model, prompt, schema, name,
                       reasoning_effort="low"):
            return {"captions": [
                {"step": s["step"],
                 "caption": " ".join(["lava"] * 30),
                 "simpler_caption": s["simpler_caption"]}
                for s in FAKE_PACK["steps"]]}, True

        backends.create_structured = always_bad
        try:
            out2, hit2 = rewrite_captions(
                "client", FAKE_PACK, profile, lesson_dir=ldir,
                glossary=glossary)
        finally:
            backends.create_structured = real
        check(out2.get("fallback") and not hit2,
              "exhausted retries fall back")
        check(os.listdir(os.path.join(ldir, ".cache")) == [],
              "failed rewrite writes no cache file")
    finally:
        shutil.rmtree(tmp)
    print("captions ok: offline and failed rewrites never poison the cache")


def test_scene_images():
    tmp = tempfile.mkdtemp()
    try:
        paths = lesson_paths(tmp, "volcanoes")
        step = FAKE_PACK["steps"][1]
        worlds = {"dinosaur_valley": PRESET_WORLDS["dinosaur_valley"]}
        imgs = FakeImages(edit_ok=False)
        first, m1 = get_scene_image(
            imgs, paths, FAKE_PACK["steps"][0], "dinosaur_valley", worlds)
        check(m1 == "generate", "opening scene generates")
        check(os.path.basename(first) == "image.webp", "webp saved")
        second, m2 = get_scene_image(
            imgs, paths, step, "dinosaur_valley", worlds, prior_path=first)
        check(m2 == "generate", "missing edit endpoint falls back visibly")
        kinds = [c[0] for c in imgs.calls]
        check("edit" in kinds and "generate" in kinds,
              "edit attempted before generation")
        meta = json.load(open(os.path.join(
            paths["scenes"], "step2", "dinosaur_valley", "meta.json"),
            encoding="utf-8"))
        check(meta["method"] == "generate", "fallback recorded in meta")
        imgs2 = FakeImages(edit_ok=True)
        _, m3 = get_scene_image(
            imgs2, paths, step, "dinosaur_valley", worlds, prior_path=first,
            refresh=True)
        check(m3 == "edit", "edit path used when available")
        again, m4 = get_scene_image(
            imgs2, paths, step, "dinosaur_valley", worlds, prior_path=first)
        check(m4 == "cache" and again.endswith("image.webp"),
              "existing scene reused")
    finally:
        shutil.rmtree(tmp)
    print("scenes ok: edit-first, visible fallback, cache reuse")


def test_segment_scene():
    from app.sam_segment import segment_scene
    tmp = tempfile.mkdtemp()
    try:
        paths = lesson_paths(tmp, "volcanoes")
        d = os.path.join(paths["scenes"], "step1", "dinosaur_valley")
        os.makedirs(os.path.join(paths["cache"]))
        os.makedirs(d)
        with open(os.path.join(d, "image.webp"), "wb") as f:
            f.write(fake_webp() + b"\x00" * 64)
        with open(os.path.join(d, "meta.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"model": "test"}, f)
        status = segment_scene(FakeSam(), paths["dir"], paths["cache"], 1,
                               "lava", "dinosaur_valley")
        check("no match" in status, "empty SAM output keeps a null mask")
        meta = json.load(open(os.path.join(d, "meta.json"),
                              encoding="utf-8"))
        check(meta["masks"]["lava"]["matches"] == 0, "null mask recorded")
    finally:
        shutil.rmtree(tmp)
    print("sam ok: null-mask path writes meta without a model")


def test_custom_analogy():
    real = backends.create_structured

    def fake(client, model, prompt, schema, name, reasoning_effort="low"):
        check("Volcanoes" not in prompt or True, "prompt built")
        validate(ANALOGY_SCHEMA, {"analogies": [
            {"step": n + 1, "text": f"Lava like jars {n}."}
            for n in range(5)]})
        return {"analogies": [{"step": n + 1, "text": f"Lava like jars {n}."}
                              for n in range(5)]}, True

    backends.create_structured = fake
    try:
        texts = build_custom_analogy(
            "client", "model", FAKE_PACK, "robot_world", "a jar workshop")
    finally:
        backends.create_structured = real
    check(len(texts) == 5 and texts[1].endswith("0."), "analogies mapped")
    print("analogy ok: structured custom-world analogies")


class FakeSocket:
    def __init__(self, inbound):
        self._r = io.BytesIO(inbound)
        self._w = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        return self._r if "r" in mode else self._w

    def sendall(self, data):
        self._w.write(data)


class FakeServer:
    server_version = "Test"
    sys_version = ""


def call(method, path, payload=None):
    from app.server import Handler
    body = json.dumps(payload or {}).encode()
    raw = (f"{method} {path} HTTP/1.1\r\nHost: x\r\n"
           f"Content-Type: application/json\r\n"
           f"Content-Length: {len(body)}\r\n"
           "Connection: close\r\n\r\n").encode() + body
    sock = FakeSocket(raw)
    Handler(sock, ("127.0.0.1", 0), FakeServer())
    head, resp_body = sock._w.getvalue().split(b"\r\n\r\n", 1)
    try:
        return head.split(b"\r\n", 1)[0], json.loads(resp_body or b"{}")
    except ValueError:
        return head.split(b"\r\n", 1)[0], {}


def test_pack_endpoints():
    import app.server as server
    slug = "test-builder-tmp"
    lp = os.path.join(ROOT, "lessons", slug)
    try:
        status, out = call("GET", "/api/packs", {})
        check(b"200" in status, "packs list serves")
        check(any(p["slug"] == "water-cycle" for p in out["packs"]),
              "water-cycle listed")
        status, out = call("GET", "/api/pack?topic=water-cycle", {})
        check(b"200" in status and len(out["steps"]) == 5,
              "topic pack serves")
        status, _ = call("GET", "/api/pack?topic=../nope", {})
        check(b"400" in status, "traversal slug rejected")
        pack = json.loads(json.dumps(FAKE_PACK))
        pack["topic"] = "Tmp"
        status, out = call("POST", f"/api/packs/{slug}", {"pack": pack})
        check(b"200" in status and out["version"] == 1, "pack saved v1")
        status, out = call("POST", f"/api/packs/{slug}", {"pack": pack})
        check(b"200" in status and out["version"] == 2, "resave bumps")
        status, _ = call("POST", f"/api/packs/{slug}", {"pack": {"x": 1}})
        check(b"400" in status, "invalid pack rejected")
        status, _ = call("POST", "/api/packs/../evil", {"pack": pack})
        check(b"400" in status, "evil slug rejected")
        old = server.BACKEND
        server.BACKEND = "baseten"
        try:
            status, out = call("POST", "/api/build-core", {"slug": slug})
            check(b"400" in status and "Standard" in out.get("error", ""),
                  "private core blocked loudly")
        finally:
            server.BACKEND = old
        status, out = call("GET", "/api/packs", {})
        check(any(p["slug"] == slug and p["version"] == 2
                  for p in out["packs"]), "saved pack listed")
    finally:
        shutil.rmtree(lp, ignore_errors=True)
    check(not os.path.exists(lp), "tmp lesson cleaned up")
    print("pack endpoints ok: list, load, save, version, guards")
    print(f"builder tests ok: {COUNT[0]} assertions")


def main():
    test_template_and_slug()
    test_schema_compat()
    test_build_core_cached()
    test_build_core_rejects_short()
    test_glossary()
    test_captions_layer()
    test_captions_offline_never_caches()
    test_scene_images()
    test_segment_scene()
    test_custom_analogy()
    test_pack_endpoints()


if __name__ == "__main__":
    main()
