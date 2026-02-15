"""MCP Tool Bridge - Connects LangGraph agents to the MCP Gateway."""
import httpx
import os
import json
from typing import Any

MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp_gateway:8050")
_client = None

async def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), base_url=MCP_GATEWAY_URL)
    return _client

async def call_mcp_tool(server: str, tool_name: str, **kwargs) -> Any:
    client = await _get_client()
    payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": f"{server}_{tool_name}", "arguments": {k: v for k, v in kwargs.items() if v is not None}}, "id": 1}
    try:
        resp = await client.post("/mcp/v1", json=payload)
        resp.raise_for_status()
        result = resp.json()
        if "result" in result:
            content = result["result"].get("content", [])
            if content and isinstance(content, list):
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                if text_parts:
                    try:
                        return json.loads(text_parts[0])
                    except json.JSONDecodeError:
                        return {"text": text_parts[0]}
            return result["result"]
        elif "error" in result:
            return {"error": result["error"].get("message", "Unknown MCP error")}
        return result
    except Exception as e:
        return {"error": f"MCP error: {str(e)}"}
