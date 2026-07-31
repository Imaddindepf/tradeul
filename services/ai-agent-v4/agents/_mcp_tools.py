"""
MCP Tool Bridge - Connects LangGraph agents to the MCP Gateway.

Uses the REST API wrapper (/api/tool/{name}) on the MCP Gateway
for simple JSON request/response without SSE parsing.
"""
import httpx
import os
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp_gateway:8050")
# Shared secret for the gateway. Safe rollout: only sent when set; the gateway
# only enforces when it too has the token — so an empty value keeps today's
# behaviour and both sides can be flipped on together.
MCP_GATEWAY_TOKEN = os.getenv("MCP_GATEWAY_TOKEN", "").strip()
_client: httpx.AsyncClient | None = None


class MCPToolError(Exception):
    """Raised when an MCP tool call returns an error."""
    pass


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        headers = {"X-MCP-Token": MCP_GATEWAY_TOKEN} if MCP_GATEWAY_TOKEN else None
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            base_url=MCP_GATEWAY_URL,
            headers=headers,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


async def close_client() -> None:
    """Close the shared httpx client (called during app shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


def _record_tool_call(
    server: str, tool_name: str, ok: bool, error: str, started: float,
) -> None:
    """Persist per-tool success/failure counters (agent_tool_calls table).

    Deferred import and never fatal: telemetry going down must not take the
    tool call with it.
    """
    try:
        from telemetry import get_telemetry
        get_telemetry().record_tool(
            server=server, tool=tool_name, ok=ok, error=error,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:  # noqa: BLE001
        pass


async def call_mcp_tool(
    server: str,
    tool_name: str,
    arguments: dict | None = None,
    *,
    retries: int = 1,
    timeout: float | None = None,
    **kwargs,
) -> Any:
    """Call an MCP tool via the gateway's REST API.

    The tool name is composed as {server}_{tool_name} matching FastMCP's
    prefix-based mounting convention.

    Raises MCPToolError on tool-level errors so callers get proper exceptions.

    Can be called as:
        call_mcp_tool("scanner", "get_scanner_snapshot", {"category": "gappers"})
        call_mcp_tool("scanner", "get_scanner_snapshot", category="gappers")
    """
    client = await _get_client()
    full_tool_name = f"{server}_{tool_name}"
    # Merge dict argument with kwargs
    merged = {}
    if arguments and isinstance(arguments, dict):
        merged.update(arguments)
    merged.update(kwargs)
    arguments = {k: v for k, v in merged.items() if v is not None}

    started = time.monotonic()
    last_error: Exception | None = None
    for attempt in range(1 + retries):
        try:
            resp = await client.post(
                f"/api/tool/{full_tool_name}",
                json=arguments,
                # Per-call override for slow tools (e.g. full-universe strategy
                # scans); falls back to the client default (30s).
                timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )

            if resp.status_code == 404:
                raise MCPToolError(f"Tool not found: {full_tool_name}")
            if resp.status_code == 401:
                raise MCPToolError(f"MCP gateway rejected token for {full_tool_name}")

            data = resp.json()

            if "error" in data:
                raise MCPToolError(f"MCP tool {full_tool_name}: {data['error']}")

            result = data.get("result", data)

            # Backend services frequently signal failure with an in-band
            # `error` field inside a HTTP-200 body (e.g. {"tickers": [],
            # "error": "..."}). Surface it as a real error instead of letting
            # the agent treat degraded/empty data as success.
            if isinstance(result, dict) and result.get("error"):
                raise MCPToolError(
                    f"MCP tool {full_tool_name} returned error: {result['error']}"
                )

            _record_tool_call(server, tool_name, True, "", started)
            return result

        except MCPToolError as e:
            # Tool-level failures (404 / 401 / in-band `error`) used to
            # propagate silently: httpx logs the HTTP exchange at INFO and the
            # agents swallow the exception into their in-memory `_errors`
            # array, so a broken tool left no durable trace anywhere.
            logger.warning("MCP tool %s error: %s", full_tool_name, e)
            _record_tool_call(server, tool_name, False, str(e), started)
            raise
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(
                "MCP tool %s timeout (attempt %d/%d)",
                full_tool_name, attempt + 1, 1 + retries,
            )
        except Exception as e:
            last_error = e
            logger.warning(
                "MCP tool %s failed (attempt %d/%d): %s",
                full_tool_name, attempt + 1, 1 + retries, e,
            )

    logger.warning(
        "MCP tool %s failed after %d attempts: %s",
        full_tool_name, 1 + retries, last_error,
    )
    _record_tool_call(server, tool_name, False, str(last_error), started)
    raise MCPToolError(f"MCP tool {full_tool_name} failed after {1 + retries} attempts: {last_error}")
