"""Runtime JSON Schema loader and resolver for dynamic tree & form generation."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ANCHOR_BY_FORMAT: dict[str, str] = {
    "gp3": "bar",
    "gp4": "bar",
    "gp5": "bar",
    "gp": "bar",
    "gpx": "bar",
    "musicxml": "bar",
    "mxl": "bar",
    "mscz": "bar",
    "alphatex": "bar",
    "midi": "tick",
    "abc": "text",
    "pdf": "pdf",
    "txt": "text",
}


def find_schema_dir() -> Path:
    """Locate the repository's `schema/` directory."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "schema"
        if (candidate / "manifest.schema.json").is_file():
            return candidate
    raise FileNotFoundError("Could not locate schema/manifest.schema.json")


class SchemaRegistry:
    """Loads manifest, sync, and beats schemas from disk at runtime."""

    def __init__(self, schema_dir: Path | None = None) -> None:
        self.schema_dir = schema_dir or find_schema_dir()
        self.manifest = self._load("manifest.schema.json")
        self.sync = self._load("sync.schema.json")
        self.beats = self._load("beats.schema.json")

    def _load(self, filename: str) -> dict[str, Any]:
        with open(self.schema_dir / filename, "r", encoding="utf-8") as f:
            return json.load(f)


def resolve_ref(root_schema: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Follow local `#/...` `$ref` pointers."""
    seen: set[str] = set()
    cur = schema
    while isinstance(cur, dict) and "$ref" in cur:
        ref = cur["$ref"]
        if ref in seen or not ref.startswith("#/"):
            break
        seen.add(ref)
        target: Any = root_schema
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            target = target[part]
        merged = dict(target)
        for k, v in cur.items():
            if k != "$ref":
                merged[k] = v
        cur = merged
    return cur


def _matches_condition(root_schema: dict[str, Any], cond_schema: dict[str, Any], data: Any) -> bool:
    """Check whether `data` satisfies an `if` subschema."""
    if not isinstance(data, dict):
        return False
    full_cond = dict(cond_schema)
    if "$defs" in root_schema and "$defs" not in full_cond:
        full_cond["$defs"] = root_schema["$defs"]
    return Draft202012Validator(full_cond).is_valid(data)


def _merge_schema_into(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Merge effective JSON Schema keywords from `src` into `dst`."""
    for key in (
        "type",
        "title",
        "description",
        "const",
        "enum",
        "default",
        "format",
        "pattern",
        "minimum",
        "maximum",
        "minLength",
        "minItems",
        "uniqueItems",
        "items",
        "additionalProperties",
        "propertyNames",
    ):
        if key in src and key not in dst:
            dst[key] = copy.deepcopy(src[key])

    if "properties" in src:
        dst_props = dst.setdefault("properties", {})
        for k, v in src["properties"].items():
            if k in dst_props and isinstance(dst_props[k], dict) and isinstance(v, dict):
                merged_prop = copy.deepcopy(dst_props[k])
                _merge_schema_into(merged_prop, v)
                dst_props[k] = merged_prop
            else:
                dst_props[k] = copy.deepcopy(v)

    if "required" in src:
        req = dst.setdefault("required", [])
        for r in src["required"]:
            if r not in req:
                req.append(r)


def resolve_schema(
    root_schema: dict[str, Any],
    sub_schema: dict[str, Any] | bool,
    data: Any = None,
) -> dict[str, Any]:
    """Flatten `$ref`, `allOf`, conditional `if`/`then`/`else`, and `oneOf` hints for `data`."""
    if not isinstance(sub_schema, dict):
        return {}
    base = resolve_ref(root_schema, sub_schema)
    out: dict[str, Any] = {}
    _merge_schema_into(out, {k: v for k, v in base.items() if k not in ("allOf", "if", "then", "else", "oneOf")})

    if "if" in base and data is not None:
        branch = base.get("then") if _matches_condition(root_schema, base["if"], data) else base.get("else")
        if isinstance(branch, dict):
            resolved_branch = resolve_schema(root_schema, branch, data)
            _merge_schema_into(out, resolved_branch)

    for sub in base.get("allOf", []):
        resolved_sub = resolve_schema(root_schema, sub, data)
        _merge_schema_into(out, resolved_sub)

    # For oneOf (e.g., score path/externalPath or scoreTracks omits/only), collect all candidate properties
    # so the form can display and switch between them.
    if "oneOf" in base:
        for alt in base["oneOf"]:
            if isinstance(alt, dict):
                resolved_alt = resolve_schema(root_schema, alt, data)
                if "properties" in resolved_alt:
                    _merge_schema_into(out, {"properties": resolved_alt["properties"]})

    return out


def item_label(item: Any, index: int) -> str:
    """Derive a readable tree label for an array element."""
    if isinstance(item, dict):
        for key in ("id", "label", "name", "title", "type"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                if key == "id" and isinstance(item.get("label"), str) and item["label"].strip():
                    return f"{val} ({item['label']})"
                if key == "id" and isinstance(item.get("role"), str) and item["role"].strip():
                    return f"{val} [{item['role']}]"
                if key == "id" and isinstance(item.get("format"), str) and item["format"].strip():
                    return f"{val} ({item['format']})"
                return val
        if "bar" in item:
            return f"bar {item['bar']} @ {item.get('timeMs', '?')} ms"
        if "tick" in item:
            return f"tick {item['tick']} @ {item.get('timeMs', '?')} ms"
        if "page" in item:
            return f"page {item['page']} @ {item.get('timeMs', '?')} ms"
        if "line" in item:
            return f"line {item['line']} @ {item.get('timeMs', '?')} ms"
        if "timeMs" in item:
            return f"{item['timeMs']} ms"
    return f"[{index}]"


def default_value_for_schema(root_schema: dict[str, Any], sub_schema: dict[str, Any]) -> Any:
    """Build a minimal valid starter value for a schema node."""
    eff = resolve_schema(root_schema, sub_schema)
    if "const" in eff:
        return copy.deepcopy(eff["const"])
    if "default" in eff:
        return copy.deepcopy(eff["default"])
    if "enum" in eff and eff["enum"]:
        return copy.deepcopy(eff["enum"][0])

    typ = eff.get("type")
    if typ == "object" or "properties" in eff:
        obj: dict[str, Any] = {}
        props = eff.get("properties", {})
        for req in eff.get("required", []):
            if req in props:
                obj[req] = default_value_for_schema(root_schema, props[req])
            else:
                obj[req] = ""
        return obj
    if typ == "array":
        return []
    if typ == "boolean":
        return False
    if typ == "integer":
        return int(eff.get("minimum", 0))
    if typ == "number":
        return float(eff.get("minimum", 0))
    return ""
