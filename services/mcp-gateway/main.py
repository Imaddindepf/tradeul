"""
Tradeul MCP Gateway
Composite MCP server that exposes all 27 microservices as standardized tools.

Architecture:
- 12 domain-specific MCP servers composed into a single gateway
- ~50 tools covering scanner, events, news, earnings, SEC, financials,
  dilution, screener, historical, analytics, patterns, and prediction markets
- Shared Redis + HTTP clients for efficient resource usage
- Streamable HTTP transport for network access from LangGraph agents

Usage:
  python main.py                          # Start HTTP server on port 8050
  fastmcp dev main.py                     # Interactive development mode
  fastmcp install main.py --name tradeul  # Install as MCP server
"""
import asyncio
import signal
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastmcp import FastMCP
from config import config

# ──────────────────────────────────────────────────────────────────────
# Root MCP Server
# ──────────────────────────────────────────────────────────────────────
gateway = FastMCP(
    "Tradeul Gateway",
    instructions=(
        "Tradeul is a real-time stock trading platform processing 11,000+ tickers. "
        "This gateway provides access to all platform services through standardized tools.\n\n"
        "AVAILABLE DOMAINS:\n"
        "- Scanner: Real-time rankings (gappers, momentum, volume, halts)\n"
        "- Events: 27+ market event types (breakouts, VWAP crosses, volume spikes)\n"
        "- News: Benzinga real-time news and catalyst alerts\n"
        "- Earnings: Calendar with EPS/revenue estimates and actuals\n"
        "- SEC Filings: Real-time EDGAR filings (8-K, 10-K, S-1, etc.)\n"
        "- Financials: Financial statements, ratios, key stats, adjusted metrics, segments\n"
        "- Dilution: Warrant tracking, ATM offerings, cash runway, risk scores\n"
        "- Screener: DuckDB-powered screening with 60+ indicators\n"
        "- Historical: 1760+ days of OHLCV data (minute + daily)\n"
        "- Analytics: RVOL, VWAP, technical indicators, volume/price windows\n"
        "- Patterns: FAISS similarity search for chart patterns\n"
        "- Predictions: Polymarket prediction markets\n\n"
        "TIPS:\n"
        "- For real-time data, use Scanner or Analytics tools\n"
        "- For historical analysis, use Historical tools with DuckDB\n"
        "- For fundamental analysis, combine Financials + Dilution + SEC tools\n"
        "- For news-driven analysis, combine News + Events + Earnings tools"
    ),
)

# ──────────────────────────────────────────────────────────────────────
# Import and mount all domain servers
# ──────────────────────────────────────────────────────────────────────
from servers.scanner import mcp as scanner_mcp
from servers.events import mcp as events_mcp
from servers.news import mcp as news_mcp
from servers.earnings import mcp as earnings_mcp
from servers.sec_filings import mcp as sec_mcp
from servers.financials import mcp as financials_mcp
from servers.dilution import mcp as dilution_mcp
from servers.screener import mcp as screener_mcp
from servers.historical import mcp as historical_mcp
from servers.analytics import mcp as analytics_mcp
from servers.patterns import mcp as patterns_mcp
from servers.predictions import mcp as predictions_mcp
from servers.market_pulse import mcp as market_pulse_mcp
from servers.strategy_scan import mcp as strategy_scan_mcp

# Mount each domain server with a prefix for namespacing
# FastMCP mount signature: mount(server, prefix=)
gateway.mount(scanner_mcp, prefix="scanner")
gateway.mount(events_mcp, prefix="events")
gateway.mount(news_mcp, prefix="news")
gateway.mount(earnings_mcp, prefix="earnings")
gateway.mount(sec_mcp, prefix="sec")
gateway.mount(financials_mcp, prefix="financials")
gateway.mount(dilution_mcp, prefix="dilution")
gateway.mount(screener_mcp, prefix="screener")
gateway.mount(historical_mcp, prefix="historical")
gateway.mount(analytics_mcp, prefix="analytics")
gateway.mount(patterns_mcp, prefix="patterns")
gateway.mount(predictions_mcp, prefix="predictions")
gateway.mount(market_pulse_mcp, prefix="market_pulse")
gateway.mount(strategy_scan_mcp, prefix="strategy")


# ──────────────────────────────────────────────────────────────────────
# Gateway-level tools (cross-domain)
# ──────────────────────────────────────────────────────────────────────
@gateway.tool()
async def get_platform_status() -> dict:
    """Get the overall platform status including market session,
    number of active tickers, and service health."""
    from clients.redis_client import redis_get_json, get_redis

    session = await redis_get_json("market:session:status")

    r = await get_redis()
    enriched_count = await r.hlen("snapshot:enriched:latest")

    return {
        "market_session": session or {"session": "UNKNOWN"},
        "active_tickers": enriched_count,
        "mcp_version": "1.0.0",
        "domains": [
            "scanner", "events", "news", "earnings", "sec_filings",
            "financials", "dilution", "screener", "historical",
            "analytics", "patterns", "predictions",
        ],
    }


@gateway.tool()
async def get_full_ticker_analysis(symbol: str) -> dict:
    """Get a comprehensive analysis of a single ticker combining data from
    multiple domains: enriched snapshot, recent events, news, and earnings.

    This is a convenience tool that aggregates data from 4 sources in parallel.
    For deeper analysis of any single domain, use the domain-specific tools.
    """
    import asyncio
    from clients.redis_client import get_redis
    from clients.http_client import service_get
    import orjson

    r = await get_redis()
    sym = symbol.upper()

    # Parallel data fetching
    enriched_task = r.hget("snapshot:enriched:latest", sym)
    news_task = r.zrevrange(f"cache:benzinga:news:ticker:{sym}", 0, 4)

    enriched_raw, news_raw = await asyncio.gather(
        enriched_task, news_task, return_exceptions=True
    )

    result = {"symbol": sym}

    # Enriched data
    if isinstance(enriched_raw, str):
        result["market_data"] = orjson.loads(enriched_raw)
    else:
        result["market_data"] = None

    # News
    if isinstance(news_raw, list):
        articles = []
        for item in news_raw:
            try:
                articles.append(orjson.loads(item))
            except Exception:
                pass
        result["recent_news"] = articles
    else:
        result["recent_news"] = []

    # Events (from stream)
    from clients.redis_client import redis_xrevrange
    events = await redis_xrevrange("stream:alerts:market", count=200)
    ticker_events = [e for e in events if e.get("symbol") == sym][:10]
    result["recent_events"] = ticker_events

    return result


# ──────────────────────────────────────────────────────────────────────
# Lifecycle management
# ──────────────────────────────────────────────────────────────────────
async def cleanup():
    """Cleanup connections on shutdown."""
    from clients.redis_client import close_redis
    from clients.http_client import close_http_client
    from clients.db_client import close_db_pool
    await close_redis()
    await close_http_client()
    await close_db_pool()


# ──────────────────────────────────────────────────────────────────────
# REST API for direct tool invocation (used by AI Agent V4)
# Wraps FastMCP tools in a simple JSON POST endpoint.
# ──────────────────────────────────────────────────────────────────────
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import orjson
import traceback
import hmac
import logging as _logging

_gwlog = _logging.getLogger("mcp_gateway.rest")

rest_app = FastAPI(title="Tradeul MCP Gateway REST API")


async def _catalog_warm_loop() -> None:
    """Pre-calienta el catálogo de eventos en background.

    La agregación sobre market_events (~12M filas/día) tarda ~140s: si un
    usuario la dispara en frío, revienta todos los timeouts de la cadena
    (incidente 2026-07-27). Calentándola aquí cada 50 min, las llamadas de
    agentes/usuarios siempre golpean el caché de strategy_scan.

    Lo arranca el lifespan combinado de build_app(). NOTA: antes vivía en un
    @rest_app.on_event("startup"), que NUNCA se ejecutaba — Starlette no
    propaga lifespan a las apps montadas con Mount().

    force_refresh=True es imprescindible: con un caché read-through, el warm
    a los 3000s encontraba el caché aún vigente (TTL 3600s) y no re-consultaba,
    dejando ~42 min de ventana fría cada ~102 min (revisión 2026-07-28).
    _event_catalog devuelve {"error": ...} en vez de lanzar: hay que detectarlo
    o el fallo se loguea como éxito; tras fallo, backoff corto de 120s.
    """
    # Helper plano, no la tool decorada (FunctionTool no es invocable).
    from servers.strategy_scan import _event_catalog

    log = _logging.getLogger("catalog_warm")
    first = True
    while True:
        ok_all = True
        for d in (["today", "yesterday"] if first else ["today"]):
            try:
                result = await _event_catalog(date=d, min_count=50, force_refresh=True)
                if isinstance(result, dict) and result.get("error"):
                    ok_all = False
                    log.warning("catalog warm FAILED for %s: %s", d, result["error"])
                else:
                    log.warning("event catalog warmed for %s (%s event types)",
                                d, result.get("count"))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                log.warning("catalog warm failed for %s: %s", d, exc)
        first = False
        await asyncio.sleep(3000 if ok_all else 120)


def _warm_task_done(task: "asyncio.Task") -> None:
    """El warm loop es un while True: si el task termina sin cancelación es un
    bug — dejarlo morir en silencio ocultaría la vuelta de las ventanas frías."""
    if task.cancelled():
        return
    exc = task.exception()
    _logging.getLogger("catalog_warm").error(
        "catalog warm task murió inesperadamente: %r", exc)

# Internal service token. The gateway sits on the private bridge network and
# proxies data services (incl. a TimescaleDB tool that aggregates ~12M rows),
# so callers must present a shared secret. Safe rollout: if MCP_GATEWAY_TOKEN
# is unset the check is disabled and behaviour is unchanged — set the env var
# on the gateway AND on ai-agent-v4 to turn enforcement on.
_GATEWAY_TOKEN = os.getenv("MCP_GATEWAY_TOKEN", "").strip()


def _require_token(request: Request) -> None:
    if not _GATEWAY_TOKEN:
        return
    provided = request.headers.get("x-mcp-token", "")
    try:
        # compare_digest lanza TypeError con str no-ASCII: debe ser 401, no 500
        authorized = bool(provided) and hmac.compare_digest(provided, _GATEWAY_TOKEN)
    except TypeError:
        authorized = False
    if not authorized:
        raise HTTPException(status_code=401, detail="unauthorized")


@rest_app.get("/health")
async def health():
    return {"status": "healthy", "service": "mcp-gateway"}


@rest_app.get("/api/tools")
async def list_tools(request: Request):
    """List all available MCP tools (public FastMCP API, works on v3.x)."""
    _require_token(request)
    tools = []
    try:
        if hasattr(gateway, "get_tools"):
            # fastmcp >= 2.14: get_tools() → dict[str, Tool]. La CLAVE lleva
            # el prefijo del mount (earnings_get_earnings_results); tool.name
            # es el nombre local sin prefijo — usar siempre la clave.
            tool_map = await gateway.get_tools()
            items = (tool_map.items() if isinstance(tool_map, dict)
                     else ((t.name, t) for t in tool_map))
        else:
            items = ((t.name, t) for t in await gateway.list_tools())
        for name, tool in items:
            tools.append({
                "name": name,
                "description": getattr(tool, "description", "") or "",
                # JSON schema de los argumentos — lo consumen los smoke tests
                # (scripts/smoke_tools.py, evals/run_tool_execution.py) para
                # sintetizar llamadas mínimas válidas.
                "input_schema": getattr(tool, "parameters", None),
            })
    except Exception:
        _logging.getLogger("api_tools").exception("tool listing failed")
    return {"tools": tools, "total": len(tools)}


@rest_app.post("/api/tool/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    """Invoke an MCP tool directly via REST POST.

    Body: JSON object with tool arguments.
    Returns: {"result": ...} or {"error": "..."}
    """
    _require_token(request)
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        tool = await gateway.get_tool(tool_name)
        result = await tool.run(body)

        # Parse ToolResult into JSON-serializable output
        # ToolResult has .content which is a list of content parts
        if hasattr(result, 'content') and isinstance(result.content, list):
            parts = []
            for item in result.content:
                if hasattr(item, 'text'):
                    try:
                        parts.append(orjson.loads(item.text))
                    except Exception:
                        parts.append(item.text)
                elif hasattr(item, 'data'):
                    parts.append(item.data)
                else:
                    parts.append(str(item))
            return JSONResponse(content={"result": parts[0] if len(parts) == 1 else parts})
        elif isinstance(result, str):
            try:
                return JSONResponse(content={"result": orjson.loads(result)})
            except Exception:
                return JSONResponse(content={"result": result})
        else:
            return JSONResponse(content={"result": str(result)})
    except HTTPException:
        raise
    except Exception as e:
        # Log the full traceback server-side; never leak internal structure
        # (paths, stack) to callers.
        _gwlog.warning("tool %s failed: %s", tool_name, traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": f"tool execution failed: {type(e).__name__}"}
        )


# ──────────────────────────────────────────────────────────────────────
# App composition - Mount both MCP + REST on the same Uvicorn server
# ──────────────────────────────────────────────────────────────────────
class _McpTokenGate:
    """ASGI middleware: exige X-MCP-Token en el mount /mcp.

    El REST valida el token vía _require_token(); las apps montadas con
    Mount() no pasan por las dependencias de FastAPI, así que el transporte
    MCP necesita su propio gate. Misma semántica de rollout que el REST:
    sin MCP_GATEWAY_TOKEN configurado, el check queda desactivado.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # http y websocket: si fastmcp añadiera rutas ws en el futuro, no
        # deben colarse sin token (hallazgo revisión 2026-07-28)
        if scope["type"] in ("http", "websocket") and _GATEWAY_TOKEN:
            provided = ""
            for key, value in scope.get("headers") or []:
                if key == b"x-mcp-token":
                    provided = value.decode("latin-1")
                    break
            try:
                # compare_digest lanza TypeError con no-ASCII → 401, no 500
                authorized = bool(provided) and hmac.compare_digest(provided, _GATEWAY_TOKEN)
            except TypeError:
                authorized = False
            if not authorized:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                from starlette.responses import JSONResponse as _JR
                await _JR({"detail": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def build_app():
    """Compone la app ASGI final: MCP (streamable HTTP) en /mcp, REST en /.

    El lifespan del Starlette exterior es imprescindible: Starlette NO propaga
    lifespan a las apps montadas, así que sin esto (a) el session manager de
    FastMCP nunca se inicializa (/mcp devolvía 500 en initialize) y (b) los
    startup hooks del REST nunca corrían (el warmer del catálogo estuvo muerto
    por esa razón). Aquí corremos el lifespan de FastMCP, arrancamos el warmer
    y cerramos las conexiones compartidas en el shutdown.
    """
    from contextlib import asynccontextmanager, suppress
    from starlette.applications import Starlette
    from starlette.responses import RedirectResponse
    from starlette.routing import Mount, Route

    # path="/" dentro de la app MCP + Mount("/mcp") ⇒ endpoint limpio en /mcp
    # (con el antiguo path="/mcp" quedaba duplicado en /mcp/mcp).
    mcp_app = gateway.http_app(path="/")

    @asynccontextmanager
    async def _lifespan(app):
        try:
            async with mcp_app.lifespan(app):
                warm_task = asyncio.create_task(_catalog_warm_loop())
                warm_task.add_done_callback(_warm_task_done)
                try:
                    yield
                finally:
                    warm_task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await warm_task
        finally:
            # Tras salir del lifespan MCP: el session manager ya está cerrado
            # y no quedan requests en vuelo usando los clientes compartidos.
            await cleanup()

    async def _mcp_slash_redirect(request):
        # La URL exacta /mcp (sin barra) no la captura el Mount y caería al
        # 404 del REST; 307 preserva método y body. URL canónica: /mcp/
        url = "/mcp/"
        if request.url.query:
            url += "?" + request.url.query
        return RedirectResponse(url=url, status_code=307)

    return Starlette(
        routes=[
            Route("/mcp", _mcp_slash_redirect, methods=["GET", "POST", "DELETE"]),
            Mount("/mcp", app=_McpTokenGate(mcp_app)),
            Mount("/", app=rest_app),
        ],
        lifespan=_lifespan,
    )


# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    print(f"Starting Tradeul MCP Gateway on {config.mcp_host}:{config.mcp_port}")
    print(f"Redis: {config.redis_host}:{config.redis_port}")
    print(f"Domains: 12 | Tools: ~50")

    uvicorn.run(
        build_app(),
        host=config.mcp_host,
        port=config.mcp_port,
    )
