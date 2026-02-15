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


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            base_url=MCP_GATEWAY_URL,
        )
    return _client


async def call_mcp_tool(server: str, tool_name: str, arguments: dict | None = None, **kwargs) -> Any:
    """Call an MCP tool via the gateway's REST API.

    The tool name is composed as {server}_{tool_name} matching FastMCP's
    prefix-based mounting convention.

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

    try:
        resp = await client.post(f"/api/tool/{full_tool_name}", json=arguments)

        if resp.status_code == 404:
            return {"error": f"Tool not found: {full_tool_name}"}

        data = resp.json()

        if "error" in data:
            logger.warning("MCP tool %s error: %s", full_tool_name, data["error"])
            return {"error": data["error"]}

        return data.get("result", data)

    except httpx.TimeoutException:
        logger.error("MCP tool %s timeout", full_tool_name)
        return {"error": f"Timeout calling {full_tool_name}"}
    except Exception as e:
        logger.error("MCP tool %s failed: %s", full_tool_name, e)
        return {"error": f"MCP error: {str(e)}"}
