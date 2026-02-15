"""
Shared async HTTP client for calling internal services.
Singleton httpx.AsyncClient with connection pooling.
"""
import httpx
from typing import Optional, Any

_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=True,
        )
    return _client


async def close_http_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def service_get(base_url: str, path: str, params: dict = None) -> Any:
    client = await get_http_client()
    url = f"{base_url}{path}"
    resp = await client.get(url, params={k: v for k, v in (params or {}).items() if v is not None})
    resp.raise_for_status()
    return resp.json()


async def service_post(base_url: str, path: str, json_data: dict = None) -> Any:
    client = await get_http_client()
    url = f"{base_url}{path}"
    resp = await client.post(url, json=json_data or {})
    resp.raise_for_status()
    return resp.json()
