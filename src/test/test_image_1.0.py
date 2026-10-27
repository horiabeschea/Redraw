import base64
import json
import os
import urllib.request
from openai import OpenAI

client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])

PROMPT = ("A calm lake at the left, sun at top right, hills at the back, "
          "a river at the right. Soft colours, children's book style. "
          "No text, no letters, no numbers, no people.")

resp = client.images.generate(
    model="muse-image-1.0",
    prompt=PROMPT,
    size="1024x1024",
)
data = resp.data[0]

# export the received image to the lessons folder (scratch probe output goes
# to .cache so it never touches the pack or the scenes)
OUT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..",
                                        "lessons", "water-cycle", ".cache"))
os.makedirs(OUT_DIR, exist_ok=True)

if data.b64_json:
    raw = base64.b64decode(data.b64_json)
    saved_from = "b64_json"
else:
    with urllib.request.urlopen(data.url) as r:
        raw = r.read()
    saved_from = "url"

ext = ".webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else ".png"
img_path = os.path.join(OUT_DIR, "test_image_1.0" + ext)
with open(img_path, "wb") as f:
    f.write(raw)

meta = {"model": "muse-image-1.0", "size": "1024x1024",
        "saved_from": saved_from, "format": ext.lstrip("."),
        "prompt": PROMPT}
if getattr(data, "revised_prompt", None):
    meta["revised_prompt"] = data.revised_prompt
with open(os.path.join(OUT_DIR, "test_image_1.0_meta.json"), "w",
          encoding="utf-8") as f:
    json.dump(meta, f, indent=2)

print(f"wrote {img_path} ({len(raw)} bytes)")
