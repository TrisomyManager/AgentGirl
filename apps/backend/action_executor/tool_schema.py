"""Canonical JSON Schema for tool consumers; host identity is never model input."""

from copy import deepcopy

from jsonschema import Draft202012Validator

_IDENTITY = {"user_id", "session_id", "turn_id", "operation_id"}
_READ_ONLY = {"get_time", "get_weather", "query_memory", "list_reminders", "list_devices", "web_search", "device_ping"}


def builtin_schema(name: str) -> dict | None:
    string = {"type": "string", "minLength": 1, "maxLength": 12000}
    schemas = {
        "get_time": {},
        "list_reminders": {},
        "list_devices": {},
        "query_memory": {"query": string},
        "get_weather": {"location": string},
        "web_search": {"query": string},
        "set_reminder": {
            "text": string,
            "delay_seconds": {"type": "integer", "minimum": 1, "maximum": 31536000},
            "fire_at": {"type": "string", "format": "date-time"},
            "raw_text": string,
            "repeat_interval_seconds": {"type": "integer", "minimum": 60, "maximum": 31536000},
        },
        "cancel_reminder": {"id": string, "raw_text": string},
        "timer_countdown": {
            "duration_seconds": {"type": "integer", "minimum": 1, "maximum": 31536000},
            "label": string,
            "raw_text": string,
        },
        "update_user_profile": {"field": {"type": "string", "minLength": 1, "maxLength": 64}, "value": string},
        "device_ping": {"device_id": string},
        "device_notify": {"text": string, "device_id": string},
        "device_open_url": {"url": {"type": "string", "pattern": "^https?://", "maxLength": 2048}, "device_id": string},
    }
    if name not in schemas:
        return None
    result = {"type": "object", "properties": deepcopy(schemas[name]), "additionalProperties": False}
    required = {
        "get_weather": ["location"],
        "web_search": ["query"],
        "update_user_profile": ["field", "value"],
        "device_notify": ["text"],
        "device_open_url": ["url"],
    }
    if name in required:
        result["required"] = required[name]
    if name == "set_reminder":
        result["anyOf"] = [
            {"required": ["text", "delay_seconds"]},
            {"required": ["text", "fire_at"]},
            {"required": ["raw_text"]},
        ]
    elif name == "timer_countdown":
        result["anyOf"] = [{"required": ["duration_seconds"]}, {"required": ["raw_text"]}]
    elif name == "cancel_reminder":
        result["anyOf"] = [{"required": ["id"]}, {"required": ["raw_text"]}]
    return result


def canonical_schema(name: str, schema: dict) -> dict:
    """Accept real schemas and the original decorator's flat type-description map."""
    if schema.get("type") == "object" or "properties" in schema:
        result = deepcopy(schema)
        result.setdefault("type", "object")
        _remove_host_fields(result)
        result.setdefault("additionalProperties", False)
    elif (builtin := builtin_schema(name)) is not None:
        result = builtin
    else:
        properties, required = {}, []
        for field, description in schema.items():
            if field in _IDENTITY:
                continue
            if isinstance(description, dict):
                properties[field] = deepcopy(description)
                continue
            description = str(description)
            kind = description.split()[0].lower()
            kind = {"int": "integer", "float": "number", "bool": "boolean", "str": "string"}.get(kind, kind)
            if kind not in {"integer", "number", "boolean", "string", "object", "array"}:
                kind = "string"
            properties[field] = {"type": kind, "description": description}
            if "required" in description.lower():
                required.append(field)
        result = {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
    Draft202012Validator.check_schema(result)
    return result


def _remove_host_fields(schema: dict) -> None:
    """Strip identity constraints at the input object level, including compositions."""
    properties = schema.get("properties", {})
    for field in _IDENTITY:
        properties.pop(field, None)
    if "required" in schema:
        schema["required"] = [field for field in schema["required"] if field not in _IDENTITY]
    for keyword in ("allOf", "anyOf", "oneOf"):
        for child in schema.get(keyword, []):
            _remove_host_fields(child)


def tool_annotations(name: str, *, read_only: bool | None = None) -> dict:
    read_only = name in _READ_ONLY if read_only is None else read_only
    return {
        "readOnlyHint": read_only,
        "destructiveHint": name in {"cancel_reminder", "update_user_profile"}
        or name
        not in {
            "get_time",
            "get_weather",
            "query_memory",
            "list_reminders",
            "list_devices",
            "web_search",
            "device_ping",
            "device_notify",
            "device_open_url",
            "set_reminder",
            "timer_countdown",
        },
        "idempotentHint": read_only,
        "openWorldHint": name in {"get_weather", "web_search", "device_open_url"},
    }
