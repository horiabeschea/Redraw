import os
from openai import OpenAI

api_key=os.environ["BASETEN_API_KEY"]

client = OpenAI(
    base_url="https://inference.baseten.co/v1",
    api_key=api_key,
)

response = client.chat.completions.create(
    model="meta-models/muse-spark-open-1026",
    messages=[{"role": "user", "content": "Hello!"}],
)

with open(os.path.join(os.path.dirname(__file__), "test_baseten-evidence.json"), "w") as evidence_file:
    evidence_file.write(response.model_dump_json(indent=2))


# print(response.choices[0].message.content)