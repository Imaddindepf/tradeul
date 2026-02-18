"""
MCP Tool Bridge - Connects LangGraph agents to the MCP Gateway.

Uses the REST API wrapper (/api/tool/{name}) on the MCP Gateway
for simple JSON request/response without SSE parsing.
"""
import httpx
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp_gateway:8050")
_client: httpx.AsyncClient | None = None


class MCPToolError(Exception):
    """Raised when an MCP tool call returns an error."""
    pass


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            base_url=MCP_GATEWAY_URL,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


async def close_client() -> None:
    """Close the shared httpx client (called during app shutdown)."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


async def call_mcp_tool(
    server: str,
    tool_name: str,
    arguments: dict | None = None,
    *,
    retries: int = 1,
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

    last_error: Exception | None = None
    for attempt in range(1 + retries):
        try:
            resp = await client.post(f"/api/tool/{full_tool_name}", json=arguments)

            if resp.status_code == 404:
                raise MCPToolError(f"Tool not found: {full_tool_name}")

            data = resp.json()

            if "error" in data:
                raise MCPToolError(f"MCP tool {full_tool_name}: {data['error']}")

            return data.get("result", data)

        except MCPToolError:
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

    raise MCPToolError(f"MCP tool {full_tool_name} failed after {1 + retries} attempts: {last_error}")
