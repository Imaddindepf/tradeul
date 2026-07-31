"""
Argument guard for MCP tool calls.

The LLM picks WHICH tool to call; the arguments are built by deterministic
code. That split is deliberate — a model asked to fill arguments tends to
borrow fields from a neighbouring tool's schema or emit placeholders. But it
only holds up if the deterministic side is checked, because a wrong or
invented key is accepted by the gateway and comes back as an empty result
that reads exactly like "there is no data".

So every call passes through here on its way out:

  * keys the tool does not declare are dropped, not sent
  * values whose type contradicts the schema are dropped (after the obvious
    coercions: "40" -> 40, "true" -> True)
  * placeholder-looking values ("<date>", "YYYY-MM-DD", "TICKER", "") are
    dropped — they are never a real argument
  * nothing is ever invented to fill a gap

Every drop is recorded so the caller can say what it could not ask for,
instead of returning a confident answer built on a silently truncated query.

Fail-open by design: if the gateway schema cannot be read, arguments pass
through untouched. A validator that cannot validate must not block trading
data.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Warnings collected during the current node run. A ContextVar keeps
# concurrent agent nodes from writing into each other's list.
_warnings: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "mcp_arg_warnings", default=None
)

_schemas: dict[str, dict] | None = None
_schema_lock = asyncio.Lock()

# Values that look like a template rather than data. Cheap to test, and they
# are the single most common way a bad argument reaches an upstream service.
_PLACEHOLDER_RE = re.compile(
    r"^\s*(?:<[^>]*>|\{\{.*\}\}|\[[a-z_ ]+\]|"
    r"yyyy-mm-dd|mm/dd/yyyy|ticker|symbol|string|value|none|null|n/?a|\.{3})\s*$",
    re.IGNORECASE,
)


def start_run() -> list[str]:
    """Begin collecting warnings for one node run. Returns the live list."""
    bucket: list[str] = []
    _warnings.set(bucket)
    return bucket


def take_warnings() -> list[str]:
    """Drain what was collected since start_run()."""
    bucket = _warnings.get()
    if not bucket:
        return []
    out = list(dict.fromkeys(bucket))  # dedupe, keep order
    bucket.clear()
    return out


def warn(message: str) -> None:
    """Record something the caller wanted but could not ask for."""
    bucket = _warnings.get()
    if bucket is None:
        logger.debug("arg warning outside a run: %s", message)
        return
    bucket.append(message)


async def _load_schemas() -> dict[str, dict]:
    """Tool name -> input schema, read once from the gateway listing."""
    global _schemas
    if _schemas is not None:
        return _schemas
    async with _schema_lock:
        if _schemas is not None:
            return _schemas
        loaded: dict[str, dict] = {}
        try:
            from agents._mcp_tools import _get_client

            client = await _get_client()
            resp = await client.get("/api/tools", timeout=10.0)
            resp.raise_for_status()
            payload = resp.json()
            tools = payload if isinstance(payload, list) else (payload.get("tools") or [])
            for tool in tools:
                name = tool.get("name")
                schema = tool.get("input_schema") or tool.get("inputSchema")
                if name and isinstance(schema, dict):
                    loaded[name] = schema
            logger.info("Loaded input schemas for %d MCP tools", len(loaded))
        except Exception as exc:  # noqa: BLE001
            # Fail-open: an unreachable listing must not stop tool calls.
            logger.warning("Could not load MCP tool schemas (%s) — args unchecked", exc)
        _schemas = loaded
        return _schemas


def _types_of(spec: Any) -> set[str]:
    """JSON-Schema types a property accepts, flattening anyOf/oneOf."""
    if not isinstance(spec, dict):
        return set()
    types: set[str] = set()
    declared = spec.get("type")
    if isinstance(declared, str):
        types.add(declared)
    elif isinstance(declared, list):
        types.update(t for t in declared if isinstance(t, str))
    for branch in (spec.get("anyOf") or []) + (spec.get("oneOf") or []):
        types |= _types_of(branch)
    return types


def _coerce(value: Any, types: set[str]) -> tuple[Any, bool]:
    """(value, ok). Applies only unambiguous coercions."""
    if not types or "null" in types and value is None:
        return value, True

    def matches(v: Any) -> bool:
        if isinstance(v, bool):
            return "boolean" in types
        if isinstance(v, int):
            return "integer" in types or "number" in types
        if isinstance(v, float):
            return "number" in types
        if isinstance(v, str):
            return "string" in types
        if isinstance(v, list):
            return "array" in types
        if isinstance(v, dict):
            return "object" in types
        return v is None and "null" in types

    if matches(value):
        return value, True

    # "40" -> 40 and 40 -> "40" are the two conversions worth doing; anything
    # cleverer starts guessing at intent.
    if isinstance(value, str):
        text = value.strip()
        if "integer" in types:
            try:
                return int(text), True
            except ValueError:
                pass
        if "number" in types:
            try:
                return float(text), True
            except ValueError:
                pass
        if "boolean" in types and text.lower() in ("true", "false"):
            return text.lower() == "true", True
    elif isinstance(value, (int, float)) and "string" in types and not isinstance(value, bool):
        return str(value), True

    return value, False


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return not value.strip() or bool(_PLACEHOLDER_RE.match(value))


async def clean_args(full_name: str, args: dict | None) -> dict | None:
    """Drop what the tool cannot accept; record every drop.

    `full_name` is the gateway name (server_tool). Unknown tools and
    unreadable schemas pass through untouched.
    """
    if not args or not isinstance(args, dict):
        return args

    schemas = await _load_schemas()
    schema = schemas.get(full_name)
    props = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(props, dict) or not props:
        return args

    cleaned: dict[str, Any] = {}
    for key, value in args.items():
        if key not in props:
            warn(f"{full_name}: dropped unknown argument '{key}'")
            continue
        if _is_placeholder(value):
            warn(f"{full_name}: dropped placeholder value for '{key}' ({value!r})")
            continue
        coerced, ok = _coerce(value, _types_of(props[key]))
        if not ok:
            warn(
                f"{full_name}: dropped '{key}' — {type(value).__name__} does not fit "
                f"{sorted(_types_of(props[key])) or 'schema'}"
            )
            continue
        cleaned[key] = coerced
    return cleaned
