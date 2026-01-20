from __future__ import annotations

from typing import Any, Dict, List


def infer_schema(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {key: infer_schema(item) for key, item in value.items()},
        }
    if isinstance(value, list):
        return {"type": "array", "items": _merge_schemas([infer_schema(item) for item in value])}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) or isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    return {"type": "unknown"}


def _merge_schemas(schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not schemas:
        return {"type": "unknown"}
    if len(schemas) == 1:
        return schemas[0]
    types = sorted({schema.get("type", "unknown") for schema in schemas})
    return {"type": "union", "members": types}
