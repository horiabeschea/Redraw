"""Contracts for the Redraw adaptation loop.

ADAPTATION_DECISION_SCHEMA: what the policy (Muse Spark 1.3, strict mode)
must return on every turn. Fixed keys only, so it is strict-compatible.
LEARNER_STATE_SCHEMA: the learner model the policy reads and updates.

`validate(schema, value)` is a minimal hand-rolled checker (no third-party
dependency): it enforces type, required, enum, minimum/maximum,
minItems/maxItems, properties, items, and additionalProperties: False.
It raises ValueError with a path on the first violation.
"""

ADAPTATION_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "signal": {"type": "string",
                   "enum": ["stuck", "bored", "explore"]},
        "strategy": {"type": "string",
                     "enum": ["simplify_language", "redraw_simpler",
                              "simplify_max", "offer_support",
                              "raise_challenge", "switch_to_tap_game",
                              "advance"]},
        "target_concept": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["signal", "strategy", "target_concept", "reason"],
    "additionalProperties": False,
}

LEARNER_STATE_SCHEMA = {
    "type": "object",
    "properties": {
        "current_step": {"type": "integer", "minimum": 1, "maximum": 5},
        "world": {"type": "string",
                  "enum": ["dinosaur_valley", "block_world"]},
        "mastered": {"type": "array", "items": {"type": "string"}},
        "stuck_count": {"type": "integer", "minimum": 0},
        "bored_count": {"type": "integer", "minimum": 0},
    },
    "required": ["current_step", "world", "mastered",
                 "stuck_count", "bored_count"],
    "additionalProperties": False,
}


def validate(schema, value, path="$"):
    stype = schema.get("type")
    if stype == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected object")
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}: missing required key '{key}'")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(schema.get("properties", {}))
            if extra:
                raise ValueError(f"{path}: unexpected keys {sorted(extra)}")
        for key, subschema in schema.get("properties", {}).items():
            if key in value:
                validate(subschema, value[key], f"{path}.{key}")
    elif stype == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected array")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValueError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path}: too many items")
        for i, item in enumerate(value):
            validate(schema["items"], item, f"{path}[{i}]")
    elif stype == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path}: expected string")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{path}: '{value}' not in {schema['enum']}")
    elif stype == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{path}: expected integer")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path}: above maximum")
    else:
        raise ValueError(f"{path}: unsupported schema type '{stype}'")
    return True
