"""Backend connectors: Meta Model API (default) and Baseten (private mode).

Baseten Model APIs are OpenAI-compatible: same SDK, base_url
https://inference.baseten.co/v1, key from BASETEN_API_KEY, model slug
"meta-models/muse-spark-open-1026". Private mode routes the policy and
say-it grading here so child transcripts stay off third-party training
pipelines.

Strict structured output may not be supported on every backend: create()
tries strict True first, then retries with strict False and enforces the
schema locally with contracts.validate. Either way the returned dict is
schema-valid or an exception raises.
"""

import json
import os

BACKENDS = {
    "meta": {
        "base_url": "https://api.meta.ai/v1",
        "api_key_env": "MODEL_API_KEY",
        "policy_model": "muse-spark-1.3",
        "sayit_model": "muse-spark-1.3",
    },
    "baseten": {
        "base_url": "https://inference.baseten.co/v1",
        "api_key_env": "BASETEN_API_KEY",
        "policy_model": "meta-models/muse-spark-open-1026",
        "sayit_model": "meta-models/muse-spark-open-1026",
    },
}


def get_client(backend="meta"):
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend '{backend}'")
    key = os.environ.get(BACKENDS[backend]["api_key_env"])
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(base_url=BACKENDS[backend]["base_url"], api_key=key)


def create_structured(client, model, input_text, schema, name,
                      reasoning_effort="low"):
    """Responses call with strict-first, validated fallback."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from app.contracts import validate
    last = None
    for strict in (True, False):
        try:
            resp = client.responses.create(
                model=model,
                reasoning={"effort": reasoning_effort},
                input=input_text,
                text={"format": {"type": "json_schema", "name": name,
                                 "strict": strict, "schema": schema}},
            )
            out = json.loads(resp.output_text)
            validate(schema, out)
            return out, strict
        except Exception as e:  # noqa: BLE001 (fallback across backends)
            last = e
    raise last
