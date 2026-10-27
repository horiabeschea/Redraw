import os, json
from openai import OpenAI

client = OpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])

# load the brief from lessons/water-cycle/brief.md
BRIEF_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                           "lessons", "water-cycle", "brief.md")
with open(os.path.normpath(BRIEF_PATH), encoding="utf-8") as f:
    BRIEF = f.read()

step_schema = {
  "type": "object",
  "properties": {
    "caption": {"type": "string"},
    "simpler_caption": {"type": "string"},
    "misconception": {"type": "string"},
    "correction": {"type": "string"},
    "analogies": {"type": "object", "additionalProperties": {"type": "string"}},
    "tap_question": {"type": "object", "properties": {
        "prompt": {"type": "string"}, "target_noun": {"type": "string"}},
        "required": ["prompt", "target_noun"], "additionalProperties": False},
    "say_it": {"type": "object", "properties": {
        "prompt": {"type": "string"}, "answer_key": {"type": "string"}},
        "required": ["prompt", "answer_key"], "additionalProperties": False},
    "image_prompts": {"type": "object", "additionalProperties": {"type": "string"}},
  },
  "required": ["caption", "simpler_caption", "misconception", "correction",
               "analogies", "tap_question", "say_it", "image_prompts"],
  "additionalProperties": False,
}

resp = client.responses.create(
    model="muse-wonder-1.0",
    reasoning={"effort": "medium"},
    input=BRIEF,
    text={"format": {"type": "json_schema", "name": "lesson_step",
                     "strict": False, "schema": step_schema}},
)
step1 = json.loads(resp.output_text)

# export the received lesson to the lessons folder (scratch probe output goes
# to .cache so it never overwrites the 5-step pack.json)
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                         "lessons", "water-cycle", ".cache",
                         "test_wonder_step1.json")
with open(os.path.normpath(OUT_PATH), "w", encoding="utf-8") as f:
    json.dump(step1, f, indent=2, ensure_ascii=False)
print(f"wrote {os.path.normpath(OUT_PATH)}")