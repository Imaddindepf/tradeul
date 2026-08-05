"""
API Gateway - Main Entry Point

Gateway principal para el frontend web:
- REST API para consultas
- WebSocket para datos en tiempo real
- Agregación de múltiples servicios
"""

import asyncio
import json as _json
import os
import uuid
from datetime import datetime
from typing import Optional, List
from zoneinfo import ZoneInfo

# Todas las fechas "de trading" (rangos hacia Polygon, día actual) deben
# calcularse en hora del exchange. Con datetime.now() naive (UTC en el
# contenedor), entre las 20:00 y 23:59 ET el "hoy" apuntaba al día siguiente.
ET_TZ = ZoneInfo("America/New_York")
import structlog
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse, Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from shared.config.settings import settings
from shared.config.fmp_endpoints import FMPEndpoints
from shared.config.index_symbols import normalize_index_symbol, to_fmp as index_to_fmp
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import configure_logging, get_logger
from shared.models.description import (
    TickerDescription, CompanyInfo, MarketStats, ValuationMetrics,
    DividendInfo, RiskMetrics, AnalystRating, PriceTarget, FMPRatios
)
from shared.models.polygon import PolygonSingleTickerSnapshotResponse
from ws_manager import ConnectionManager
from routes.user_prefs import router as user_prefs_router, set_timescale_client
from routes.tv_designs import router as tv_designs_router, drawings_router as tv_drawings_router, set_timescale_client as set_tv_designs_timescale_client
from routes.user_filters import router as user_filters_router, set_timescale_client as set_user_filters_timescale_client, set_redis_client as set_user_filters_redis
from routes.screener_templates import router as screener_templates_router, set_timescale_client as set_screener_templates_timescale_client
from routes.financials import router as financials_router
from routes.proxy import router as proxy_router
from routes.realtime import router as realtime_router, set_redis_client as set_realtime_redis
from routes.ratio_analysis import router as ratio_analysis_router
from routes.morning_news import router as morning_news_router, set_redis_client as set_morning_news_redis
from routes.insights import router as insights_router, set_redis_client as set_insights_redis
from routes.symbols import router as symbols_router, set_timescale_client as set_symbols_timescale_client
from routes.heatmap import router as heatmap_router, set_redis_client as set_heatmap_redis
from routes.scanner import router as scanner_router, set_redis_client as set_scanner_redis
from routes.institutional import router as institutional_router, set_sec_api_client as set_institutional_sec_client, warmup_sec_api_connection
from routes.earnings import router as earnings_router
from routes.halts import router as halts_router
from routes.l2replay import router as l2replay_router
from routes.alerts import router as alerts_router
from routes.alert_strategies import router as alert_strategies_router, set_timescale_client as set_alert_strategies_timescale_client
from routes.performance import router as performance_router, set_redis_client as set_performance_redis, set_timescale_client as set_performance_timescale
from routes.rrg import router as rrg_router, set_redis_client as set_rrg_redis, set_timescale_client as set_rrg_timescale
from routes.analyst_ratings import router as analyst_ratings_router
from routes.perplexity_financials import router as perplexity_financials_router
from routes.developer import router as developer_router, set_redis_client as set_developer_redis
from routes.bug_reports import router as bug_reports_router, set_redis_client as set_bug_reports_redis
from routes.imap import router as imap_router
from routes.tape import router as tape_router
from routers.watchlist_router import router as watchlist_router
from routers.notes_router import router as notes_router
from http_clients import http_clients, HTTPClientManager
from auth import clerk_jwt_verifier, PassiveAuthMiddleware, get_current_user, AuthenticatedUser
from ticker_chain import get_ticker_chain, fetch_chained_polygon_data, MANUAL_CHAIN_OVERRIDES

# Configurar logger
configure_logging(service_name="api_gateway")
logger = get_logger(__name__)

# ============================================================================
# Global State
# ============================================================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
connection_manager: ConnectionManager = ConnectionManager()
stream_broadcaster_task: Optional[asyncio.Task] = None

# HTTP Clients Manager (connection pooling)
# Acceso via: http_clients.polygon, http_clients.fmp, etc.


# ============================================================================
# Lifecycle Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    global redis_client, timescale_client, stream_broadcaster_task
    
    logger.info("api_gateway_starting")
    
    # Inicializar Redis
    redis_client = RedisClient()
    await redis_client.connect()
    
    # Inicializar TimescaleDB (requerido para preferencias de usuario y filtros)
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    set_timescale_client(timescale_client)  # Para user_prefs
    set_tv_designs_timescale_client(timescale_client)  # Para tv_designs (diseños chart TVC)
    set_user_filters_timescale_client(timescale_client)  # Para user_filters
    set_user_filters_redis(redis_client)  # Para notificar al scanner cuando cambian filtros
    set_screener_templates_timescale_client(timescale_client)  # Para screener_templates
    set_symbols_timescale_client(timescale_client)  # Para symbols (indexed query ~150ms)
    set_alert_strategies_timescale_client(timescale_client)  # Para alert strategies
    set_performance_timescale(timescale_client)  # Para performance aggregation
    set_rrg_timescale(timescale_client)  # Para RRG trails
    logger.info("timescale_connected")
    
    # Router de financials ahora es un microservicio separado
    # Se accede via http_clients.financials (FinancialsClient)
    logger.info("financials_microservice_ready")
    
    # Configurar router de realtime con Redis
    set_realtime_redis(redis_client)
    logger.info("realtime_router_configured")
    
    # Configurar router de morning news con Redis
    set_morning_news_redis(redis_client)
    logger.info("morning_news_router_configured")
    
    set_insights_redis(redis_client)
    logger.info("insights_router_configured")
    
    # Configurar router de heatmap con Redis
    set_heatmap_redis(redis_client)
    logger.info("heatmap_router_configured")
    
    # Configurar router de scanner con Redis
    set_scanner_redis(redis_client)
    logger.info("scanner_router_configured")
    
    # Configurar router de performance con Redis
    set_performance_redis(redis_client)
    set_rrg_redis(redis_client)
    logger.info("performance_router_configured")

    # Configurar router de developer API (trader keys)
    set_developer_redis(redis_client)
    set_bug_reports_redis(redis_client)
    logger.info("developer_router_configured")

    # Configurar router de institutional con SEC API client
    # Nota: se configura después de http_clients.initialize()
    
    # Inicializar HTTP Clients con connection pooling
    # Esto evita crear conexiones por request - CRÍTICO para latencia
    await http_clients.initialize(
        polygon_api_key=settings.POLYGON_API_KEY,
        fmp_api_key=settings.FMP_API_KEY,
        sec_api_key=getattr(settings, 'SEC_API_IO_KEY', None),
        elevenlabs_api_key=os.getenv("ELEVEN_LABS_API_KEY"),
    )
    logger.info("http_clients_initialized_with_pooling")
    
    # Configurar router de institutional holdings con SEC API client
    if http_clients.sec_api:
        set_institutional_sec_client(http_clients.sec_api)
        # Warmup connection in background to avoid slow first request
        asyncio.create_task(warmup_sec_api_connection())
        logger.info("institutional_router_configured")
    
    # Inicializar Clerk JWT Verifier (pre-carga JWKS para auth)
    if getattr(settings, 'auth_enabled', False):
        try:
            await clerk_jwt_verifier.initialize()
            logger.info("clerk_jwt_verifier_initialized")
        except Exception as e:
            logger.warning(f"clerk_jwt_init_failed error={e} - auth will be disabled")
    
    # Iniciar broadcaster de streams - DESACTIVADO: Ahora usamos servidor WebSocket dedicado
    # stream_broadcaster_task = asyncio.create_task(broadcast_streams())
    stream_broadcaster_task = None
    logger.info("WebSocket broadcaster disabled - using dedicated websocket_server")
    
    
    logger.info("api_gateway_started")
    
    yield
    
    # Shutdown
    logger.info("api_gateway_shutting_down")
    
    if stream_broadcaster_task:
        stream_broadcaster_task.cancel()
        try:
            await stream_broadcaster_task
        except asyncio.CancelledError:
            pass
    
    # Cerrar HTTP clients (liberar conexiones)
    await http_clients.close()
    
    if redis_client:
        await redis_client.disconnect()
    
    if timescale_client:
        await timescale_client.disconnect()
    
    logger.info("api_gateway_stopped")


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Tradeul Scanner API",
    description="API Gateway para el scanner en tiempo real",
    version="1.0.0",
    lifespan=lifespan,
    # Superficie de descubrimiento desactivada: nadie debe poder enumerar
    # los endpoints desde fuera (api.tradeul.com/docs, /redoc, /openapi.json).
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# CORS Middleware
# Nota: allow_credentials=True requiere orígenes específicos (no "*")
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://157.180.45.153:3000",
    "http://157.180.45.153:3001",
    "https://tradeul.com",
    "https://www.tradeul.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth Middleware (PASIVO - lee token pero NO bloquea)
# Controlado por AUTH_ENABLED env var (default: false)
app.add_middleware(
    PassiveAuthMiddleware,
    enabled=getattr(settings, 'auth_enabled', False)
)

# Registrar routers
app.include_router(user_prefs_router)
app.include_router(tv_designs_router)
app.include_router(tv_drawings_router)
app.include_router(user_filters_router)
app.include_router(screener_templates_router)
app.include_router(financials_router)
app.include_router(watchlist_router)
app.include_router(proxy_router)  # Incluye endpoints de dilution, SEC filings, etc.
app.include_router(realtime_router)  # Real-time ticker data for charts
app.include_router(ratio_analysis_router)  # Ratio analysis entre dos activos
app.include_router(morning_news_router)  # Morning News Call diario
app.include_router(insights_router)  # Tradeul Insights (Morning, Mid-Morning, etc.)
app.include_router(symbols_router)  # Symbol lookups (market cap filtering for AI agent)
app.include_router(heatmap_router)  # Market heatmap visualization
app.include_router(scanner_router)  # Scanner filtered tickers
app.include_router(institutional_router)  # Form 13F institutional holdings
app.include_router(notes_router)  # User notes with TipTap content
app.include_router(earnings_router)  # Benzinga Earnings calendar
app.include_router(halts_router)  # Trading halts from LULD stream
app.include_router(l2replay_router)  # L2 Replay historico por venue (Databento)
app.include_router(alerts_router)  # Alert catalog and categories
app.include_router(alert_strategies_router)  # User alert strategies (CRUD)
app.include_router(performance_router)  # Market performance aggregation (sectors, industries, themes)
app.include_router(rrg_router)  # RRG (Relative Rotation Graph) with historical trails
app.include_router(analyst_ratings_router)  # Analyst ratings & price targets (Perplexity proxy)
app.include_router(perplexity_financials_router)  # Balance Sheet + Cash Flow (Perplexity proxy)
app.include_router(developer_router)               # Trader API key management (Openul stream)
app.include_router(bug_reports_router)             # Dashboard bug report submissions
app.include_router(imap_router)                    # World Venue Map (IMAP) — FMP exchange hours
app.include_router(tape_router)                    # Time & Sales: backfill + reference (conditions/exchanges)


# ============================================================================
# Financial Analyst Proxy (Gemini AI)
# ============================================================================

FINANCIAL_ANALYST_URL = os.getenv("FINANCIAL_ANALYST_URL", "http://financial_analyst:8099")


async def _get_ticker_metadata_for_fan(symbol: str) -> dict:
    """
    Obtener metadata del ticker para pasarla al Financial Analyst.
    Esto evita que Gemini busque datos que ya tenemos en BD.
    """
    from decimal import Decimal
    
    try:
        query = """
            SELECT 
                symbol, company_name, exchange, sector, industry,
                market_cap, shares_outstanding, free_float, free_float_percent,
                description, homepage_url, total_employees, cik, list_date,
                is_etf, type
            FROM ticker_metadata
            WHERE symbol = $1
        """
        result = await timescale_client.fetchrow(query, symbol.upper())
        
        if result:
            metadata = {}
            for key, value in dict(result).items():
                if value is None:
                    continue
                # Convertir Decimal a float para JSON
                if isinstance(value, Decimal):
                    metadata[key] = float(value)
                # Convertir date/datetime a string
                elif hasattr(value, 'isoformat'):
                    metadata[key] = str(value)
                else:
                    metadata[key] = value
            return metadata
    except Exception as e:
        logger.warning("fan_metadata_fetch_error", symbol=symbol, error=str(e))
    
    return {}


SCREENER_URL = os.getenv("SCREENER_URL", "http://screener:8000")


async def _get_technical_indicators_for_fan(symbol: str) -> dict:
    """
    Obtener indicadores técnicos DIARIOS desde el Screener service.
    El screener tiene RSI, SMA, 52W precomputados y es ~20x más rápido que SQL.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{SCREENER_URL}/api/v1/screener/screen",
                json={"filters": [], "symbols": [symbol.upper()], "limit": 1}
            )
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    r = results[0]
                    price = r.get("price")
                    sma_50 = r.get("sma_50")
                    sma_200 = r.get("sma_200")
                    
                    # Calcular high/low 52W desde el porcentaje
                    from_high = r.get("from_52w_high")  # Negativo = debajo del máximo
                    from_low = r.get("from_52w_low")    # Positivo = arriba del mínimo
                    
                    high_52w = price / (1 + from_high/100) if from_high and price else None
                    low_52w = price / (1 + from_low/100) if from_low and price else None
                    
                    # RSI status
                    rsi = r.get("rsi_14")
                    rsi_status = "Oversold" if rsi and rsi < 30 else "Overbought" if rsi and rsi > 70 else "Neutral"
                    
                    return {
                        "last_close": round(price, 2) if price else None,
                        "rsi_14": round(rsi, 1) if rsi else None,
                        "rsi_status": rsi_status,
                        "ma_50": round(sma_50, 2) if sma_50 else None,
                        "ma_200": round(sma_200, 2) if sma_200 else None,
                        "high_52w": round(high_52w, 2) if high_52w else None,
                        "low_52w": round(low_52w, 2) if low_52w else None,
                        "from_52w_high_pct": round(from_high, 1) if from_high else None,
                        "from_52w_low_pct": round(from_low, 1) if from_low else None,
                        "gap_percent": round(r.get("gap_percent", 0), 2),
                        "relative_volume": round(r.get("relative_volume", 0), 2),
                        "atr_14": round(r.get("atr_14", 0), 2) if r.get("atr_14") else None,
                        "query_time_ms": data.get("query_time_ms")
                    }
    except Exception as e:
        logger.warning("fan_technical_fetch_error", symbol=symbol, error=str(e))
    
    return {}


async def _get_insider_summary_for_fan(symbol: str) -> dict:
    """
    Obtener resumen de actividad insider reciente.
    """
    try:
        # Usar nuestro endpoint existente
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"http://localhost:8000/api/v1/insider-trading/{symbol}/details",
                params={"size": 10}
            )
            if response.status_code == 200:
                data = response.json()
                transactions = data.get("transactions", [])
                
                if not transactions:
                    return {}
                
                # Calcular resumen
                buys = [t for t in transactions if t.get("transaction_type") in ["P", "A"]]
                sells = [t for t in transactions if t.get("transaction_type") in ["S", "D"]]
                
                total_bought = sum(t.get("shares", 0) or 0 for t in buys)
                total_sold = sum(t.get("shares", 0) or 0 for t in sells)
                
                # Encontrar CEO/CFO en las transacciones
                executives = {}
                for t in transactions:
                    title = (t.get("owner_title") or "").upper()
                    name = t.get("owner_name", "")
                    if "CEO" in title or "CHIEF EXECUTIVE" in title:
                        executives["ceo"] = name
                    elif "CFO" in title or "CHIEF FINANCIAL" in title:
                        executives["cfo"] = name
                
                return {
                    "recent_transactions": len(transactions),
                    "buys_count": len(buys),
                    "sells_count": len(sells),
                    "total_shares_bought": total_bought,
                    "total_shares_sold": total_sold,
                    "net_insider_sentiment": "Bullish" if total_bought > total_sold else "Bearish" if total_sold > total_bought else "Neutral",
                    **executives
                }
    except Exception as e:
        logger.warning("fan_insider_fetch_error", symbol=symbol, error=str(e))
    
    return {}


async def _get_price_snapshot_for_fan(symbol: str) -> dict:
    """
    Obtener precio actual y cambio desde Polygon snapshot.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"http://localhost:8000/api/v1/ticker/{symbol}/snapshot"
            )
            if response.status_code == 200:
                data = response.json()
                ticker_data = data.get("ticker", {})
                day = ticker_data.get("day", {})
                prev_day = ticker_data.get("prevDay", {})
                
                current_price = day.get("c") or prev_day.get("c")
                prev_close = prev_day.get("c")
                
                if current_price and prev_close:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                    return {
                        "current_price": round(current_price, 2),
                        "prev_close": round(prev_close, 2),
                        "change_percent": round(change_pct, 2),
                        "day_volume": day.get("v"),
                        "day_high": day.get("h"),
                        "day_low": day.get("l")
                    }
    except Exception as e:
        logger.warning("fan_snapshot_fetch_error", symbol=symbol, error=str(e))
    
    return {}


async def _get_fundamentals_for_fan(symbol: str, current_price: float, cik: str = None) -> dict:
    """
    Obtener fundamentales desde SEC XBRL (P/E, P/B, P/S, EV/EBITDA, D/E).
    Datos oficiales de 10-K/10-Q, cacheados 7 días.
    
    Args:
        symbol: Ticker
        current_price: Precio actual
        cik: CIK de SEC (más preciso que ticker)
    """
    try:
        from fundamentals_extractor import get_fundamentals_for_fan
        result = await get_fundamentals_for_fan(symbol, current_price, redis_client, cik)
        
        if result.get("status") == "success":
            ratios = result.get("ratios", {})
            fundamentals = result.get("fundamentals", {})
            filing = result.get("filing", {})
            
            return {
                # Ratios calculados
                "pe_ratio": ratios.get("pe_ratio"),
                "pb_ratio": ratios.get("pb_ratio"),
                "ps_ratio": ratios.get("ps_ratio"),
                "ev_ebitda": ratios.get("ev_ebitda"),
                "debt_equity": ratios.get("debt_equity"),
                "profit_margin": ratios.get("profit_margin"),
                # Datos crudos
                "eps_diluted": fundamentals.get("eps_diluted"),
                "revenue": fundamentals.get("revenue"),
                "net_income": fundamentals.get("net_income"),
                "total_debt": fundamentals.get("total_debt"),
                "cash": fundamentals.get("cash"),
                # Info del filing
                "filing_type": filing.get("form_type"),
                "filing_date": filing.get("period_end"),
                "accounting_standard": result.get("standard")
            }
    except Exception as e:
        logger.warning("fan_fundamentals_error", symbol=symbol, error=str(e))
    
    return {}


async def _get_polygon_ratios_for_fan(symbol: str) -> dict:
    """
    Obtener ratios financieros TTM desde Polygon.
    Incluye dividend_yield, ROE, ROA, current_ratio, quick_ratio, cash_ratio,
    EV/EBITDA, EV/Sales, free_cash_flow, y ratios de precio.
    Cache: 24 horas (se actualiza diario en Polygon).
    """
    cache_key = f"fan:polygon_ratios:{symbol.upper()}"
    try:
        cached = await redis_client.get(cache_key)
        if cached and isinstance(cached, dict):
            return cached
    except Exception:
        pass

    try:
        data = await http_clients.polygon.get_financial_ratios(symbol)
        results = data.get("results", [])
        if not results:
            return {}

        r = results[0]
        result = {
            "dividend_yield": r.get("dividend_yield"),
            "return_on_equity": r.get("return_on_equity"),
            "return_on_assets": r.get("return_on_assets"),
            "current_ratio": r.get("current"),
            "quick_ratio": r.get("quick"),
            "cash_ratio": r.get("cash"),
            "debt_to_equity": r.get("debt_to_equity"),
            "price_to_earnings": r.get("price_to_earnings"),
            "price_to_book": r.get("price_to_book"),
            "price_to_sales": r.get("price_to_sales"),
            "price_to_cash_flow": r.get("price_to_cash_flow"),
            "price_to_free_cash_flow": r.get("price_to_free_cash_flow"),
            "ev_to_ebitda": r.get("ev_to_ebitda"),
            "ev_to_sales": r.get("ev_to_sales"),
            "enterprise_value": r.get("enterprise_value"),
            "free_cash_flow": r.get("free_cash_flow"),
            "earnings_per_share": r.get("earnings_per_share"),
            "market_cap": r.get("market_cap"),
            "date": r.get("date"),
        }
        # Quitar nulos para no ensuciar el payload
        result = {k: v for k, v in result.items() if v is not None}

        try:
            await redis_client.set(cache_key, result, ttl=86400)  # 24h
        except Exception:
            pass

        return result
    except Exception as e:
        logger.warning("fan_polygon_ratios_error", symbol=symbol, error=str(e))
    return {}


# ============================================================================
# Perplexity v3 deterministic "Key Metrics" snapshot (TIKR-style)
# ----------------------------------------------------------------------------
# Single authoritative source for every NUMBER shown in the DESC window, reusing
# the same v3 layer that powers the FA window. Gemini never produces numbers.
# ============================================================================

# LTM ratio map: snapshot_field -> (Perplexity ratioId, is_percent_fraction)
# Percent fields come back as fractions (0.27) and are scaled ×100 → 27.0.
_V3_LTM_MAP = {
    # Capital structure
    "market_cap":          ("calculated_market_cap", False),
    "enterprise_value":    ("calculated_tev", False),
    "net_debt":            ("calculated_net_debt", False),
    "total_debt":          ("calculated_total_debt", False),
    "net_debt_to_ebitda":  ("ratio_net_debt_to_ebitda", False),
    "shares_outstanding":  ("market_data_total_shares_outstanding", False),
    "share_price":         ("market_data_share_price", False),
    # Efficiency
    "gross_margin":        ("ratio_gross_profit_margin", True),
    "ebit_margin":         ("ratio_operating_margin", True),
    "ebitda_margin":       ("ratio_ebitda_margin", True),
    "net_margin":          ("ratio_net_profit_margin", True),
    "fcf_margin":          ("ratio_fcf_margin", True),
    "roa":                 ("ratio_return_on_assets", True),
    "roe":                 ("ratio_return_on_equity", True),
    "roic":                ("ratio_return_on_invested_capital", True),
    "roce":                ("ratio_return_on_capital_employed", True),
    # Valuation (LTM)
    "ev_to_revenue":       ("ratio_ev_to_sales", False),
    "ev_to_gross_profit":  ("ratio_ev_to_gross_profit", False),
    "ev_to_ebitda":        ("ratio_ev_to_ebitda", False),
    "pe":                  ("ratio_price_to_earnings", False),
    "ps":                  ("ratio_price_to_sales", False),
    "pb":                  ("ratio_price_to_book", False),
    "p_fcf":               ("ratio_price_to_fcf", False),
    "ncav":                ("calculated_net_current_asset_value", False),
    "dividend_yield":      ("calculated_dividend_yield", True),
    "payout_ratio":        ("ratio_payout_ratio", True),
    "current_ratio":       ("ratio_current_ratio", False),
    "debt_to_equity":      ("ratio_debt_to_equity", False),
    "diluted_eps":         ("ratio_diluted_eps", False),
    # Growth (trailing CAGR)
    "rev_cagr_3y":         ("growth_revenue_3y_cagr", True),
    "ebitda_cagr_3y":      ("growth_ebitda_3y_cagr", True),
    "eps_cagr_3y":         ("growth_diluted_eps_3y_cagr", True),
    "rev_growth_1y":       ("growth_revenue_1y", True),
    "eps_growth_1y":       ("growth_diluted_eps_1y", True),
}


def _grade_from_keymetrics(m: dict) -> Optional[str]:
    """Deterministic financial-health letter grade from quality signals."""
    def band(v, a, b, c):
        # returns 1 / 0.7 / 0.4 / 0.1 for >=a / >=b / >=c / else
        if v is None:
            return None
        return 1.0 if v >= a else 0.7 if v >= b else 0.4 if v >= c else 0.1

    def band_inv(v, a, b, c):
        # lower is better (e.g. debt/equity)
        if v is None:
            return None
        return 1.0 if v <= a else 0.7 if v <= b else 0.4 if v <= c else 0.1

    signals = [
        band(m.get("net_margin"), 20, 10, 0),
        band(m.get("rev_growth_1y"), 20, 8, 0),
        band(m.get("roe"), 20, 10, 0),
        band(m.get("fcf_margin"), 15, 5, 0),
        band_inv(m.get("debt_to_equity"), 0.5, 1.0, 2.0),
    ]
    scored = [s for s in signals if s is not None]
    if not scored:
        return None
    avg = sum(scored) / len(scored)
    if avg >= 0.9:
        return "A+"
    if avg >= 0.8:
        return "A"
    if avg >= 0.7:
        return "B+"
    if avg >= 0.6:
        return "B"
    if avg >= 0.5:
        return "C+"
    if avg >= 0.4:
        return "C"
    return "D"


async def _get_v3_keymetrics_for_fan(symbol: str, current_price: float = 0.0) -> dict:
    """
    Build the deterministic TIKR-style key-metrics snapshot from Perplexity v3.

    Returns a flat dict with LTM ratios/margins/efficiency, trailing CAGRs, and
    forward (NTM / FY+2) multiples & CAGRs computed from analyst estimates.
    Percent fields are stored as percent numbers (e.g. 27.1 → 27.1%).
    """
    cache_key = f"fan:v3_keymetrics:{symbol.upper()}"
    try:
        cached = await redis_client.get(cache_key)
        if cached and isinstance(cached, dict):
            return cached
    except Exception:
        pass

    try:
        from perplexity_v3 import (
            fetch_v3,
            fetch_v3_with_estimates,
            transform_ratios,
            transform_key_stats,
        )

        ttm_payload = await fetch_v3(symbol, "ttm")
        ratios = transform_ratios(symbol, "ttm", ttm_payload) if ttm_payload else None
        if not ratios:
            return {}

        rmap = {f["key"]: f for f in (ratios.get("fields") or [])}

        # v3 periods are ordered most-recent-first, so the latest value is the
        # first non-null entry in the values array.
        def _recent(key):
            f = rmap.get(key)
            if not f:
                return None
            for v in (f.get("values") or []):
                if v is not None:
                    return v
            return None

        m: dict = {"currency": ratios.get("currency")}
        for field, (rid, is_pct) in _V3_LTM_MAP.items():
            v = _recent(rid)
            if v is None:
                continue
            m[field] = round(v * 100, 4) if is_pct else v

        # --- Forward estimates (NTM / FY+2) from annual key_stats -------------
        try:
            ks_payload = await fetch_v3_with_estimates(symbol, "annual")
            ks = transform_key_stats(symbol, "annual", ks_payload) if ks_payload else None
            if ks:
                periods = ks.get("periods") or []
                est = set(ks.get("estimate_periods") or [])
                kmap = {f["key"]: f for f in (ks.get("fields") or [])}

                def _at(key, period):
                    f = kmap.get(key)
                    if not f or period not in periods:
                        return None
                    vals = f.get("values") or []
                    idx = periods.index(period)
                    return vals[idx] if idx < len(vals) else None

                actual_years = sorted((p for p in periods if p not in est and p.isdigit()), key=int)
                est_years = sorted((p for p in est if p.isdigit()), key=int)
                last_actual = actual_years[-1] if actual_years else None
                ntm = est_years[0] if est_years else None
                fy2 = est_years[1] if len(est_years) > 1 else None

                ev = m.get("enterprise_value")
                mc = m.get("market_cap")

                rev_ntm = _at("key_stats_total_revenues", ntm) if ntm else None
                ebitda_ntm = _at("key_stats_ebitda", ntm) if ntm else None
                ni_ntm = _at("key_stats_net_income", ntm) if ntm else None
                fcf_ntm = _at("key_stats_free_cash_flow", ntm) if ntm else None
                eps_ntm = _at("key_stats_diluted_eps", ntm) if ntm else None

                if ev and rev_ntm:
                    m["ntm_ev_to_revenue"] = round(ev / rev_ntm, 2)
                if ev and ebitda_ntm and ebitda_ntm > 0:
                    m["ntm_ev_to_ebitda"] = round(ev / ebitda_ntm, 2)
                if mc and ni_ntm and ni_ntm > 0:
                    m["ntm_pe"] = round(mc / ni_ntm, 2)
                elif current_price and eps_ntm and eps_ntm > 0:
                    m["ntm_pe"] = round(current_price / eps_ntm, 2)
                if mc and fcf_ntm and fcf_ntm > 0:
                    m["ntm_mc_to_fcf"] = round(mc / fcf_ntm, 2)
                if eps_ntm is not None:
                    m["ntm_eps"] = eps_ntm

                def _cagr(base, end, yrs):
                    if base and end and base > 0 and end > 0 and yrs > 0:
                        return round(((end / base) ** (1 / yrs) - 1) * 100, 2)
                    return None

                if last_actual and fy2:
                    yrs = int(fy2) - int(last_actual)
                    m["fwd_rev_cagr_2y"] = _cagr(
                        _at("key_stats_total_revenues", last_actual),
                        _at("key_stats_total_revenues", fy2), yrs)
                    m["fwd_ebitda_cagr_2y"] = _cagr(
                        _at("key_stats_ebitda", last_actual),
                        _at("key_stats_ebitda", fy2), yrs)
                    m["fwd_eps_cagr_2y"] = _cagr(
                        _at("key_stats_diluted_eps", last_actual),
                        _at("key_stats_diluted_eps", fy2), yrs)
        except Exception as e:
            logger.warning("fan_v3_keymetrics_fwd_error", symbol=symbol, error=str(e))

        # --- Derived LTM ------------------------------------------------------
        mc = m.get("market_cap")
        ncav = m.get("ncav")
        if mc and ncav and ncav != 0:
            m["p_ncav"] = round(mc / ncav, 2)

        pe = m.get("pe")
        eg = m.get("eps_growth_1y")
        if pe and eg and eg > 0:
            m["peg"] = round(pe / eg, 2)

        # Forward P/E for the existing Valuation widget = NTM P/E.
        m["forward_pe"] = m.get("ntm_pe")
        m["financial_grade"] = _grade_from_keymetrics(m)
        m["_source"] = "perplexity_v3"

        try:
            await redis_client.set(cache_key, m, ttl=86400)
        except Exception:
            pass
        return m
    except Exception as e:
        logger.warning("fan_v3_keymetrics_error", symbol=symbol, error=str(e))
    return {}


async def _get_short_interest_for_fan(symbol: str) -> dict:
    """
    Obtener short interest bi-mensual desde Polygon (fuente: FINRA).
    Incluye short_interest, days_to_cover, avg_daily_volume.
    Cache: 12 horas (se publica cada 2 semanas, pero cambia poco intradía).
    """
    cache_key = f"fan:short_interest:{symbol.upper()}"
    try:
        cached = await redis_client.get(cache_key)
        if cached and isinstance(cached, dict):
            return cached
    except Exception:
        pass

    try:
        data = await http_clients.polygon.get_short_interest(symbol)
        results = data.get("results", [])
        if not results:
            return {}

        r = results[0]
        result = {
            "short_interest": r.get("short_interest"),
            "days_to_cover": r.get("days_to_cover"),
            "avg_daily_volume": r.get("avg_daily_volume"),
            "settlement_date": r.get("settlement_date"),
        }
        result = {k: v for k, v in result.items() if v is not None}

        try:
            await redis_client.set(cache_key, result, ttl=43200)  # 12h
        except Exception:
            pass

        return result
    except Exception as e:
        logger.warning("fan_short_interest_error", symbol=symbol, error=str(e))
    return {}


async def _get_analyst_ratings_for_fan(symbol: str) -> dict:
    """
    Obtener ratings de analistas desde Perplexity Finance.
    Reutiliza _fetch_ratings del módulo analyst_ratings (misma sesión curl_cffi).
    Cache: 1 hora.
    """
    cache_key = f"fan:analyst_ratings:{symbol.upper()}"
    try:
        cached = await redis_client.get(cache_key)
        if cached and isinstance(cached, dict):
            return cached
    except Exception:
        pass

    try:
        from routes.analyst_ratings import _fetch_ratings
        data = await asyncio.to_thread(_fetch_ratings, symbol.upper())
        if data:
            try:
                await redis_client.set(cache_key, data, ttl=3600)
            except Exception:
                pass
            return data
    except Exception as e:
        logger.warning("fan_analyst_ratings_error", symbol=symbol, error=str(e))
    return {}


async def _get_news_for_fan(symbol: str, limit: int = 5) -> list:
    """
    Obtener las últimas noticias del ticker desde Polygon.
    Devuelve lista de {title, published_utc, publisher, article_url}.
    Cache: 30 minutos.
    """
    cache_key = f"fan:news:{symbol.upper()}"
    try:
        cached = await redis_client.get(cache_key)
        if isinstance(cached, list):
            return cached
    except Exception:
        pass

    try:
        data = await http_clients.polygon.get_news(symbol, limit=limit)
        results = data.get("results", [])
        news = [
            {
                "title": r.get("title"),
                "published_utc": r.get("published_utc"),
                "publisher": r.get("publisher", {}).get("name"),
                "article_url": r.get("article_url"),
                "description": (r.get("description") or "")[:200],
            }
            for r in results
            if r.get("title")
        ]
        try:
            await redis_client.set(cache_key, news, ttl=1800)  # 30 min
        except Exception:
            pass
        return news
    except Exception as e:
        logger.warning("fan_news_error", symbol=symbol, error=str(e))
    return []


@app.get("/api/report/{ticker}/instant")
async def get_instant_report(ticker: str):
    """Endpoint RÁPIDO: Solo datos internos sin Gemini (~1-2s).
    
    Devuelve inmediatamente:
    - Metadata de BD (company_name, sector, industry, etc.)
    - Technical (RSI, MA50, MA200, 52W)
    - Insider summary + CEO/CFO
    - Price snapshot
    - Fundamentals XBRL (P/E, P/B, P/S, EV/EBITDA)
    
    El frontend puede mostrar esto mientras espera a Gemini.
    """
    import time
    start_time = time.time()
    
    try:
        # 1. Primero obtener precio Y metadata en paralelo (necesitamos CIK)
        price_task = _get_price_snapshot_for_fan(ticker)
        metadata_task = _get_ticker_metadata_for_fan(ticker)
        
        price, db_metadata = await asyncio.gather(price_task, metadata_task, return_exceptions=True)
        
        if isinstance(price, Exception):
            price = {}
        if isinstance(db_metadata, Exception):
            db_metadata = {}
        
        current_price = price.get("current_price", 0) if price else 0
        cik = db_metadata.get("cik") if db_metadata else None
        
        # 2. Ejecutar el resto EN PARALELO
        technical_task = _get_technical_indicators_for_fan(ticker)
        insider_task = _get_insider_summary_for_fan(ticker)
        fundamentals_task = _get_fundamentals_for_fan(ticker, current_price, cik) if current_price else asyncio.sleep(0)
        
        technical, insider, fundamentals = await asyncio.gather(
            technical_task, insider_task, fundamentals_task,
            return_exceptions=True
        )
        
        # Manejar excepciones
        technical = {} if isinstance(technical, Exception) else technical
        insider = {} if isinstance(insider, Exception) else insider
        fundamentals = {} if isinstance(fundamentals, Exception) or fundamentals is None else fundamentals
        
        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.info("instant_report_complete", ticker=ticker, elapsed_ms=elapsed_ms)
        
        # Construir respuesta con estructura similar a AIReport pero solo datos internos
        return {
            "ticker": ticker.upper(),
            "company_name": db_metadata.get("company_name", ticker.upper()),
            "sector": db_metadata.get("sector"),
            "industry": db_metadata.get("industry"),
            "exchange": db_metadata.get("exchange"),
            "ceo": insider.get("ceo"),
            "website": db_metadata.get("website"),
            "employees": db_metadata.get("employees"),
            "business_summary": db_metadata.get("description"),
            "special_status": None,
            # Valuation from XBRL
            "pe_ratio": fundamentals.get("pe_ratio"),
            "pb_ratio": fundamentals.get("pb_ratio"),
            "ps_ratio": fundamentals.get("ps_ratio"),
            "ev_ebitda": fundamentals.get("ev_ebitda"),
            "forward_pe": None,  # Requiere Gemini
            "peg_ratio": None,   # Requiere Gemini
            "dividend_yield": None,  # Requiere Gemini
            "dividend_frequency": None,
            # Financial health from XBRL
            "financial_health": {
                "debt_to_equity": fundamentals.get("debt_equity"),
                "profit_margin": fundamentals.get("profit_margin"),
            } if fundamentals else None,
            "financial_grade": None,  # Requiere Gemini
            # Technical from Screener
            "technical": {
                "trend": None,  # Requiere Gemini
                "rsi_status": _interpret_rsi(technical.get("rsi_14")) if technical.get("rsi_14") else None,
                "ma_50_status": technical.get("ma_50_status"),
                "ma_200_status": technical.get("ma_200_status"),
                "support_level": None,  # Requiere Gemini
                "resistance_level": None,
            } if technical else None,
            # Insider
            "insider_sentiment": insider.get("sentiment"),
            "insider_activity": insider.get("recent_transactions", []),
            # Price
            "price_snapshot": price,
            # Campos que requieren Gemini (vacíos)
            "consensus_rating": None,
            "analyst_ratings": [],
            "average_price_target": None,
            "price_target_high": None,
            "price_target_low": None,
            "short_interest": None,
            "competitors": None,
            "upcoming_catalysts": None,
            "earnings_date": None,
            "news_sentiment": None,
            "risk_sentiment": None,
            "risk_factors": [],
            "critical_event": None,
            # Metadata
            "generated_at": None,
            "_instant": True,  # Flag para indicar que es respuesta instantánea
            "_elapsed_ms": elapsed_ms,
        }
    except Exception as e:
        logger.error("instant_report_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def _interpret_rsi(rsi: float | None) -> str | None:
    """Interpreta RSI como status textual."""
    if rsi is None:
        return None
    if rsi < 30:
        return "Oversold"
    elif rsi > 70:
        return "Overbought"
    else:
        return "Neutral"


@app.get("/api/report/{ticker}/key-metrics")
async def get_key_metrics(ticker: str):
    """Deterministic TIKR-style key metrics for the DESC window.

    100% structured data (Perplexity v3 + internal sources). No LLM, no
    hallucinated numbers — consistent with the FA window for the same ticker.
    """
    symbol = ticker.upper()

    # Price + metadata first (needed for current price / market data).
    price, meta = await asyncio.gather(
        _get_price_snapshot_for_fan(symbol),
        _get_ticker_metadata_for_fan(symbol),
        return_exceptions=True,
    )
    price = {} if isinstance(price, Exception) else (price or {})
    meta = {} if isinstance(meta, Exception) else (meta or {})
    current_price = price.get("current_price") or 0.0

    km, tech, si, ratings = await asyncio.gather(
        _get_v3_keymetrics_for_fan(symbol, current_price),
        _get_technical_indicators_for_fan(symbol),
        _get_short_interest_for_fan(symbol),
        _get_analyst_ratings_for_fan(symbol),
        return_exceptions=True,
    )
    km = {} if isinstance(km, Exception) else (km or {})
    tech = {} if isinstance(tech, Exception) else (tech or {})
    si = {} if isinstance(si, Exception) else (si or {})
    ratings = {} if isinstance(ratings, Exception) else (ratings or {})

    consensus = ratings.get("consensus") if isinstance(ratings.get("consensus"), dict) else {}
    street_target = consensus.get("averagePriceTarget") or ratings.get("priceTarget")

    def r(label, value, fmt):
        return {"label": label, "value": value, "format": fmt}

    groups = [
        {"title": "Market Data", "rows": [
            r("52 Week High", tech.get("high_52w"), "price"),
            r("52 Week Low", tech.get("low_52w"), "price"),
            r("Avg Daily Volume", si.get("avg_daily_volume"), "int"),
            r("Float %", meta.get("free_float_percent"), "percent"),
        ]},
        {"title": "Capital Structure", "rows": [
            r("Market Cap", km.get("market_cap"), "money_mm"),
            r("Enterprise Value", km.get("enterprise_value"), "money_mm"),
            r("Shares Outstanding", km.get("shares_outstanding"), "shares_mm"),
            r("Net Debt", km.get("net_debt"), "money_mm"),
            r("Net Debt / EBITDA", km.get("net_debt_to_ebitda"), "multiple"),
            r("Debt / Equity", km.get("debt_to_equity"), "multiple"),
            r("Current Ratio", km.get("current_ratio"), "multiple"),
        ]},
        {"title": "Efficiency", "rows": [
            r("Gross Margin", km.get("gross_margin"), "percent"),
            r("EBIT Margin", km.get("ebit_margin"), "percent"),
            r("Net Margin", km.get("net_margin"), "percent"),
            r("FCF Margin", km.get("fcf_margin"), "percent"),
            r("ROA", km.get("roa"), "percent"),
            r("ROE", km.get("roe"), "percent"),
            r("ROIC", km.get("roic"), "percent"),
            r("ROCE", km.get("roce"), "percent"),
        ]},
        {"title": "Growth", "rows": [
            r("Fwd 2-Yr Rev. CAGR", km.get("fwd_rev_cagr_2y"), "percent"),
            r("Fwd 2-Yr EBITDA CAGR", km.get("fwd_ebitda_cagr_2y"), "percent"),
            r("Fwd 2-Yr EPS CAGR", km.get("fwd_eps_cagr_2y"), "percent"),
            r("Last 3-Yr Rev. CAGR", km.get("rev_cagr_3y"), "percent"),
            r("Last 3-Yr EBITDA CAGR", km.get("ebitda_cagr_3y"), "percent"),
            r("Last 3-Yr EPS CAGR", km.get("eps_cagr_3y"), "percent"),
        ]},
        {"title": "Valuation", "rows": [
            r("Street Target Price", street_target, "price"),
            r("NTM EV/Revenues", km.get("ntm_ev_to_revenue"), "multiple"),
            r("NTM EV/EBITDA", km.get("ntm_ev_to_ebitda"), "multiple"),
            r("NTM P/E", km.get("ntm_pe"), "multiple"),
            r("NTM MC/FCF", km.get("ntm_mc_to_fcf"), "multiple"),
            r("LTM EV/Revenues", km.get("ev_to_revenue"), "multiple"),
            r("LTM EV/Gross Profit", km.get("ev_to_gross_profit"), "multiple"),
            r("LTM P/E", km.get("pe"), "multiple"),
            r("LTM P/BV", km.get("pb"), "multiple"),
            r("LTM P/NCAV", km.get("p_ncav"), "multiple"),
            r("Dividend Yield", km.get("dividend_yield"), "percent"),
            r("Payout Ratio", km.get("payout_ratio"), "percent"),
        ]},
    ]

    return {
        "symbol": symbol,
        "currency": km.get("currency") or "USD",
        "source": km.get("_source") or "perplexity_v3",
        "groups": groups,
    }


@app.get("/api/report/{ticker}")
async def proxy_financial_analyst_report(ticker: str, lang: str = Query("en")):
    """Proxy to Financial Analyst service for AI-generated reports (completo con Gemini).
    
    Optimización HÍBRIDA: Obtenemos datos de múltiples fuentes locales en paralelo
    y los pasamos a financial-analyst para reducir el trabajo de Gemini.
    
    Datos locales (paralelo):
    - Metadata: company_name, sector, industry, exchange, employees, etc.
    - Technical: RSI-14, MA50, MA200, 52W High/Low (desde Screener)
    - Insider: resumen de actividad insider + nombres CEO/CFO
    - Price: precio actual y cambio desde Polygon
    - Fundamentals: P/E, P/B, P/S, EV/EBITDA desde SEC XBRL (NUEVO)
    """
    import time
    start_time = time.time()
    
    try:
        # 1. Primero obtener precio Y metadata en paralelo (necesitamos CIK de metadata)
        price_task = _get_price_snapshot_for_fan(ticker)
        metadata_task = _get_ticker_metadata_for_fan(ticker)
        
        price, db_metadata = await asyncio.gather(price_task, metadata_task, return_exceptions=True)
        
        if isinstance(price, Exception):
            logger.warning("fan_price_exception", error=str(price))
            price = {}
        if isinstance(db_metadata, Exception):
            logger.warning("fan_metadata_exception", error=str(db_metadata))
            db_metadata = {}
        
        current_price = price.get("current_price", 0) if price else 0
        cik = db_metadata.get("cik") if db_metadata else None  # CIK para búsqueda precisa en SEC
        
        # 2. Ejecutar el resto EN PARALELO (usando CIK para fundamentals)
        technical_task = _get_technical_indicators_for_fan(ticker)
        insider_task = _get_insider_summary_for_fan(ticker)
        fundamentals_task = _get_fundamentals_for_fan(ticker, current_price, cik) if current_price else asyncio.sleep(0)
        polygon_ratios_task = _get_polygon_ratios_for_fan(ticker)
        short_interest_task = _get_short_interest_for_fan(ticker)
        analyst_ratings_task = _get_analyst_ratings_for_fan(ticker)
        news_task = _get_news_for_fan(ticker, limit=5)

        technical, insider, fundamentals, polygon_ratios, short_interest, analyst_ratings, news = await asyncio.gather(
            technical_task, insider_task, fundamentals_task,
            polygon_ratios_task, short_interest_task, analyst_ratings_task, news_task,
            return_exceptions=True
        )

        # Manejar excepciones individuales
        if isinstance(technical, Exception):
            logger.warning("fan_technical_exception", error=str(technical))
            technical = {}
        if isinstance(insider, Exception):
            logger.warning("fan_insider_exception", error=str(insider))
            insider = {}
        if isinstance(fundamentals, Exception) or fundamentals is None:
            if isinstance(fundamentals, Exception):
                logger.warning("fan_fundamentals_exception", error=str(fundamentals))
            fundamentals = {}
        if isinstance(polygon_ratios, Exception):
            logger.warning("fan_polygon_ratios_exception", error=str(polygon_ratios))
            polygon_ratios = {}
        if isinstance(short_interest, Exception):
            logger.warning("fan_short_interest_exception", error=str(short_interest))
            short_interest = {}
        if isinstance(analyst_ratings, Exception):
            logger.warning("fan_analyst_ratings_exception", error=str(analyst_ratings))
            analyst_ratings = {}
        if isinstance(news, Exception):
            logger.warning("fan_news_exception", error=str(news))
            news = []

        # 3. Combinar todos los datos
        enriched_metadata = {
            **db_metadata,
            "technical_daily": technical,        # RSI, MA, 52W - DIARIOS
            "insider_summary": insider,          # Resumen + CEO/CFO
            "price_snapshot": price,             # Precio actual
            "fundamentals_xbrl": fundamentals,   # P/E, P/B, P/S desde SEC XBRL
            "polygon_ratios": polygon_ratios,    # Ratios TTM de Polygon (div yield, ROE, ROA, etc.)
            "short_interest": short_interest,    # Short interest FINRA via Polygon
            "analyst_ratings": analyst_ratings,  # Ratings de analistas via Perplexity
            "recent_news": news,                 # Últimas noticias via Polygon
        }

        local_time = round((time.time() - start_time) * 1000)
        logger.info("fan_local_data_collected",
                   ticker=ticker,
                   local_time_ms=local_time,
                   has_metadata=bool(db_metadata),
                   has_technical=bool(technical),
                   has_insider=bool(insider),
                   has_price=bool(price),
                   has_fundamentals=bool(fundamentals),
                   has_polygon_ratios=bool(polygon_ratios),
                   has_short_interest=bool(short_interest),
                   has_analyst_ratings=bool(analyst_ratings),
                   has_news=bool(news))
        
        # 3. Llamar a financial-analyst con TODOS los datos
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{FINANCIAL_ANALYST_URL}/api/report/{ticker}",
                params={"lang": lang},
                json={"db_metadata": enriched_metadata}
            )
            
            total_time = round((time.time() - start_time) * 1000)
            logger.info("fan_report_complete",
                       ticker=ticker,
                       total_time_ms=total_time,
                       local_time_ms=local_time,
                       gemini_time_ms=total_time - local_time)
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type="application/json"
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI report generation timed out")
    except Exception as e:
        logger.error("financial_analyst_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Failed to reach Financial Analyst service: {str(e)}")


# ============================================================================
# Stream Broadcaster
# ============================================================================

async def broadcast_streams():
    """
    DESACTIVADO COMPLETAMENTE: Ahora usamos servidor WebSocket dedicado (websocket_server)
    Esta función ya no se ejecuta - la línea está comentada en startup()
    """
    # Esta función nunca debe ejecutarse - está desactivada en startup()
    logger.warning("broadcast_streams() fue llamado pero está DESACTIVADO")
    return  # Return inmediatamente sin hacer nada
    
    streams_config = [
        {
            "stream": "stream:analytics:rvol",
            "group": "api_gateway_rvol",
            "consumer": "gateway_consumer_1",
            "message_type": "rvol"
        },
        {
            "stream": "stream:realtime:aggregates",
            "group": "api_gateway_agg",
            "consumer": "gateway_consumer_2",
            "message_type": "aggregate"
        }
    ]
    
    # Crear consumer groups
    for config in streams_config:
        try:
            await redis_client.create_consumer_group(
                config["stream"],
                config["group"],
                mkstream=True
            )
        except Exception as e:
            logger.debug("consumer_group_exists", stream=config["stream"])
    
    while True:
        try:
            # Leer de múltiples streams
            for config in streams_config:
                messages = await redis_client.read_stream(
                    stream_name=config["stream"],
                    consumer_group=config["group"],
                    consumer_name=config["consumer"],
                    count=50,
                    block=100  # 100ms
                )
                
                if messages:
                    # Parsear estructura: [(stream_name, [(message_id, data), ...])]
                    for stream_name, stream_messages in messages:
                        for message_id, data in stream_messages:
                            symbol = data.get('symbol') if isinstance(data, dict) else None
                            
                            if symbol:
                                # Transformar datos de Redis a formato Polygon para el frontend
                                transformed_data = {
                                    "o": float(data.get('open', 0)),
                                    "h": float(data.get('high', 0)),
                                    "l": float(data.get('low', 0)),
                                    "c": float(data.get('close', 0)),
                                    "v": int(data.get('volume', 0)),
                                    "vw": float(data.get('vwap', 0)),
                                    "av": int(data.get('volume_accumulated', 0)),
                                    "op": float(data.get('open', 0)),
                                }
                                
                                # Agregar RVOL si existe
                                if 'rvol' in data:
                                    transformed_data['rvol'] = float(data['rvol'])
                                
                                # Preparar mensaje para WebSocket
                                ws_message = {
                                    "type": config["message_type"],
                                    "symbol": symbol,
                                    "data": transformed_data,
                                    "timestamp": datetime.now().isoformat()
                                }
                                
                                # Broadcast a suscriptores
                                await connection_manager.broadcast_to_subscribers(
                                    ws_message,
                                    symbol
                                )
                            
                            # ACK mensaje
                            await redis_client.xack(
                                config["stream"],
                                config["group"],
                                message_id
                            )
            
            # Pequeña pausa para no saturar CPU
            await asyncio.sleep(0.01)
        
        except asyncio.CancelledError:
            logger.info("stream_broadcaster_cancelled")
            raise
        
        except Exception as e:
            logger.error(
                "stream_broadcaster_error",
                error=str(e),
                error_type=type(e).__name__
            )
            await asyncio.sleep(1)


# ============================================================================
# REST API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "api_gateway",
        "timestamp": datetime.now().isoformat(),
        "redis_connected": redis_client is not None,
        "timescale_connected": timescale_client is not None
    }


@app.get("/api/v1/auth/me")
async def get_current_user_info(user: AuthenticatedUser = Depends(get_current_user)):
    """
    Endpoint de prueba para verificar autenticación.
    Devuelve los datos del usuario autenticado.
    """
    return {
        "authenticated": True,
        "user_id": user.id,
        "email": user.email,
        "name": user.display_name,
        "is_admin": user.is_admin,
        "is_premium": user.is_premium,
        "roles": user.roles,
    }


@app.get("/api/v1/scanner/status")
async def get_scanner_status():
    """
    Obtiene el estado actual del scanner
    
    Returns:
        Estado general del sistema
    """
    try:
        # Obtener estado de Redis
        market_session = await redis_client.get("market:session:current")
        
        # Obtener count de tickers filtrados
        filtered_count = await redis_client.get("scanner:filtered:count")
        
        return {
            "status": "running",
            "market_session": market_session or "UNKNOWN",
            "filtered_tickers_count": int(filtered_count or 0),
            "websocket_connections": connection_manager.stats["active_connections"],
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("scanner_status_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/scanner/filtered")
async def get_filtered_tickers(
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Obtiene los tickers actualmente filtrados por el scanner
    
    Args:
        limit: Número máximo de tickers a retornar
    
    Returns:
        Lista de tickers filtrados con sus métricas
    """
    try:
        # Obtener sesión de mercado actual (usa cliente con connection pooling)
        session_data = await http_clients.market_session.get_current_session()
        current_session = session_data.get('session', 'POST_MARKET')
        
        # Leer desde cache del scanner (donde realmente se guardan los tickers)
        cache_key = f"scanner:filtered_complete:{current_session}"
        cached_data = await redis_client.get(cache_key, deserialize=True)
        
        if cached_data and isinstance(cached_data, list):
            # Limitar y retornar
            tickers = cached_data[:limit]
            return {
                "tickers": tickers,
                "count": len(tickers),
                "timestamp": datetime.now().isoformat()
            }
        
        # Fallback 1: Intentar leer último scan guardado (sin TTL)
        last_scan_key = "scanner:filtered_complete:LAST"
        last_scan_data = await redis_client.get(last_scan_key, deserialize=True)
        
        if last_scan_data and isinstance(last_scan_data, dict):
            last_tickers = last_scan_data.get("tickers", [])
            if last_tickers and isinstance(last_tickers, list):
                logger.info("using_last_scan_fallback", session=last_scan_data.get("session"), count=len(last_tickers))
                tickers = last_tickers[:limit]
                return {
                    "tickers": tickers,
                    "count": len(tickers),
                    "timestamp": last_scan_data.get("timestamp", datetime.now().isoformat()),
                    "source": "last_scan_cache"
                }
        
        # Fallback 2: Intentar leer del stream (por compatibilidad)
        messages = await redis_client.read_stream_range(
            "stream:scanner:filtered",
            count=limit
        )
        
        tickers = []
        seen = set()
        
        for message_id, data in messages:
            symbol = data.get('symbol')
            if symbol and symbol not in seen:
                tickers.append({
                    "symbol": symbol,
                    "price": float(data.get('price', 0)),
                    "change_percent": float(data.get('change_percent', 0)),
                    "volume": int(data.get('volume', 0)),
                    "rvol": float(data.get('rvol', 0)),
                    "market_cap": float(data.get('market_cap', 0)),
                    "timestamp": data.get('timestamp')
                })
                seen.add(symbol)
        
        return {
            "tickers": tickers,
            "count": len(tickers),
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("filtered_tickers_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ticker/{symbol}")
async def get_ticker_details(symbol: str):
    """
    Obtiene información detallada de un ticker
    
    Args:
        symbol: Símbolo del ticker (ej: AAPL)
    
    Returns:
        Información completa del ticker
    """
    try:
        symbol = symbol.upper()
        
        # Obtener datos de Redis (caché)
        cached_data = await redis_client.get(f"ticker:data:{symbol}")
        
        if cached_data:
            return JSONResponse(content=eval(cached_data))
        
        # Si no está en caché, obtener de TimescaleDB
        query = """
            SELECT 
                symbol,
                price,
                change_percent,
                volume,
                market_cap,
                free_float,
                free_float_percent,
                avg_volume_30d,
                timestamp
            FROM ticker_metadata
            WHERE symbol = $1
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        result = await timescale_client.fetchrow(query, symbol)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Ticker {symbol} not found")
        
        ticker_data = dict(result)
        
        # Guardar en caché (5 segundos)
        await redis_client.setex(
            f"ticker:data:{symbol}",
            5,
            str(ticker_data)
        )
        
        return ticker_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ticker_details_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/metadata/search")
async def search_tickers(
    q: str = Query(..., description="Search query", min_length=1),
    limit: int = Query(10, ge=1, le=50, description="Max results")
):
    """
    Proxy para búsqueda de tickers (ticker-metadata-service)
    
    Args:
        q: Query string (symbol o company name)
        limit: Máximo de resultados
    
    Returns:
        Lista de tickers que coinciden con la búsqueda
    """
    try:
        # Usa cliente con connection pooling para baja latencia
        return await http_clients.ticker_metadata.search(q, limit)
    
    except httpx.TimeoutException:
        logger.error("metadata_search_timeout", query=q)
        raise HTTPException(status_code=504, detail="Search timeout")
    except httpx.ConnectError:
        logger.error("metadata_search_unavailable", query=q)
        raise HTTPException(status_code=503, detail="Metadata service unavailable")
    except httpx.HTTPStatusError as e:
        logger.error("metadata_search_error", query=q, status=e.response.status_code)
        raise HTTPException(status_code=e.response.status_code, detail=f"Search failed")
    except Exception as e:
        logger.error("metadata_search_error", query=q, error=str(e))
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.get("/api/v1/ticker/{symbol}/metadata")
async def get_ticker_metadata(symbol: str):
    """
    Obtiene los metadatos completos de la compañía (sector, industria, exchange, etc.)
    
    Args:
        symbol: Símbolo del ticker (ej: AAPL)
    
    Returns:
        Metadatos completos de la compañía
    """
    try:
        symbol = symbol.upper()
        
        # Intentar obtener de ticker-metadata-service (usa connection pooling)
        try:
            metadata = await http_clients.ticker_metadata.get_metadata(symbol)
            if metadata:
                logger.info("metadata_service_success", symbol=symbol)
                return metadata
            else:
                logger.info("metadata_service_404_using_fallback", symbol=symbol)
        except httpx.TimeoutException:
            logger.warning("metadata_service_timeout", symbol=symbol)
        except httpx.ConnectError:
            logger.warning("metadata_service_unavailable", symbol=symbol)
        except Exception as e:
            logger.warning("metadata_service_error", symbol=symbol, error=str(e))
        
        # Fallback: Query directo a DB (modo degradado)
        logger.info("using_fallback_db_query", symbol=symbol)
        
        query = """
            SELECT 
                symbol, company_name, exchange, sector, industry,
                market_cap, free_float, free_float_percent, shares_outstanding,
                avg_volume_30d, avg_volume_10d, avg_price_30d, beta,
                description, homepage_url, phone_number, address,
                total_employees, list_date,
                logo_url, icon_url,
                cik, composite_figi, share_class_figi, ticker_root, ticker_suffix,
                type, currency_name, locale, market, round_lot, delisted_utc,
                is_etf, is_actively_trading, updated_at
            FROM ticker_metadata
            WHERE symbol = $1
        """
        
        result = await timescale_client.fetchrow(query, symbol)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Metadata for {symbol} not found")
        
        metadata = dict(result)
        
        # Convertir datetime a string para JSON
        if metadata.get('updated_at'):
            metadata['updated_at'] = metadata['updated_at'].isoformat()
        
        return metadata
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("ticker_metadata_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/proxy/logo")
async def proxy_logo(url: str):
    """
    Proxy para logos de Polygon.io con API key
    
    Args:
        url: URL del logo sin API key
    
    Returns:
        StreamingResponse con la imagen
    """
    try:
        # Usar cliente Polygon para proxy de logo
        response = await http_clients.polygon.proxy_logo(url)
        
        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Logo not found")
        
        # Devolver la imagen como stream
        return StreamingResponse(
            iter([response.content]),
            media_type=response.headers.get("content-type", "image/svg+xml"),
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache 24h
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("logo_proxy_error", url=url, error=str(e))
        raise HTTPException(status_code=500, detail="Error fetching logo")


# ============================================================================
# Ticker Description Endpoint
# ============================================================================

@app.get("/api/v1/ticker/{symbol}/description")
async def get_ticker_description(
    symbol: str,
    force_refresh: bool = Query(default=False, description="Force refresh from API")
):
    """
    Get comprehensive ticker description combining:
    - Company info (metadata)
    - Market stats (profile)
    - Valuation ratios
    - Dividend info
    - Analyst ratings & price targets
    
    Caches for 5 minutes.
    """
    global redis_client
    
    symbol = symbol.upper()
    cache_key = f"description:{symbol}"
    cache_ttl = 300  # 5 minutes
    
    try:
        # Check cache first
        if not force_refresh and redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("description_cache_hit", symbol=symbol)
                return cached
        
        # Usar clientes HTTP con connection pooling
        # 1. Get metadata from Redis (already cached)
        metadata = None
        if redis_client:
            metadata = await redis_client.get(f"metadata:ticker:{symbol}")
        
        # 2. Fetch FMP profile (for price, beta, CEO, etc)
        profile_list = await http_clients.fmp.get_profile(symbol)
        profile_data = profile_list[0] if profile_list else {}
        
        # 3. Fetch FMP ratios
        ratios_list = await http_clients.fmp.get_ratios(symbol, limit=1)
        ratios_data = ratios_list[0] if ratios_list else {}
        
        # 4. Fetch analyst recommendations
        analyst_list = await http_clients.fmp.get_analyst_recommendations(symbol)
        analyst_data = analyst_list[0] if analyst_list else {}
        
        # 5. Fetch price targets (limit 10)
        targets_list = await http_clients.fmp.get_price_targets(symbol)
        targets_data = targets_list[:10] if targets_list else []
        
        # 6. Detect SPAC/de-SPAC status (async, cached for company lifecycle)
        spac_info = {"is_spac": False, "is_de_spac": False, "sic_code": None}
        try:
            if http_clients.sec_edgar:
                spac_result = await http_clients.sec_edgar.detect_spac(
                    symbol, 
                    http_clients.sec_api if hasattr(http_clients, 'sec_api') else None
                )
                spac_info = {
                    "is_spac": spac_result.get("is_spac", False),
                    "is_de_spac": spac_result.get("is_de_spac", False),
                    "sic_code": spac_result.get("sic_code"),
                    "former_spac_name": spac_result.get("former_spac_name"),
                    "merger_date": spac_result.get("merger_date")
                }
                if spac_info["is_spac"]:
                    logger.info("spac_detected", symbol=symbol, confidence=spac_result.get("confidence"))
                if spac_info["is_de_spac"]:
                    logger.info("de_spac_detected", symbol=symbol, former_name=spac_info.get("former_spac_name"))
                # Debug log para verificar detección
                logger.debug("spac_detection_result", symbol=symbol, spac_info=spac_info)
        except Exception as e:
            logger.debug("spac_detection_skipped", symbol=symbol, error=str(e))
        
        # Build company info
        company = CompanyInfo(
            symbol=symbol,
            name=profile_data.get("companyName") or (metadata.get("company_name") if metadata else symbol),
            exchange=profile_data.get("exchange") or (metadata.get("exchange") if metadata else None),
            exchangeFullName=profile_data.get("exchangeFullName"),
            sector=profile_data.get("sector") or (metadata.get("sector") if metadata else None),
            industry=profile_data.get("industry") or (metadata.get("industry") if metadata else None),
            is_spac=spac_info.get("is_spac"),
            is_de_spac=spac_info.get("is_de_spac"),
            former_spac_name=spac_info.get("former_spac_name"),
            merger_date=spac_info.get("merger_date"),
            sic_code=spac_info.get("sic_code"),
            description=profile_data.get("description") or (metadata.get("description") if metadata else None),
            ceo=profile_data.get("ceo"),
            website=profile_data.get("website") or (metadata.get("homepage_url") if metadata else None),
            address=profile_data.get("address"),
            city=profile_data.get("city"),
            state=profile_data.get("state"),
            country=profile_data.get("country"),
            phone=profile_data.get("phone") or (metadata.get("phone_number") if metadata else None),
            employees=int(profile_data.get("fullTimeEmployees") or 0) if profile_data.get("fullTimeEmployees") else (metadata.get("total_employees") if metadata else None),
            ipoDate=profile_data.get("ipoDate") or (metadata.get("list_date") if metadata else None),
            logoUrl=profile_data.get("image") or (metadata.get("logo_url") if metadata else None),
            iconUrl=metadata.get("icon_url") if metadata else None,
        )
        
        # Build market stats
        stats = MarketStats(
            price=profile_data.get("price"),
            change=profile_data.get("change"),
            changePercent=profile_data.get("changePercentage"),
            volume=profile_data.get("volume"),
            avgVolume=profile_data.get("averageVolume") or (metadata.get("avg_volume_30d") if metadata else None),
            marketCap=profile_data.get("marketCap") or (metadata.get("market_cap") if metadata else None),
            sharesOutstanding=metadata.get("shares_outstanding") if metadata else None,
            freeFloat=metadata.get("free_float") if metadata else None,
            freeFloatPercent=metadata.get("free_float_percent") if metadata else None,
            dayLow=None,  # Not in stable/profile
            dayHigh=None,
            yearLow=float(profile_data.get("range", "0-0").split("-")[0]) if profile_data.get("range") else None,
            yearHigh=float(profile_data.get("range", "0-0").split("-")[1]) if profile_data.get("range") else None,
            range52Week=profile_data.get("range"),
            beta=profile_data.get("beta"),
        )
        
        # Build valuation metrics
        valuation = ValuationMetrics(
            peRatio=ratios_data.get("priceToEarningsRatio"),
            forwardPE=None,  # Need separate endpoint
            pegRatio=ratios_data.get("priceToEarningsGrowthRatio"),
            pbRatio=ratios_data.get("priceToBookRatio"),
            psRatio=ratios_data.get("priceToSalesRatio"),
            evToEbitda=ratios_data.get("enterpriseValueMultiple"),
            evToRevenue=None,
            enterpriseValue=None,
        )
        
        # Build dividend info
        dividend = DividendInfo(
            trailingYield=ratios_data.get("dividendYieldPercentage"),
            forwardYield=None,
            payoutRatio=ratios_data.get("dividendPayoutRatio"),
            dividendPerShare=ratios_data.get("dividendPerShare") or profile_data.get("lastDividend"),
            exDividendDate=None,
            dividendDate=None,
            fiveYearAvgYield=None,
        )
        
        # Build risk metrics
        risk = RiskMetrics(
            beta=profile_data.get("beta"),
            shortInterest=None,  # Need separate endpoint
            shortRatio=None,
            shortPercentFloat=None,
        )
        
        # Build analyst rating
        analyst_rating = None
        if analyst_data:
            analyst_rating = AnalystRating(
                symbol=symbol,
                date=analyst_data.get("date"),
                analystRatingsbuy=analyst_data.get("analystRatingsbuy"),
                analystRatingsHold=analyst_data.get("analystRatingsHold"),
                analystRatingsSell=analyst_data.get("analystRatingsSell"),
                analystRatingsStrongSell=analyst_data.get("analystRatingsStrongSell"),
                analystRatingsStrongBuy=analyst_data.get("analystRatingsStrongBuy"),
            )
        
        # Build price targets
        price_targets = [
            PriceTarget(
                symbol=symbol,
                publishedDate=t.get("publishedDate"),
                analystName=t.get("analystName"),
                analystCompany=t.get("analystCompany"),
                priceTarget=t.get("priceTarget"),
                adjPriceTarget=t.get("adjPriceTarget"),
                priceWhenPosted=t.get("priceWhenPosted"),
                newsTitle=t.get("newsTitle"),
                newsURL=t.get("newsURL"),
                newsPublisher=t.get("newsPublisher"),
            )
            for t in targets_data
        ]
        
        # Calculate consensus target
        consensus_target = None
        target_upside = None
        if price_targets:
            valid_targets = [t.priceTarget for t in price_targets if t.priceTarget]
            if valid_targets:
                consensus_target = sum(valid_targets) / len(valid_targets)
                if stats.price and consensus_target:
                    target_upside = ((consensus_target - stats.price) / stats.price) * 100
        
        # Build complete description
        description = TickerDescription(
            symbol=symbol,
            company=company,
            stats=stats,
            valuation=valuation,
            dividend=dividend,
            risk=risk,
            analystRating=analyst_rating,
            priceTargets=price_targets,
            consensusTarget=round(consensus_target, 2) if consensus_target else None,
            targetUpside=round(target_upside, 2) if target_upside else None,
        )
        
        result = description.model_dump()
        
        # Cache result
        if redis_client:
            await redis_client.set(cache_key, result, ttl=cache_ttl)
            logger.info("description_cached", symbol=symbol)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("description_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def _get_index_snapshot_response(symbol: str) -> JSONResponse:
    """
    Snapshot estilo Polygon para un índice, construido desde
    snapshot:indices:latest (fmp_indices). Un índice no tiene NBBO: se
    publica bid = ask = valor del índice (mid exacto, spread 0).
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    raw = await redis_client.client.hget("snapshot:indices:latest", symbol)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Index {symbol} snapshot not available")
    q = _json.loads(raw)
    price = q.get("price") or 0
    ts_ms = int(q.get("updated_at") or 0)
    ts_ns = ts_ms * 1_000_000
    prev_close = q.get("previous_close") or 0
    ticker = {
        "ticker": symbol,
        "todaysChange": q.get("change") or 0,
        "todaysChangePerc": q.get("change_percent") or 0,
        "updated": ts_ns,
        "day": {
            "o": q.get("open") or 0, "h": q.get("day_high") or 0,
            "l": q.get("day_low") or 0, "c": price,
            "v": q.get("volume") or 0, "vw": price,
        },
        "prevDay": {"o": 0, "h": 0, "l": 0, "c": prev_close, "v": 0, "vw": 0},
        "lastQuote": {"p": price, "P": price, "s": 0, "S": 0, "t": ts_ns},
        "lastTrade": {"p": price, "s": 0, "t": ts_ns, "c": [], "i": "", "x": 0},
        "min": {
            "av": q.get("volume") or 0, "o": price, "h": price,
            "l": price, "c": price, "v": 0, "t": ts_ms,
        },
    }
    return JSONResponse(content={"status": "OK", "ticker": ticker})


@app.get("/api/v1/ticker/{symbol}/snapshot", response_model=PolygonSingleTickerSnapshotResponse)
async def get_ticker_snapshot(
    symbol: str,
    force_refresh: bool = Query(default=False, description="Force refresh from API")
):
    """
    Get the most recent market data snapshot for a single ticker from Polygon.
    
    This endpoint consolidates the latest trade, quote, and aggregated data
    (minute, day, and previous day) for the specified ticker.
    
    Snapshot data is cleared at 3:30 AM EST and begins updating as exchanges
    report new information, which can start as early as 4:00 AM EST.
    
    Use Cases: 
    - Fallback when WebSocket quotes are not available
    - Focused monitoring, real-time analysis, price alerts
    
    Caches for 5 minutes (300 seconds) to reduce API calls.
    """
    global redis_client
    symbol = symbol.upper()

    # Índices (SPX, VIX, ^GDAXI...): snapshot sintetizado desde el hash de
    # fmp_indices con la MISMA forma que el snapshot de Polygon, para que
    # useRealtimeQuote/QuoteMonitor no distingan fuentes.
    index_snap_symbol = normalize_index_symbol(symbol)
    if index_snap_symbol:
        return await _get_index_snapshot_response(index_snap_symbol)

    cache_key = f"ticker_snapshot:{symbol}"
    cache_ttl = 300  # 5 minutes
    
    try:
        if not force_refresh and redis_client:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                logger.debug("ticker_snapshot_cache_hit", symbol=symbol)
                return cached_data
        
        # Usar cliente Polygon con connection pooling
        data = await http_clients.polygon.get_snapshot(symbol)
        
        # Validate response structure
        if data.get("status") != "OK":
            raise HTTPException(
                status_code=404, 
                detail=f"Snapshot not available for {symbol}: {data.get('status')}"
            )
        
        # Parse response with Pydantic model
        snapshot_response = PolygonSingleTickerSnapshotResponse(**data)
        
        # Cache the response
        if redis_client:
            await redis_client.set(cache_key, snapshot_response.model_dump(), ttl=cache_ttl)
            logger.info("ticker_snapshot_cached", symbol=symbol)
        
        return snapshot_response
            
    except httpx.HTTPStatusError as e:
        logger.error("ticker_snapshot_http_error", symbol=symbol, error=str(e), status_code=e.response.status_code)
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Snapshot not found for {symbol}")
        raise HTTPException(status_code=e.response.status_code, detail=f"API error: {e.response.text}")
    except Exception as e:
        logger.error("ticker_snapshot_fetch_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch snapshot: {str(e)}")


@app.get("/api/v1/ticker/{symbol}/prev-close")
async def get_ticker_prev_close(
    symbol: str,
    user: AuthenticatedUser = Depends(get_current_user)  # 🔒 Requiere auth
):
    """
    Get previous day's close price for a ticker (lightweight endpoint).
    
    Returns only the prev_close value from the snapshot, useful for calculating
    change percentages without fetching the full snapshot.
    """
    global redis_client
    symbol = symbol.upper()

    # Índices: previous_close desde el hash de fmp_indices
    index_pc_symbol = normalize_index_symbol(symbol)
    if index_pc_symbol:
        if not redis_client:
            raise HTTPException(status_code=503, detail="Redis not available")
        raw = await redis_client.client.hget("snapshot:indices:latest", index_pc_symbol)
        if raw:
            pc = _json.loads(raw).get("previous_close")
            if pc:
                return {"symbol": index_pc_symbol, "close": pc, "c": pc, "cached": False}
        raise HTTPException(status_code=404, detail=f"Previous close not available for {index_pc_symbol}")

    cache_key = f"ticker_prev_close:{symbol}"
    cache_ttl = 3600  # 1 hora (prev_close no cambia durante el día)
    
    try:
        # Check cache first
        if redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                return {"symbol": symbol, "close": float(cached), "c": float(cached), "cached": True}
        
        # Fetch snapshot (usa cache interno del snapshot endpoint)
        snapshot_data = await http_clients.polygon.get_snapshot(symbol)
        
        if snapshot_data.get("status") != "OK":
            raise HTTPException(status_code=404, detail=f"Ticker {symbol} not found")
        
        # Extract prevDay close
        ticker_data = snapshot_data.get("ticker", {})
        prev_day = ticker_data.get("prevDay", {})
        prev_close = prev_day.get("c")  # Close price
        
        if prev_close is None:
            raise HTTPException(status_code=404, detail=f"Previous close not available for {symbol}")
        
        # Cache the result
        if redis_client:
            await redis_client.set(cache_key, str(prev_close), ttl=cache_ttl)
        
        return {
            "symbol": symbol,
            "close": prev_close,
            "c": prev_close,
            "cached": False
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching prev_close for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rvol/{symbol}")
async def get_ticker_rvol(symbol: str):
    """
    Obtiene el RVOL actual de un ticker
    
    Args:
        symbol: Símbolo del ticker
    
    Returns:
        RVOL del ticker con información del slot
    """
    try:
        symbol = symbol.upper()
        
        # Obtener RVOL del Analytics Service
        # (podríamos hacer una llamada HTTP o leer de Redis)
        rvol_data = await redis_client.get(f"rvol:{symbol}")
        
        if not rvol_data:
            raise HTTPException(status_code=404, detail=f"RVOL data not available for {symbol}")
        
        return JSONResponse(content=eval(rvol_data))
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("rvol_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/history/scans")
async def get_scan_history(
    date: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Obtiene histórico de scans para backtesting
    
    Args:
        date: Fecha en formato YYYY-MM-DD (opcional)
        limit: Número máximo de resultados
    
    Returns:
        Histórico de scans
    """
    try:
        if date:
            query = """
                SELECT 
                    scan_id,
                    symbol,
                    price,
                    volume,
                    rvol,
                    change_percent,
                    market_cap,
                    scan_timestamp
                FROM scan_results
                WHERE DATE(scan_timestamp) = $1
                ORDER BY scan_timestamp DESC
                LIMIT $2
            """
            results = await timescale_client.fetch(query, date, limit)
        else:
            query = """
                SELECT 
                    scan_id,
                    symbol,
                    price,
                    volume,
                    rvol,
                    change_percent,
                    market_cap,
                    scan_timestamp
                FROM scan_results
                ORDER BY scan_timestamp DESC
                LIMIT $1
            """
            results = await timescale_client.fetch(query, limit)
        
        scans = [dict(row) for row in results]
        
        return {
            "scans": scans,
            "count": len(scans),
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error("scan_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats")
async def get_system_stats():
    """Obtiene estadísticas del sistema completo"""
    try:
        stats = {
            "api_gateway": {
                "websocket_connections": connection_manager.stats["active_connections"],
                "messages_sent": connection_manager.stats["messages_sent"],
                "errors": connection_manager.stats["errors"]
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return stats
    
    except Exception as e:
        logger.error("system_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Benzinga News Proxy
# ============================================================================

@app.get("/news/api/v1/news")
async def proxy_news(
    ticker: Optional[str] = Query(None, description="Filter by ticker symbol"),
    channels: Optional[str] = Query(None, description="Filter by channels"),
    tags: Optional[str] = Query(None, description="Filter by tags"),
    author: Optional[str] = Query(None, description="Filter by author"),
    limit: int = Query(50, ge=1, le=2000, description="Limit results"),
    offset: int = Query(0, ge=0, le=5000, description="Offset for pagination")
):
    """
    Proxy para el servicio de News (Benzinga y futuras fuentes)
    """
    try:
        # Usar cliente con connection pooling
        return await http_clients.benzinga_news.get_news(
            ticker=ticker,
            channels=channels,
            tags=tags,
            author=author,
            limit=limit,
            offset=offset
        )
    
    except httpx.TimeoutException:
        logger.error("news_service_timeout")
        raise HTTPException(status_code=504, detail="News service timeout")
    except httpx.ConnectError:
        logger.error("news_service_unavailable")
        raise HTTPException(status_code=503, detail="News service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Benzinga news service error")
    except Exception as e:
        logger.error("news_service_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/latest")
async def proxy_news_latest(limit: int = Query(50, ge=1, le=200)):
    """Proxy para las últimas noticias"""
    try:
        # Usar cliente con connection pooling
        return await http_clients.benzinga_news.get_latest(limit)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Service error")
    except Exception as e:
        logger.error("benzinga_latest_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/top")
async def proxy_news_top(
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0, le=300)
):
    """Proxy para Top News (Reuters) del servicio fmp-news"""
    try:
        # Usar cliente con connection pooling
        return await http_clients.fmp_news.get_top_news(limit, offset)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Service error")
    except Exception as e:
        logger.error("news_top_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/ticker/{ticker}")
async def proxy_news_by_ticker(ticker: str, limit: int = Query(50, ge=1, le=200)):
    """Proxy para noticias por ticker"""
    try:
        # Usar cliente con connection pooling
        return await http_clients.benzinga_news.get_by_ticker(ticker, limit)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Service error")
    except Exception as e:
        logger.error("news_ticker_error", error=str(e), ticker=ticker)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/history")
async def proxy_news_history(request: Request):
    """
    Búsqueda del histórico unificado de noticias (news-persister → TimescaleDB).
    Full-text (q) + tickers + sources + publisher + channels + tags + fechas,
    con paginación por cursor (before/before_id).
    Sustituye al viejo /news/search, que solo cubría Benzinga e ignoraba fechas.
    """
    try:
        params = dict(request.query_params)
        return await http_clients.news_persister.search_history(params)
    except httpx.TimeoutException:
        logger.error("news_history_timeout")
        raise HTTPException(status_code=504, detail="News history service timeout")
    except httpx.ConnectError:
        logger.error("news_history_unavailable")
        raise HTTPException(status_code=503, detail="News history service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="News history service error")
    except Exception as e:
        logger.error("news_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/news/api/v1/news/extract")
async def proxy_news_extract(url: str = Query(..., description="URL del artículo a extraer")):
    """
    Lector nativo: extracción server-side del cuerpo del artículo
    (news-persister → trafilatura, con cache). El frontend lo renderiza con
    su propia tipografía — sin iframes.
    """
    try:
        return await http_clients.news_persister.extract_article(url)
    except httpx.TimeoutException:
        logger.error("news_extract_timeout")
        raise HTTPException(status_code=504, detail="News extract timeout")
    except httpx.ConnectError:
        logger.error("news_extract_unavailable")
        raise HTTPException(status_code=503, detail="News extract unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="News extract error")
    except Exception as e:
        logger.error("news_extract_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/proxy/news")
async def proxy_news_article(url: str = Query(..., description="News article URL to proxy")):
    """
    Proxy para cargar artículos de noticias sin restricciones de CORS/X-Frame-Options
    
    Esto permite mostrar artículos en iframe dentro de la app.
    Similar al sistema de SEC filings.
    """
    # Validar dominios permitidos
    allowed_domains = [
        "benzinga.com",
        "www.benzinga.com",
        "seekingalpha.com",
        "www.seekingalpha.com",
        "reuters.com",
        "www.reuters.com",
        "bloomberg.com",
        "www.bloomberg.com",
        "marketwatch.com",
        "www.marketwatch.com",
        "cnbc.com",
        "www.cnbc.com",
        "yahoo.com",
        "finance.yahoo.com",
    ]
    
    from urllib.parse import urlparse
    parsed = urlparse(url)
    
    if not any(parsed.netloc.endswith(domain) for domain in allowed_domains):
        raise HTTPException(
            status_code=400,
            detail=f"Domain not allowed: {parsed.netloc}. Only approved news domains are permitted."
        )
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
            })
            response.raise_for_status()
            
            # Devolver el HTML sin headers restrictivos
            return HTMLResponse(
                content=response.text,
                status_code=200,
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "X-Content-Type-Options": "nosniff"
                }
            )
    
    except httpx.HTTPError as e:
        logger.error("news_proxy_http_error", url=url, error=str(e))
        raise HTTPException(
            status_code=502,
            detail=f"Error fetching news article: {str(e)}"
        )
    except Exception as e:
        logger.error("news_proxy_error", url=url, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Proxy error: {str(e)}"
        )


# ============================================================================
# Prediction Markets Proxy
# ============================================================================

PREDICTION_MARKETS_URL = os.getenv("PREDICTION_MARKETS_URL", "http://prediction-markets:8021")

@app.get("/api/v1/predictions")
async def proxy_predictions(
    category: Optional[str] = Query(None, description="Filter by category"),
    refresh: bool = Query(False, description="Force refresh from source"),
):
    """
    Proxy para el servicio de Prediction Markets (Polymarket)
    Retorna datos de mercados de prediccion organizados por categoria
    """
    try:
        params = {}
        if category:
            params["category"] = category
        if refresh:
            params["refresh"] = "true"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PREDICTION_MARKETS_URL}/api/v1/predictions",
                params=params
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Prediction Markets request timed out")
    except Exception as e:
        logger.error("predictions_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/events")
async def proxy_predictions_events(
    category: Optional[str] = Query(None, description="Filter by category"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    min_volume: Optional[float] = Query(None, description="Minimum total volume"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Page size"),
):
    """Proxy para lista de eventos de prediction markets"""
    try:
        params = {"page": page, "page_size": page_size}
        if category:
            params["category"] = category
        if subcategory:
            params["subcategory"] = subcategory
        if min_volume:
            params["min_volume"] = min_volume
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PREDICTION_MARKETS_URL}/api/v1/predictions/events",
                params=params
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("predictions_events_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/categories")
async def proxy_predictions_categories():
    """Proxy para lista de categorias disponibles"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PREDICTION_MARKETS_URL}/api/v1/predictions/categories")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("predictions_categories_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/event/{event_id}")
async def proxy_predictions_event(event_id: str):
    """Proxy para obtener un evento especifico por ID"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PREDICTION_MARKETS_URL}/api/v1/predictions/event/{event_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
        raise HTTPException(status_code=502, detail="Prediction Markets service error")
    except Exception as e:
        logger.error("predictions_event_proxy_error", event_id=event_id, error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/series")
async def proxy_predictions_series(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Proxy para obtener series de eventos"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{PREDICTION_MARKETS_URL}/api/v1/predictions/series",
                params={"limit": limit, "offset": offset}
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("predictions_series_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/series/{series_id}")
async def proxy_predictions_series_detail(series_id: str):
    """Proxy para obtener una serie especifica"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PREDICTION_MARKETS_URL}/api/v1/predictions/series/{series_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Series {series_id} not found")
        raise HTTPException(status_code=502, detail="Prediction Markets service error")
    except Exception as e:
        logger.error("predictions_series_detail_proxy_error", series_id=series_id, error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/comments/{event_id}")
async def proxy_predictions_comments(
    event_id: str,
    limit: int = Query(30, ge=1, le=100),
):
    """Proxy para obtener comentarios de un evento"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{PREDICTION_MARKETS_URL}/api/v1/predictions/comments/{event_id}",
                params={"limit": limit}
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("predictions_comments_proxy_error", event_id=event_id, error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/top-holders/{market_id}")
async def proxy_predictions_top_holders(
    market_id: str,
    limit: int = Query(10, ge=1, le=50),
):
    """Proxy para obtener top holders de un mercado"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{PREDICTION_MARKETS_URL}/api/v1/predictions/top-holders/{market_id}",
                params={"limit": limit}
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("predictions_top_holders_proxy_error", market_id=market_id, error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/volume/{event_id}")
async def proxy_predictions_volume(event_id: str):
    """Proxy para obtener volumen en vivo de un evento"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PREDICTION_MARKETS_URL}/api/v1/predictions/volume/{event_id}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("predictions_volume_proxy_error", event_id=event_id, error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/ticker/{ticker}")
async def proxy_predictions_ticker_search(
    ticker: str,
    limit: int = Query(20, ge=1, le=50),
):
    """Proxy para buscar predicciones relacionadas a un ticker especifico"""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{PREDICTION_MARKETS_URL}/api/v1/predictions/ticker/{ticker}",
                params={"limit": limit}
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"ticker": ticker.upper(), "events": [], "total": 0}
        raise HTTPException(status_code=502, detail="Prediction Markets service error")
    except Exception as e:
        logger.error("predictions_ticker_search_proxy_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


@app.get("/api/v1/predictions/event/{event_id}/detail")
async def proxy_predictions_event_detail(event_id: str):
    """Proxy para obtener detalle completo de un evento con comentarios y sparklines"""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{PREDICTION_MARKETS_URL}/api/v1/predictions/event/{event_id}/detail")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
        raise HTTPException(status_code=502, detail="Prediction Markets service error")
    except Exception as e:
        logger.error("predictions_event_detail_proxy_error", event_id=event_id, error=str(e))
        raise HTTPException(status_code=502, detail="Prediction Markets service unavailable")


# ============================================================================
# Pattern Matching Proxy
# ============================================================================

# Pattern Matching runs on dedicated server (37.27.183.194)
# Firewall allows only this server's IP
import os
PATTERN_MATCHING_URL = os.getenv("PATTERN_MATCHING_URL", "http://37.27.183.194:8025")

@app.get("/patterns/health")
async def proxy_patterns_health():
    """Proxy para health check del servicio Pattern Matching"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{PATTERN_MATCHING_URL}/health")
            return response.json()
    except Exception as e:
        logger.error("patterns_proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail="Pattern Matching service unavailable")

@app.get("/patterns/api/index/stats")
async def proxy_patterns_index_stats():
    """Proxy para stats del índice FAISS"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PATTERN_MATCHING_URL}/api/index/stats")
            return response.json()
    except Exception as e:
        logger.error("patterns_proxy_error", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=502, detail="Pattern Matching service unavailable")

@app.get("/patterns/api/search/{symbol}")
async def proxy_patterns_search(
    symbol: str,
    k: int = Query(30, ge=1, le=200),
    cross_asset: bool = Query(True)
):
    """Proxy para búsqueda de patrones similares"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PATTERN_MATCHING_URL}/api/search/{symbol}",
                params={"k": k, "cross_asset": cross_asset}
            )
            return response.json()
    except Exception as e:
        logger.error("patterns_search_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail="Pattern search failed")


@app.post("/patterns/api/search/historical")
async def proxy_patterns_search_historical(request: Request):
    """Proxy para búsqueda histórica de patrones - funciona sin mercado abierto"""
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{PATTERN_MATCHING_URL}/api/search/historical",
                json=body
            )
            if response.status_code != 200:
                logger.error("patterns_historical_upstream_error", status=response.status_code, text=response.text[:200])
                raise HTTPException(status_code=response.status_code, detail=response.text[:500])
            return Response(content=response.content, media_type="application/json")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("patterns_historical_search_error", error=str(e), error_type=type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Historical pattern search failed: {type(e).__name__}")


@app.get("/patterns/api/historical/prices/{symbol}")
async def proxy_patterns_historical_prices(
    symbol: str,
    date: str = Query(...),
    start_time: str = Query("09:30"),
    end_time: str = Query("16:00")
):
    """Proxy para obtener precios históricos de flat files"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{PATTERN_MATCHING_URL}/api/historical/prices/{symbol}",
                params={"date": date, "start_time": start_time, "end_time": end_time}
            )
            return response.json()
    except Exception as e:
        logger.error("patterns_historical_prices_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch historical prices")


PATTERNS_DATES_CACHE_KEY = "cache:patterns:available_dates"
PATTERNS_DATES_CACHE_TTL = 3600  # 1 hour - dates don't change often

@app.get("/patterns/api/available-dates")
async def proxy_patterns_available_dates(force_refresh: bool = Query(False)):
    """Proxy para obtener fechas disponibles en los flat files (cached)"""
    # Try cache first (fast path)
    if not force_refresh:
        try:
            cached = await redis_client.get(PATTERNS_DATES_CACHE_KEY)
            if cached:
                import json
                return json.loads(cached)
        except Exception:
            pass  # Cache miss or error, continue to fetch
    
    # Fetch from service
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PATTERN_MATCHING_URL}/api/available-dates")
            data = response.json()
            
            # Cache the result
            try:
                import json
                await redis_client.setex(PATTERNS_DATES_CACHE_KEY, PATTERNS_DATES_CACHE_TTL, json.dumps(data))
            except Exception:
                pass  # Don't fail if cache write fails
            
            return data
    except Exception as e:
        # Try to return stale cache on error
        try:
            cached = await redis_client.get(PATTERNS_DATES_CACHE_KEY)
            if cached:
                import json
                logger.warning("patterns_available_dates_stale_cache", error=str(e))
                return json.loads(cached)
        except Exception:
            pass
        
        logger.error("patterns_available_dates_error", error=str(e))
        raise HTTPException(status_code=502, detail="Failed to fetch available dates")


# ============================================================================
# Pattern Real-Time Proxy (new module for batch scanning)
# ============================================================================

@app.api_route("/patterns/api/pattern-realtime/{path:path}", methods=["GET", "POST", "DELETE"])
async def proxy_pattern_realtime(path: str, request: Request):
    """
    Proxy genérico para todos los endpoints de Pattern Real-Time.
    Endpoints incluyen: /run, /job/{id}, /performance, /stats, etc.
    """
    try:
        target_url = f"{PATTERN_MATCHING_URL}/api/pattern-realtime/{path}"
        
        # Build query string
        if request.query_params:
            target_url += f"?{request.query_params}"
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            if request.method == "GET":
                response = await client.get(target_url)
            elif request.method == "POST":
                body = await request.body()
                response = await client.post(
                    target_url,
                    content=body,
                    headers={"Content-Type": "application/json"}
                )
            elif request.method == "DELETE":
                response = await client.delete(target_url)
            else:
                raise HTTPException(status_code=405, detail="Method not allowed")
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type="application/json"
            )
    except httpx.TimeoutException:
        logger.error("pattern_realtime_timeout", path=path)
        raise HTTPException(status_code=504, detail="Pattern Real-Time request timed out")
    except Exception as e:
        logger.error("pattern_realtime_proxy_error", path=path, error=str(e))
        raise HTTPException(status_code=502, detail=f"Pattern Real-Time proxy error: {str(e)}")


# WebSocket proxy for Pattern Real-Time
@app.websocket("/patterns/ws/pattern-realtime")
async def proxy_pattern_realtime_ws(websocket: WebSocket):
    """
    WebSocket proxy para Pattern Real-Time.
    Conecta el cliente frontend con el backend de Pattern Matching.
    """
    await websocket.accept()
    
    backend_ws = None
    try:
        # Conectar al backend
        backend_url = f"ws://37.27.183.194:8025/ws/pattern-realtime"
        
        import websockets
        backend_ws = await websockets.connect(backend_url, ping_interval=30)
        
        async def forward_to_backend():
            try:
                while True:
                    data = await websocket.receive_text()
                    await backend_ws.send(data)
            except Exception:
                pass
        
        async def forward_to_frontend():
            try:
                async for message in backend_ws:
                    await websocket.send_text(message)
            except Exception:
                pass
        
        # Run both directions concurrently
        import asyncio
        await asyncio.gather(
            forward_to_backend(),
            forward_to_frontend(),
            return_exceptions=True
        )
        
    except Exception as e:
        logger.error("pattern_realtime_ws_error", error=str(e))
    finally:
        if backend_ws:
            await backend_ws.close()
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# Earnings Calendar Endpoints
# ============================================================================

@app.get("/api/v1/earnings/calendar")
async def get_earnings_calendar(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (default: today)"),
    status: Optional[str] = Query(None, description="Filter by status: scheduled, reported"),
    time_slot: Optional[str] = Query(None, description="Filter by time: BMO, AMC"),
    min_importance: Optional[int] = Query(None, ge=0, le=5, description="Minimum importance (0-5)"),
    date_status: Optional[str] = Query(None, description="Filter by date_status: confirmed, projected"),
):
    """
    Get earnings calendar for a specific date.
    Returns both scheduled and reported earnings from Benzinga/Polygon API.
    
    Features:
    - importance: 0-5 score (5 = most important companies)
    - date_status: confirmed vs projected
    - eps_method/revenue_method: GAAP vs adjusted
    """
    from datetime import datetime, date as date_type
    
    try:
        # Parse date or use today (ET: entre 20:00-23:59 ET, UTC ya es mañana)
        if date:
            target_date = date_type.fromisoformat(date)
        else:
            target_date = datetime.now(tz=ET_TZ).date()
        
        # Try cache first
        cache_key = f"earnings:calendar:{target_date.isoformat()}"
        cached = await redis_client.get(cache_key)
        
        # Build query with all Benzinga fields
        query = """
            SELECT 
                symbol, company_name, report_date, time_slot, fiscal_quarter,
                eps_estimate, eps_actual, eps_surprise_pct, beat_eps,
                revenue_estimate, revenue_actual, revenue_surprise_pct, beat_revenue,
                guidance_direction, guidance_commentary, key_highlights,
                market_cap, sector, status, source,
                importance, date_status, eps_method, revenue_method,
                previous_eps, previous_revenue, benzinga_id, notes,
                created_at
            FROM earnings_calendar
            WHERE report_date = $1
        """
        params = [target_date]
        param_num = 1
        
        if status:
            param_num += 1
            query += f" AND status = ${param_num}"
            params.append(status)
        
        if time_slot:
            param_num += 1
            query += f" AND time_slot = ${param_num}"
            params.append(time_slot.upper())
        
        if min_importance is not None:
            param_num += 1
            query += f" AND importance >= ${param_num}"
            params.append(min_importance)
        
        if date_status:
            param_num += 1
            query += f" AND date_status = ${param_num}"
            params.append(date_status.lower())
        
        query += " ORDER BY COALESCE(importance, 0) DESC, time_slot, symbol"
        
        rows = await timescale_client.fetch(query, *params)
        
        # Process results
        reports = []
        total_bmo = 0
        total_amc = 0
        total_reported = 0
        total_scheduled = 0
        total_confirmed = 0
        total_projected = 0
        
        for row in rows:
            report = dict(row)
            # Convert date to string
            if report.get('report_date'):
                report['report_date'] = str(report['report_date'])
            if report.get('created_at'):
                report['created_at'] = str(report['created_at'])
            
            reports.append(report)
            
            # Count stats
            if report.get('time_slot') == 'BMO':
                total_bmo += 1
            elif report.get('time_slot') == 'AMC':
                total_amc += 1
            
            if report.get('status') == 'reported':
                total_reported += 1
            else:
                total_scheduled += 1
            
            if report.get('date_status') == 'confirmed':
                total_confirmed += 1
            else:
                total_projected += 1
        
        result = {
            "date": str(target_date),
            "reports": reports,
            "total_count": len(reports),
            "total_bmo": total_bmo,
            "total_amc": total_amc,
            "total_reported": total_reported,
            "total_scheduled": total_scheduled,
            "total_confirmed": total_confirmed,
            "total_projected": total_projected
        }
        
        # Cache for 5 minutes
        try:
            await redis_client.set(cache_key, result, ttl=300)
        except Exception:
            pass
        
        return result
        
    except Exception as e:
        logger.error(f"earnings_calendar_error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/earnings/upcoming")
async def get_upcoming_earnings(
    days: int = Query(14, ge=1, le=30, description="Days ahead to look"),
    min_importance: Optional[int] = Query(None, ge=0, le=5, description="Minimum importance (0-5)"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
):
    """
    Get upcoming earnings for the next N days.
    Sorted by date and importance.
    """
    from datetime import datetime, date as date_type, timedelta
    
    try:
        today = datetime.now(tz=ET_TZ).date()
        end_date = today + timedelta(days=days)
        
        query = """
            SELECT 
                symbol, company_name, report_date, time_slot, fiscal_quarter,
                eps_estimate, revenue_estimate,
                importance, date_status, sector,
                status, source
            FROM earnings_calendar
            WHERE report_date >= $1 AND report_date <= $2
        """
        params = [today, end_date]
        
        if min_importance is not None:
            query += " AND importance >= $3"
            params.append(min_importance)
        
        query += " ORDER BY report_date ASC, COALESCE(importance, 0) DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        
        rows = await timescale_client.fetch(query, *params)
        
        # Group by date
        by_date = {}
        reports = []
        
        for row in rows:
            report = dict(row)
            if report.get('report_date'):
                date_str = str(report['report_date'])
                report['report_date'] = date_str
                by_date[date_str] = by_date.get(date_str, 0) + 1
            reports.append(report)
        
        return {
            "start_date": str(today),
            "end_date": str(end_date),
            "earnings": reports,
            "total_count": len(reports),
            "by_date": by_date
        }
        
    except Exception as e:
        logger.error(f"upcoming_earnings_error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/earnings/ticker/{symbol}/dates")
async def get_earnings_dates(
    symbol: str,
    limit: int = Query(100, ge=1, le=500, description="Max earnings dates to return"),
):
    """
    Lightweight endpoint: returns only earnings dates + time_slot for a ticker.
    Designed for chart E markers - minimal payload.
    """
    try:
        query = """
            SELECT report_date, time_slot
            FROM earnings_calendar
            WHERE symbol = $1
            ORDER BY report_date DESC
            LIMIT $2
        """
        
        rows = await timescale_client.fetch(query, symbol.upper(), limit)
        
        dates = []
        for row in rows:
            dates.append({
                "date": str(row["report_date"]) if row.get("report_date") else None,
                "time_slot": row.get("time_slot", "TBD")
            })
        
        return {
            "symbol": symbol.upper(),
            "count": len(dates),
            "dates": dates
        }
        
    except Exception as e:
        logger.error(f"earnings_dates_error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/v1/earnings/ticker/{symbol}")
async def get_earnings_by_ticker(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="Number of recent earnings"),
):
    """
    Get earnings history for a specific ticker.
    Includes all Benzinga data fields.
    """
    try:
        query = """
            SELECT 
                symbol, company_name, report_date, time_slot, fiscal_quarter,
                eps_estimate, eps_actual, eps_surprise_pct, beat_eps,
                revenue_estimate, revenue_actual, revenue_surprise_pct, beat_revenue,
                guidance_direction, guidance_commentary, key_highlights,
                importance, date_status, eps_method, revenue_method,
                previous_eps, previous_revenue,
                status, source
            FROM earnings_calendar
            WHERE symbol = $1
            ORDER BY report_date DESC
            LIMIT $2
        """
        
        rows = await timescale_client.fetch(query, symbol.upper(), limit)
        
        reports = []
        for row in rows:
            report = dict(row)
            if report.get('report_date'):
                report['report_date'] = str(report['report_date'])
            reports.append(report)
        
        # Calculate stats
        beats = sum(1 for r in reports if r.get('beat_eps') == True)
        misses = sum(1 for r in reports if r.get('beat_eps') == False)
        beat_rate = (beats / (beats + misses) * 100) if (beats + misses) > 0 else None
        
        return {
            "symbol": symbol.upper(),
            "earnings": reports,
            "count": len(reports),
            "stats": {
                "total_reported": beats + misses,
                "beats": beats,
                "misses": misses,
                "beat_rate": round(beat_rate, 1) if beat_rate else None
            }
        }
        
    except Exception as e:
        logger.error(f"earnings_ticker_error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================================
# IPO Endpoints (Initial Public Offerings)
# ============================================================================

IPOS_CACHE_KEY = "cache:ipos:all"
IPOS_CACHE_TTL = 86400  # 24 hours

@app.get("/api/v1/ipos")
async def get_ipos(
    ipo_status: Optional[str] = Query(None, description="Filter by status: pending, new, history, rumor, withdrawn, direct_listing_process"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results (max 1000)"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Get IPO (Initial Public Offerings) data from Polygon.io
    
    - Data is cached for 24 hours in Redis
    - Includes pending, new, historical, rumors, and withdrawn IPOs
    - Use force_refresh=true to bypass cache
    """
    global redis_client
    
    try:
        # Try cache first (unless force refresh)
        if not force_refresh and redis_client:
            cached = await redis_client.get(IPOS_CACHE_KEY)
            if cached:
                # redis_client.get() ya deserializa automáticamente
                results = cached.get("results", [])
                
                # Apply status filter if provided
                if ipo_status:
                    results = [r for r in results if r.get("ipo_status") == ipo_status]
                
                # Apply limit
                results = results[:limit]
                
                logger.info("ipos_cache_hit", count=len(results))
                return {
                    "status": "OK",
                    "count": len(results),
                    "results": results,
                    "cached": True,
                    "cache_ttl_hours": 24
                }
        
        # Fetch from Polygon API usando cliente con connection pooling
        all_results = []
        
        # First request
        data = await http_clients.polygon.get_ipos(limit=1000)
        
        if data.get("results"):
            all_results.extend(data["results"])
        
        next_url = data.get("next_url")
        
        # Paginate to get more results (up to 3 pages = 3000 IPOs)
        page_count = 1
        while next_url and page_count < 3:
            data = await http_clients.polygon.get_ipos_page(next_url)
            
            if data.get("results"):
                all_results.extend(data["results"])
            
            next_url = data.get("next_url")
            page_count += 1
        
        # Cache the full results (redis_client serializa automáticamente)
        if redis_client and all_results:
            cache_data = {
                "results": all_results,
                "fetched_at": datetime.now().isoformat(),
                "total_count": len(all_results)
            }
            await redis_client.set(IPOS_CACHE_KEY, cache_data, ttl=IPOS_CACHE_TTL)
            logger.info("ipos_cached", count=len(all_results))
        
        # Apply filters for response
        results = all_results
        if ipo_status:
            results = [r for r in results if r.get("ipo_status") == ipo_status]
        
        results = results[:limit]
        
        return {
            "status": "OK",
            "count": len(results),
            "results": results,
            "cached": False,
            "total_available": len(all_results)
        }
        
    except httpx.HTTPError as e:
        logger.error("ipos_http_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Polygon API error: {str(e)}")
    except Exception as e:
        logger.error("ipos_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ipos/stats")
async def get_ipos_stats():
    """Get IPO statistics by status"""
    global redis_client
    
    try:
        # Get cached data (redis_client.get() deserializa automáticamente)
        if redis_client:
            cached = await redis_client.get(IPOS_CACHE_KEY)
            if cached:
                results = cached.get("results", [])
                
                # Count by status
                stats = {}
                for ipo in results:
                    status = ipo.get("ipo_status", "unknown")
                    stats[status] = stats.get(status, 0) + 1
                
                return {
                    "status": "OK",
                    "total": len(results),
                    "by_status": stats,
                    "fetched_at": cached.get("fetched_at")
                }
        
        return {"status": "OK", "total": 0, "by_status": {}, "message": "No cached data, call /api/v1/ipos first"}
        
    except Exception as e:
        logger.error("ipos_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# IPO Prospectus Endpoint (S-1, 424B4) - SEC-API.io con datos estructurados
# ============================================================================

IPO_PROSPECTUS_CACHE_TTL = 604800  # 7 días (los prospectos no cambian)
SEC_API_S1_424B4_URL = "https://api.sec-api.io/form-s1-424b4"

@app.get("/api/v1/ipos/{ticker}/prospectus")
async def get_ipo_prospectus(
    ticker: str,
    ipo_status: Optional[str] = Query(None, description="IPO status: pending, new, history - affects which forms to search"),
    issuer_name: Optional[str] = Query(None, description="Company name for searching when ticker not found"),
    force_refresh: bool = Query(False, description="Force refresh from API")
):
    """
    Get IPO prospectus data (S-1, 424B4) with structured data extraction.
    
    Uses SEC-API.io to get:
    - Public offering price (per share and total)
    - Underwriters (lead and co-managers)
    - Securities being offered
    - Management team
    - Employee counts
    - Law firms and auditors
    
    Depending on IPO status:
    - pending/rumor: Search for S-1 (registration statement)
    - new/history: Search for 424B4 (final prospectus) or S-1
    
    Results are cached for 7 days.
    """
    global redis_client
    ticker = ticker.upper()
    cache_key = f"cache:ipo_prospectus:{ticker}:{ipo_status or 'all'}"
    
    try:
        # Try cache first
        if not force_refresh and redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info("ipo_prospectus_cache_hit", ticker=ticker)
                return {
                    "status": "OK",
                    "ticker": ticker,
                    **cached,
                    "cached": True
                }
        
        # Check if SEC API key is available
        sec_api_key = settings.SEC_API_IO_KEY
        if not sec_api_key:
            logger.warning("sec_api_key_not_configured")
            raise HTTPException(status_code=503, detail="SEC API not configured")
        
        # Determine which form types to search based on IPO status
        form_filter = '(formType:"S-1" OR formType:"S-1/A" OR formType:"424B4")'
        if ipo_status in ["pending", "rumor"]:
            form_filter = '(formType:"S-1" OR formType:"S-1/A")'
        elif ipo_status in ["new", "history"]:
            form_filter = '(formType:"424B4" OR formType:"S-1" OR formType:"S-1/A")'
        
        filings = []
        search_method = "ticker"
        
        # Usar cliente SEC-API con connection pooling
        if not http_clients.sec_api:
            raise HTTPException(status_code=503, detail="SEC API client not initialized")
        
        # First try: search by ticker
        query = f'ticker:{ticker} AND {form_filter}'
        data = await http_clients.sec_api.search_s1_424b4(query, size=10)
        filings = data.get("data", [])
        
        # Second try: if no results and issuer_name provided, search by company name
        if not filings and issuer_name:
            # Clean issuer name for search (remove special chars, take first meaningful words)
            clean_name = issuer_name.replace(",", "").replace(".", "").replace("Inc", "").replace("Ltd", "").replace("Corp", "").strip()
            # Take first 3-4 words to avoid too specific search
            name_parts = clean_name.split()[:4]
            search_name = " ".join(name_parts)
            
            if search_name:
                query = f'entityName:"{search_name}" AND {form_filter}'
                logger.info("ipo_prospectus_fallback_search", ticker=ticker, search_name=search_name)
                
                data = await http_clients.sec_api.search_s1_424b4(query, size=10)
                filings = data.get("data", [])
                search_method = "entity_name"
        
        if not filings:
            # For pending IPOs, this is expected - S-1 might not be filed yet
            message = "No SEC filings found yet"
            if ipo_status in ["pending", "rumor"]:
                message = "S-1 Registration Statement not yet filed with SEC. This is normal for pending IPOs - the S-1 is typically filed a few weeks before the expected listing date."
            
            return {
                "status": "OK",
                "ticker": ticker,
                "filings": [],
                "structured_data": None,
                "cached": False,
                "ipo_status": ipo_status,
                "message": message,
                "suggestion": f"Check back closer to the IPO date, or search SEC EDGAR directly: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={issuer_name or ticker}&type=S-1"
            }
        
        # Process the first (most recent) filing as the main prospectus
        main_filing = filings[0]
        
        # Build structured response
        structured_data = {
            "form_type": main_filing.get("formType"),
            "filed_at": main_filing.get("filedAt"),
            "accession_no": main_filing.get("accessionNo"),
            "cik": main_filing.get("cik"),
            "entity_name": main_filing.get("entityName"),
            "filing_url": main_filing.get("filingUrl"),
            
            # Securities info
            "tickers": main_filing.get("tickers", []),
            "securities": main_filing.get("securities", []),
            
            # Pricing info (available in 424B4, sometimes in S-1)
            "public_offering_price": main_filing.get("publicOfferingPrice"),
            "underwriting_discount": main_filing.get("underwritingDiscount"),
            "proceeds_before_expenses": main_filing.get("proceedsBeforeExpenses"),
            
            # Parties involved
            "underwriters": main_filing.get("underwriters", []),
            "law_firms": main_filing.get("lawFirms", []),
            "auditors": main_filing.get("auditors", []),
            
            # Company info
            "management": main_filing.get("management", []),
            "employees": main_filing.get("employees"),
        }
        
        # Build simplified filings list for all found filings
        filings_list = []
        for f in filings:
            filings_list.append({
                "form_type": f.get("formType"),
                "filed_at": f.get("filedAt"),
                "accession_no": f.get("accessionNo"),
                "entity_name": f.get("entityName"),
                "filing_url": f.get("filingUrl"),
                "has_pricing": f.get("publicOfferingPrice") is not None,
                "underwriters_count": len(f.get("underwriters", [])),
            })
        
        result = {
            "filings": filings_list,
            "structured_data": structured_data,
            "fetched_at": datetime.now().isoformat(),
            "total_found": data.get("total", {}).get("value", len(filings))
        }
        
        # Cache the results
        if redis_client:
            await redis_client.set(cache_key, result, ttl=IPO_PROSPECTUS_CACHE_TTL)
            logger.info("ipo_prospectus_cached", ticker=ticker, count=len(filings))
        
        return {
            "status": "OK",
            "ticker": ticker,
            **result,
            "cached": False
        }
        
    except httpx.HTTPError as e:
        logger.error("ipo_prospectus_http_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=502, detail=f"SEC API error: {str(e)}")
    except Exception as e:
        logger.error("ipo_prospectus_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Insider Trading Endpoints (Form 4)
# ============================================================================

INSIDER_CACHE_KEY = "cache:insider_trading"
INSIDER_CACHE_TTL = 300  # 5 minutos
INSIDER_CLUSTERS_CACHE_TTL = 600  # 10 minutos

@app.get("/api/v1/insider-trading")
async def get_insider_trading(
    ticker: Optional[str] = Query(None, description="Filter by company ticker"),
    size: int = Query(50, ge=1, le=200, description="Number of results"),
    from_index: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    Get insider trading data (Form 4 filings) from SEC-API.io
    
    Form 4 reports are filed when insiders (executives, directors, 10%+ shareholders)
    buy or sell company stock. This endpoint provides real-time access to these filings.
    """
    try:
        if not http_clients.sec_api:
            raise HTTPException(status_code=503, detail="SEC API client not available")
        
        # Cache key includes ticker and pagination
        cache_key = f"{INSIDER_CACHE_KEY}:{ticker or 'all'}:{size}:{from_index}"
        
        # Try cache first
        if redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info("insider_trading_cache_hit", ticker=ticker)
                return {**cached, "cached": True}
        
        # Fetch from SEC-API
        data = await http_clients.sec_api.search_form4(
            ticker=ticker,
            size=size,
            from_index=from_index
        )
        
        # Process filings to extract key info
        filings = []
        for f in data.get('filings', []):
            # Extract insider name from entities
            insider_name = None
            insider_cik = None
            insider_title = None
            is_director = False
            is_officer = False
            
            for e in f.get('entities', []):
                if 'Reporting' in e.get('companyName', ''):
                    insider_name = e.get('companyName', '').replace(' (Reporting)', '')
                    insider_cik = e.get('cik')
            
            filings.append({
                'id': f.get('id'),
                'ticker': f.get('ticker'),
                'company': f.get('companyName'),
                'insider_name': insider_name,
                'insider_cik': insider_cik,
                'filed_at': f.get('filedAt'),
                'period_of_report': f.get('periodOfReport'),
                'form_type': f.get('formType'),
                'accession_no': f.get('accessionNo'),
                'url': f.get('linkToFilingDetails'),
            })
        
        result = {
            "status": "OK",
            "total": data.get('total', {}).get('value', 0),
            "filings": filings,
            "fetched_at": datetime.now().isoformat()
        }
        
        # Cache results
        if redis_client:
            await redis_client.set(cache_key, result, ttl=INSIDER_CACHE_TTL)
        
        logger.info("insider_trading_fetched", ticker=ticker, count=len(filings))
        return {**result, "cached": False}
        
    except httpx.HTTPError as e:
        logger.error("insider_trading_http_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"SEC API error: {str(e)}")
    except Exception as e:
        logger.error("insider_trading_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/insider-trading/{ticker}/details")
async def get_insider_trading_details(
    ticker: str,
    size: int = Query(200, ge=1, le=1000, description="Number of filings to fetch"),
):
    """
    Get detailed insider trading data for a specific ticker.
    Uses SEC-API.io /insider-trading endpoint which returns pre-parsed JSON.
    NO requests to SEC.gov needed - avoids rate limits!
    """
    try:
        if not http_clients.sec_api:
            raise HTTPException(status_code=503, detail="SEC API client not available")
        
        ticker = ticker.upper()
        cache_key = f"{INSIDER_CACHE_KEY}:details:{ticker}:{size}"
        
        # Try cache first
        if redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                return {**cached, "cached": True}
        
        # Fetch from SEC-API.io /insider-trading endpoint (max 50 per request)
        all_transactions = []
        from_index = 0
        batch_size = 50  # Max per request for this endpoint
        
        while len(all_transactions) < size:
            data = await http_clients.sec_api.search_insider_trading(
                ticker=ticker, 
                size=batch_size, 
                from_index=from_index
            )
            transactions = data.get('transactions', [])
            if not transactions:
                break
            all_transactions.extend(transactions)
            from_index += batch_size
            
            # Check if we got all available
            total_available = data.get('total', {}).get('value', 0)
            if from_index >= total_available or from_index >= 500:  # Limit to 500 max
                break
        
        # Transform SEC-API.io format to our format
        filing_data_list = []
        for tx in all_transactions[:size]:
            issuer = tx.get('issuer', {})
            owner = tx.get('reportingOwner', {})
            relationship = owner.get('relationship', {})
            
            # Extract transactions from nonDerivativeTable and derivativeTable
            transactions = []
            
            # Non-derivative transactions (stocks)
            nd_table = tx.get('nonDerivativeTable', {})
            for t in nd_table.get('transactions', []):
                amounts = t.get('amounts', {})
                transactions.append({
                    'transaction_code': t.get('coding', {}).get('code', 'U'),
                    'security_title': t.get('securityTitle', 'Common Stock'),
                    'shares': amounts.get('shares', 0),
                    'price': amounts.get('pricePerShare', 0),
                    'acquired_disposed': amounts.get('acquiredDisposedCode', 'A'),
                    'date': t.get('transactionDate'),
                    'total_value': (amounts.get('shares', 0) or 0) * (amounts.get('pricePerShare', 0) or 0)
                })
            
            # Derivative transactions (options, warrants)
            d_table = tx.get('derivativeTable', {})
            for t in d_table.get('transactions', []):
                amounts = t.get('amounts', {})
                underlying = t.get('underlyingSecurity', {})
                transactions.append({
                    'transaction_code': t.get('coding', {}).get('code', 'U'),
                    'security_title': t.get('securityTitle', 'Derivative'),
                    'shares': amounts.get('shares', 0) or underlying.get('shares', 0),
                    'price': amounts.get('pricePerShare', 0),
                    'acquired_disposed': amounts.get('acquiredDisposedCode', 'A'),
                    'date': t.get('transactionDate'),
                    'total_value': (amounts.get('shares', 0) or 0) * (amounts.get('pricePerShare', 0) or 0),
                    'is_derivative': True
                })
            
            filing_data = {
                'id': tx.get('id') or tx.get('accessionNo'),
                'ticker': issuer.get('tradingSymbol', ticker),
                'company': issuer.get('name'),
                'insider_name': owner.get('name'),
                'filed_at': tx.get('filedAt'),
                'period_of_report': tx.get('periodOfReport'),
                'url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={issuer.get('cik')}&type=4",
                'transactions': transactions,
                'insider_title': relationship.get('officerTitle'),
                'is_director': relationship.get('isDirector', False),
                'is_officer': relationship.get('isOfficer', False),
                'is_ten_percent_owner': relationship.get('isTenPercentOwner', False),
            }
            filing_data_list.append(filing_data)
        
        result = {
            "status": "OK",
            "ticker": ticker,
            "total": len(filing_data_list),
            "filings": filing_data_list,
            "fetched_at": datetime.now().isoformat()
        }
        
        # Cache for 15 minutes
        if redis_client:
            await redis_client.set(cache_key, result, ttl=900)
        
        logger.info("insider_details_fetched", ticker=ticker, count=len(filing_data_list))
        return {**result, "cached": False}
        
    except Exception as e:
        logger.error("insider_details_error", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/insider-trading/clusters")
async def get_insider_clusters(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    min_count: int = Query(3, ge=2, le=10, description="Minimum trades for cluster"),
):
    """
    Detect insider trading clusters - multiple insiders trading in the same company
    
    This is a powerful signal: when multiple insiders buy/sell within a short period,
    it often indicates significant upcoming events.
    """
    try:
        if not http_clients.sec_api:
            raise HTTPException(status_code=503, detail="SEC API client not available")
        
        cache_key = f"{INSIDER_CACHE_KEY}:clusters:{days}:{min_count}"
        
        # Try cache first
        if redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info("insider_clusters_cache_hit", days=days)
                return {**cached, "cached": True}
        
        # Fetch clusters
        data = await http_clients.sec_api.get_form4_clusters(days=days, min_count=min_count)
        
        result = {
            "status": "OK",
            "clusters": data.get('clusters', []),
            "period_days": days,
            "min_count": min_count,
            "total_filings_analyzed": data.get('total_filings', 0),
            "fetched_at": datetime.now().isoformat()
        }
        
        # Cache results
        if redis_client:
            await redis_client.set(cache_key, result, ttl=INSIDER_CLUSTERS_CACHE_TTL)
        
        logger.info("insider_clusters_fetched", clusters=len(data.get('clusters', [])))
        return {**result, "cached": False}
        
    except httpx.HTTPError as e:
        logger.error("insider_clusters_http_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"SEC API error: {str(e)}")
    except Exception as e:
        logger.error("insider_clusters_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Chart Data Endpoint - TradingView Style (Lazy Loading)
# ============================================================================
# 
# Estrategia: Carga rápida inicial + lazy loading al hacer scroll
# - Primera carga: ~500 barras más recientes (rápido, <1s)
# - Scroll hacia atrás: pide más datos con parámetro "before"
# - Intraday: Polygon API (histórico desde 2015+)
# - Daily: FMP API (10+ años)
#

# Barras que se envian POR DELANTE del instante de replay. Son el colchon que
# permite avanzar sin una peticion por paso; el cliente no las pinta hasta que
# su reloj llega a ellas.
REPLAY_LOOKAHEAD_BARS = 300

CHART_INTERVALS = {
    "1min": {"polygon_timespan": "minute", "polygon_multiplier": 1, "cache_ttl": 30, "bars_per_page": 1500},
    "2min": {"polygon_timespan": "minute", "polygon_multiplier": 2, "cache_ttl": 60, "bars_per_page": 2000},
    "5min": {"polygon_timespan": "minute", "polygon_multiplier": 5, "cache_ttl": 120, "bars_per_page": 2000},
    "15min": {"polygon_timespan": "minute", "polygon_multiplier": 15, "cache_ttl": 300, "bars_per_page": 1500},
    "30min": {"polygon_timespan": "minute", "polygon_multiplier": 30, "cache_ttl": 600, "bars_per_page": 1000},
    "1hour": {"polygon_timespan": "hour", "polygon_multiplier": 1, "cache_ttl": 1800, "bars_per_page": 750},
    "4hour": {"polygon_timespan": "hour", "polygon_multiplier": 4, "cache_ttl": 3600, "bars_per_page": 500},
    "12hour": {"polygon_timespan": "hour", "polygon_multiplier": 12, "cache_ttl": 7200, "bars_per_page": 500},
    "1day": {"polygon_timespan": "day", "polygon_multiplier": 1, "cache_ttl": 14400, "bars_per_page": 1000},
    "1week": {"polygon_timespan": "week", "polygon_multiplier": 1, "cache_ttl": 14400, "bars_per_page": 500},
    "1month": {"polygon_timespan": "month", "polygon_multiplier": 1, "cache_ttl": 14400, "bars_per_page": 500},
    "3month": {"polygon_timespan": "month", "polygon_multiplier": 3, "cache_ttl": 14400, "bars_per_page": 300},
    "1year": {"polygon_timespan": "year", "polygon_multiplier": 1, "cache_ttl": 14400, "bars_per_page": 200},
}

POLYGON_AGGS_URL = "https://api.polygon.io/v2/aggs/ticker"
FMP_DAILY_URL = "https://financialmodelingprep.com/api/v3/historical-price-full"


async def fetch_polygon_chunk(
    symbol: str,
    multiplier: int,
    timespan: str,
    to_date: str,
    limit: int = 500,
    before_timestamp: Optional[int] = None,
    to_timestamp: Optional[int] = None,
    lookahead: int = 0
) -> tuple[List[dict], Optional[int]]:
    """
    Fetch chart data from Polygon - optimized for speed.
    Uses 50000 limit to get all data in one request.
    Returns (bars, oldest_timestamp) for lazy loading pagination.
    
    NOTA: Usa http_clients.polygon con connection pooling.
    """
    from datetime import datetime as dt, timedelta
    
    # Parse to_date (fallback en ET, no en el reloj UTC del contenedor)
    try:
        to_dt = dt.strptime(to_date, "%Y-%m-%d")
    except:
        to_dt = dt.now(tz=ET_TZ).replace(tzinfo=None)
    
    # Convert desired bars to calendar days, accounting for
    # weekends (~5/7 trading ratio) and holidays.
    if timespan == "minute":
        bars_per_trading_day = 390 // multiplier
        trading_days = max(1, limit // bars_per_trading_day)
        days_needed = max(10, int(trading_days * 7 / 5) + 10)
    elif timespan == "hour":
        bars_per_trading_day = max(1, 16 // multiplier)
        trading_days = max(1, limit // bars_per_trading_day)
        days_needed = max(30, int(trading_days * 7 / 5) + 15)
    elif timespan == "week":
        days_needed = max(90, limit * 7 + 30)
    elif timespan == "month" and multiplier >= 3:
        days_needed = max(730, limit * 92 + 60)
    elif timespan == "month":
        days_needed = max(365, limit * 31 + 60)
    elif timespan == "year":
        days_needed = max(730, limit * 366 + 60)
    else:
        days_needed = max(30, int(limit * 7 / 5) + 15)
    
    from_dt_calc = to_dt - timedelta(days=days_needed)
    min_date = dt(2000, 1, 1)
    if from_dt_calc < min_date:
        from_dt_calc = min_date
    from_date = from_dt_calc.strftime("%Y-%m-%d")
    
    # Retry on transient HTTP/2 failures (stale connection, server disconnect)
    last_err = None
    for attempt in range(3):
        try:
            data = await http_clients.polygon.get_aggregates(
                symbol=symbol,
                multiplier=multiplier,
                timespan=timespan,
                from_date=from_date,
                to_date=to_date,
                limit=50000,
                sort="desc"
            )
            break
        except httpx.HTTPError as e:
            last_err = e
            if attempt < 2:
                import asyncio
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
            raise last_err
    
    results = data.get("results", [])

    # Results are desc (newest first) - reverse to asc
    results.reverse()
    
    # Transform to our format
    all_bars = []
    for bar in results:
        bar_time = int(bar["t"] / 1000)
        # If before_timestamp is set, only include bars BEFORE that timestamp
        if before_timestamp and bar_time >= before_timestamp:
            continue
        all_bars.append({
            "time": bar_time,
            "open": float(bar["o"]),
            "high": float(bar["h"]),
            "low": float(bar["l"]),
            "close": float(bar["c"]),
            "volume": int(bar["v"])
        })
    
    full_count = len(all_bars)
    if to_timestamp is not None:
        # Replay: la ventana se ancla en el INSTANTE pedido, no en el cierre de
        # la sesion. Sin esto el recorte de abajo se queda con la cola del dia y
        # el grafico nace SIN pasado: medido, 0 barras previas incluso con
        # limit=500 (devolvia 11:30-19:59 para un replay que arranca a las 9:35).
        # Se devuelven las `limit` barras previas al instante mas un colchon
        # posterior, que es el que permite avanzar sin pedir en cada paso.
        # Una barra cubre [time, time+duracion). Solo esta COMPLETA si termina
        # en o antes del instante: la que lo contiene se esta formando todavia,
        # y su cierre seria informacion del futuro. Medido: con el corte por
        # `time` la barra de 09:35 (que llega hasta 09:35:59) entraba como
        # pasado y cerraba 12 centimos por delante del ultimo precio real.
        _bar_s = {"minute": 60, "hour": 3600, "day": 86400,
                  "week": 604800, "month": 2592000, "year": 31536000}
        dur = _bar_s.get(timespan, 60) * max(1, multiplier)
        past = [b for b in all_bars if b["time"] + dur <= to_timestamp]
        ahead = [b for b in all_bars if b["time"] + dur > to_timestamp]
        all_bars = past[-limit:] + (ahead[:lookahead] if lookahead > 0 else [])
    elif len(all_bars) > limit:
        all_bars = all_bars[-limit:]
    
    # Determine if there's more data available (for lazy loading).
    # Always return oldest_time when we have bars so the frontend can
    # request the next chunk. Polygon has ~2 years of intraday history;
    # the frontend will stop when a loadMore returns 0 bars.
    oldest_time = all_bars[0]["time"] if all_bars else None
    has_more = len(all_bars) > 0
    
    logger.info("polygon_chunk_fetched", symbol=symbol, bars=len(all_bars), total_available=full_count, oldest=oldest_time, before=before_timestamp)
    return all_bars, oldest_time


async def fetch_fmp_chunk(
    symbol: str,
    to_date: str,
    limit: int = 1000
) -> tuple[List[dict], Optional[int]]:
    """
    Fetch a chunk of daily data from FMP.
    
    NOTA: Usa http_clients.fmp con connection pooling.
    """
    # Usar cliente FMP con connection pooling
    raw_data = await http_clients.fmp.get_historical_prices(symbol, to_date)
    
    historical = raw_data.get("historical", [])
    if not historical:
        historical = raw_data if isinstance(raw_data, list) else []
    
    # FMP returns descending, take first 'limit' and reverse
    historical = historical[:limit]
    
    bars = []
    for bar in reversed(historical):
        try:
            date_str = bar.get("date", "")
            from datetime import datetime as dt
            dt_obj = dt.strptime(date_str, "%Y-%m-%d")
            
            bars.append({
                "time": int(dt_obj.timestamp()),
                "open": float(bar.get("open", 0)),
                "high": float(bar.get("high", 0)),
                "low": float(bar.get("low", 0)),
                "close": float(bar.get("close", 0)),
                "volume": int(bar.get("volume", 0))
            })
        except Exception:
            continue
    
    oldest_time = bars[0]["time"] if bars else None
    has_more = len(historical) >= limit
    
    logger.info("fmp_chunk_fetched", symbol=symbol, bars=len(bars))
    return bars, oldest_time if has_more else None


async def fetch_polygon_daily_chunk(
    symbol: str,
    to_date: str,
    limit: int = 1000
) -> tuple[List[dict], Optional[int]]:
    """
    Fetch daily OHLCV data from Polygon.
    
    Usado como FALLBACK cuando FMP no tiene datos (warrants, OTC, SPACs, etc.)
    
    Args:
        symbol: Ticker symbol
        to_date: Fecha fin YYYY-MM-DD
        limit: Número de barras a obtener
    
    Returns:
        (bars, oldest_time) para lazy loading pagination
    """
    from datetime import datetime as dt, timedelta
    
    # Parse to_date
    try:
        to_dt = dt.strptime(to_date, "%Y-%m-%d")
    except:
        to_dt = dt.now()
    
    # Calcular from_date (~5 años de historia para tener suficientes barras)
    # Trading days ~252/año, pedimos más para asegurar cobertura
    days_needed = int(limit * 1.5) + 30  # Buffer extra
    from_date = (to_dt - timedelta(days=days_needed)).strftime("%Y-%m-%d")
    
    # Usar cliente Polygon con connection pooling
    data = await http_clients.polygon.get_daily_aggregates(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        limit=limit
    )
    
    results = data.get("results", [])
    
    # Transform to our format (Polygon ya viene en orden ascendente)
    bars = []
    for bar in results:
        try:
            bars.append({
                "time": int(bar["t"] / 1000),  # ms to seconds
                "open": float(bar["o"]),
                "high": float(bar["h"]),
                "low": float(bar["l"]),
                "close": float(bar["c"]),
                "volume": int(bar["v"])
            })
        except Exception:
            continue
    
    # Tomar las últimas 'limit' barras si hay más
    full_count = len(bars)
    if len(bars) > limit:
        bars = bars[-limit:]
    
    oldest_time = bars[0]["time"] if bars else None
    has_more = full_count >= limit or data.get("next_url") is not None
    
    logger.info("polygon_daily_chunk_fetched", symbol=symbol, bars=len(bars), total_available=full_count)
    return bars, oldest_time if has_more else None


# Map frontend interval strings to bar_builder timeframe (minutes).
# Daily+ intervals don't need live stitching (they only close at EOD).
INTERVAL_TO_TF_MIN: dict = {
    "1min": 1,
    "2min": 2,
    "5min": 5,
    "10min": 10,
    "15min": 15,
    "30min": 30,
    "1hour": 60,
    "4hour": 240,
    "12hour": 720,
}

# URL of the bar_builder service (live bar store + hydration HTTP API).
BAR_BUILDER_URL = os.getenv("BAR_BUILDER_URL", "http://bar_builder:8050")

# Reusable, short-lived HTTP client for fire-and-forget hydrate calls.
# Created lazily so unit tests / import-time don't open sockets.
_bar_builder_http_client: Optional[httpx.AsyncClient] = None


def _get_bar_builder_client() -> httpx.AsyncClient:
    global _bar_builder_http_client
    if _bar_builder_http_client is None:
        _bar_builder_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(2.0, connect=0.5),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _bar_builder_http_client


async def _trigger_hydrate(symbol: str, wait: bool = False) -> bool:
    """
    POST to bar_builder /hydrate.

    Called when /api/v1/chart can't find an in-formation bar for a symbol —
    bar_builder will fetch Polygon snapshot+aggs and seed the live store so
    the next chart request stitches correctly.

    Args:
        symbol: ticker to hydrate
        wait: if True, await the hydrate response (so the caller can
              re-read the live bar within the same request). If False,
              fire-and-forget (default).

    Returns: True if hydrate completed successfully (only meaningful when wait=True).
    """
    try:
        client = _get_bar_builder_client()
        timeout = httpx.Timeout(2.5, connect=0.5) if wait else httpx.Timeout(0.5, connect=0.3)
        resp = await client.post(
            f"{BAR_BUILDER_URL}/hydrate",
            json={"symbols": [symbol.upper()]},
            timeout=timeout,
        )
        if not wait:
            return True
        if resp.status_code != 200:
            return False
        body = resp.json()
        status = (body.get("results") or {}).get(symbol.upper(), "")
        return status == "ok"
    except Exception as e:
        logger.debug("hydrate_trigger_failed", symbol=symbol, error=str(e))
        return False


async def _stitch_live_bar(
    chart_data: List[dict],
    symbol: str,
    interval: str,
    is_latest_request: bool,
    allow_hydrate: bool = True,
) -> List[dict]:
    """
    Append/merge the in-formation bar from bars:{tf}min:current onto chart_data.

    This is THE critical step that closes the gap between Polygon REST aggs
    (which lag) and the live WebSocket stream. Without it, the most recent
    bar is either missing or shows stale OHLC right after a timeframe switch.

    Behaviour:
      - Only runs for "latest" requests (no before / no to). For `before`
        (historical chunks) and `to` (replay) the live bar is irrelevant.
      - `after` (gap recovery) is treated as "latest" because the frontend
        wants the freshest tail.
      - Only runs for intraday intervals that bar_builder supports.
      - If no live bar in Redis, fire-and-forget hydrate (next call will hit).
    """
    if not is_latest_request:
        return chart_data
    tf_min = INTERVAL_TO_TF_MIN.get(interval)
    if tf_min is None:
        return chart_data
    if redis_client is None:
        return chart_data

    try:
        live_bar = await redis_client.hget(
            f"bars:{tf_min}min:current", symbol.upper()
        )
    except Exception as e:
        logger.warning("live_bar_read_failed", symbol=symbol, interval=interval, error=str(e))
        return chart_data

    if not live_bar or not isinstance(live_bar, dict):
        if not allow_hydrate:
            # Índices y otros símbolos sin snapshot en Polygon: hydrate no
            # aplica (bar_builder se alimenta de stream:realtime:aggregates).
            return chart_data
        # Cold ticker: no live bar yet. Hydrate synchronously with a short
        # timeout so the very first chart load doesn't miss the in-formation
        # bar. After hydrate completes, bar_builder has already flushed the
        # current bars to Redis, so we re-read.
        hydrated = await _trigger_hydrate(symbol, wait=True)
        if hydrated:
            try:
                live_bar = await redis_client.hget(
                    f"bars:{tf_min}min:current", symbol.upper()
                )
            except Exception:
                live_bar = None
        if not live_bar or not isinstance(live_bar, dict):
            # Either hydrate failed/timed out, or even after hydrate there
            # was no data (e.g. ticker not yet open today). Return as-is and
            # kick a background retry so future requests benefit.
            if not hydrated:
                asyncio.create_task(_trigger_hydrate(symbol, wait=False))
            return chart_data

    # Convert bar_builder format → frontend format
    bar_start_ms = live_bar.get("bar_start")
    if not bar_start_ms:
        return chart_data
    live_time = int(bar_start_ms) // 1000
    open_v = float(live_bar.get("open", 0) or 0)
    if open_v <= 0:
        # Defensive: an empty seeded bar somehow leaked. Skip stitching.
        return chart_data

    live_entry = {
        "time": live_time,
        "open": open_v,
        "high": float(live_bar.get("high", 0) or 0),
        "low": float(live_bar.get("low", 0) or 0),
        "close": float(live_bar.get("close", 0) or 0),
        "volume": int(live_bar.get("volume", 0) or 0),
    }

    if not chart_data:
        return [live_entry]

    last = chart_data[-1]
    last_time = int(last["time"])

    if live_time > last_time:
        # New bar in formation past the REST tail.
        return chart_data + [live_entry]

    if live_time == last_time:
        # Same bucket. The live bar can have a tighter high/low and a
        # different close because Polygon REST aggs lag a few seconds.
        # We preserve REST's open (authoritative) and merge the rest.
        merged = dict(last)
        merged["high"] = max(float(last["high"]), live_entry["high"])
        merged["low"] = min(float(last["low"]), live_entry["low"]) if live_entry["low"] > 0 else float(last["low"])
        merged["close"] = live_entry["close"]
        # Take the larger volume (REST may have a more complete count for
        # closed micro-windows; live may have caught newer trades).
        merged["volume"] = max(int(last["volume"]), live_entry["volume"])
        return chart_data[:-1] + [merged]

    # live_time < last_time: the REST already moved past the live cache.
    # This can happen briefly after a bar close. Leave REST as-is.
    return chart_data


# Resolución de intervalos para índices sintéticos TRDL (minutos por vela)
_INTERNAL_INTERVAL_MINUTES = {
    "1min": 1, "2min": 2, "5min": 5, "15min": 15, "30min": 30,
    "1hour": 60, "4hour": 240, "12hour": 720, "1day": 1440,
}


async def _get_internal_index_chart(
    symbol: str,
    interval: str,
    before: Optional[int],
    after: Optional[int],
    to: Optional[int],
    bars_limit: int,
):
    """
    Histórico de los índices sintéticos TRDL INDEX desde minute_bars
    (TimescaleDB, escrita por analytics/MarketInternalsCalculator).
    Reagrega las barras de 1 min al intervalo pedido en SQL.
    """
    minutes = _INTERNAL_INTERVAL_MINUTES.get(interval)
    if minutes is None:
        raise HTTPException(status_code=400, detail=f"Interval {interval} not supported for {symbol}")
    if timescale_client is None:
        raise HTTPException(status_code=503, detail="Database not available")
    
    bucket_ms = minutes * 60 * 1000
    conditions = ["symbol = $1"]
    params: list = [symbol]
    if before:
        params.append(before * 1000)
        conditions.append(f"ts < ${len(params)}")
    if after:
        params.append(after * 1000)
        conditions.append(f"ts > ${len(params)}")
    if to:
        params.append(to * 1000)
        conditions.append(f"ts <= ${len(params)}")
    params.append(bars_limit)
    
    query = f"""
        SELECT bucket, o, h, l, c, v FROM (
            SELECT
                (ts / {bucket_ms})::bigint * {bucket_ms} AS bucket,
                (array_agg(open ORDER BY ts ASC))[1]   AS o,
                max(high)                              AS h,
                min(low)                               AS l,
                (array_agg(close ORDER BY ts DESC))[1] AS c,
                sum(volume)                            AS v
            FROM minute_bars
            WHERE {' AND '.join(conditions)}
            GROUP BY bucket
        ) agg
        ORDER BY bucket DESC
        LIMIT ${len(params)}
    """
    
    try:
        rows = await timescale_client.fetch(query, *params)
    except Exception as e:
        logger.error("internal_chart_query_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail="Internal index data unavailable")
    
    rows.reverse()  # asc para el chart
    data = [
        {
            "time": int(r["bucket"] // 1000),
            "open": float(r["o"]),
            "high": float(r["h"]),
            "low": float(r["l"]),
            "close": float(r["c"]),
            "volume": int(r["v"] or 0),
        }
        for r in rows
    ]
    
    return {
        "symbol": symbol,
        "interval": interval,
        "source": "trdl_index",
        "data": data,
        "count": len(data),
        "oldest_time": data[0]["time"] if data and len(data) >= bars_limit else None,
        "has_more": len(data) >= bars_limit,
        "cached": False,
        "fetched_at": datetime.now().isoformat(),
    }


# ── Índices bursátiles via FMP ──────────────────────────────────────────────
# Intervalos que FMP sirve nativos en /stable/historical-chart
_FMP_NATIVE_INTRADAY = {"1min", "5min", "15min", "30min", "1hour", "4hour"}
# Derivados: se construyen agregando el intervalo base de FMP
_FMP_DERIVED_INTRADAY = {"2min": ("1min", 120), "12hour": ("4hour", 43200)}
# EOD y superiores se agregan desde 1day (bucket por calendario)
_FMP_EOD_INTERVALS = {"1day", "1week", "1month", "3month", "1year"}

# Días naturales a pedir por página según densidad de barras del intervalo
_FMP_INTRADAY_DAYS = {
    "1min": 8, "2min": 14, "5min": 30, "15min": 60,
    "30min": 90, "1hour": 150, "4hour": 365, "12hour": 730,
}


def _bucket_eod(bars: List[dict], interval: str) -> List[dict]:
    """Agrega barras diarias a 1week/1month/3month/1year por calendario."""
    if interval == "1day":
        return bars
    from datetime import datetime as dt, timezone as tz
    out: List[dict] = []
    current_key = None
    for b in bars:
        d = dt.fromtimestamp(b["time"], tz=tz.utc)
        if interval == "1week":
            key = (d.isocalendar().year, d.isocalendar().week)
        elif interval == "1month":
            key = (d.year, d.month)
        elif interval == "3month":
            key = (d.year, (d.month - 1) // 3)
        else:  # 1year
            key = d.year
        if key != current_key:
            out.append(dict(b))
            current_key = key
        else:
            agg = out[-1]
            agg["high"] = max(agg["high"], b["high"])
            agg["low"] = min(agg["low"], b["low"])
            agg["close"] = b["close"]
            agg["volume"] += b["volume"]
    return out


def _bucket_intraday(bars: List[dict], bucket_secs: int) -> List[dict]:
    """Agrega barras intradía a un bucket mayor (2min desde 1min, etc.)."""
    out: List[dict] = []
    current_bucket = None
    for b in bars:
        bucket = (b["time"] // bucket_secs) * bucket_secs
        if bucket != current_bucket:
            nb = dict(b)
            nb["time"] = bucket
            out.append(nb)
            current_bucket = bucket
        else:
            agg = out[-1]
            agg["high"] = max(agg["high"], b["high"])
            agg["low"] = min(agg["low"], b["low"])
            agg["close"] = b["close"]
            agg["volume"] += b["volume"]
    return out


async def _get_fmp_index_chart(
    symbol: str,
    interval: str,
    before: Optional[int],
    after: Optional[int],
    to: Optional[int],
    bars_limit: int,
    force_refresh: bool = False,
):
    """
    Chart de índices bursátiles (SPX, VIX, ^GDAXI...) desde FMP.

    - EOD (1day+): historical-price-full (S&P desde 1950), agregado por
      calendario para 1week/1month/3month/1year.
    - Intradía: /stable/historical-chart (1min desde ~2022). 2min y 12hour
      se derivan del intervalo nativo inferior.
    - Vela viva: la stitchea bar_builder desde stream:realtime:aggregates
      (publicado por fmp_indices) — sin hydrate (eso es solo Polygon).

    `symbol` llega ya en forma interna canónica; a FMP se le habla en la suya.
    """
    from datetime import datetime as dt, timedelta

    fmp_symbol = index_to_fmp(symbol)
    is_latest_request = before is None and to is None

    config = CHART_INTERVALS.get(interval)
    if config is None:
        raise HTTPException(status_code=400, detail=f"Invalid interval {interval}")

    range_key = f"after:{after}" if after else (f"to:{to}" if to else (before or "latest"))
    cache_key = f"chart:idx:{symbol}:{interval}:{range_key}:{bars_limit}"

    if not force_refresh and redis_client:
        try:
            cached = await redis_client.get(cache_key)
        except Exception:
            cached = None
        if cached:
            data = await _stitch_live_bar(
                cached.get("data", []), symbol, interval, is_latest_request,
                allow_hydrate=False,
            )
            return {**cached, "data": data, "count": len(data), "cached": True}

    # Fecha tope de la página, siempre en ET
    if before:
        to_dt = dt.fromtimestamp(before - 1, tz=ET_TZ)
    elif to:
        to_dt = dt.fromtimestamp(to, tz=ET_TZ)
    else:
        to_dt = datetime.now(tz=ET_TZ)
    to_date = to_dt.strftime("%Y-%m-%d")

    bars: List[dict] = []
    try:
        if interval in _FMP_EOD_INTERVALS:
            # Factor de barras diarias necesarias por barra agregada
            factor = {"1day": 1, "1week": 5, "1month": 21, "3month": 63, "1year": 252}[interval]
            daily, _ = await fetch_fmp_chunk(fmp_symbol, to_date, limit=min(bars_limit * factor, 20000))
            bars = _bucket_eod(daily, interval)
        else:
            base_interval, bucket_secs = (
                _FMP_DERIVED_INTRADAY[interval]
                if interval in _FMP_DERIVED_INTRADAY
                else (interval, None)
            )
            if base_interval not in _FMP_NATIVE_INTRADAY:
                raise HTTPException(
                    status_code=400,
                    detail=f"Interval {interval} not supported for index {symbol}",
                )
            days = _FMP_INTRADAY_DAYS.get(interval, 30)
            from_date = (to_dt - timedelta(days=days)).strftime("%Y-%m-%d")
            raw = await http_clients.fmp.get_intraday_chart(
                fmp_symbol, base_interval, from_date, to_date
            )
            # FMP devuelve descendente con date "YYYY-MM-DD HH:MM:SS" en ET
            for r in reversed(raw or []):
                try:
                    naive = dt.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
                    t = int(naive.replace(tzinfo=ET_TZ).timestamp())
                    bars.append({
                        "time": t,
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": int(r.get("volume") or 0),
                    })
                except (KeyError, ValueError):
                    continue
            if bucket_secs:
                bars = _bucket_intraday(bars, bucket_secs)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("fmp_index_chart_error", symbol=symbol, interval=interval, error=str(e))
        raise HTTPException(status_code=502, detail="Index data unavailable")

    # Filtros de paginación exactos
    if before:
        bars = [b for b in bars if b["time"] < before]
    if to:
        bars = [b for b in bars if b["time"] <= to]
    if after:
        bars = [b for b in bars if b["time"] > after]

    full_count = len(bars)
    if len(bars) > bars_limit:
        bars = bars[-bars_limit:]

    oldest_time = bars[0]["time"] if bars else None
    # EOD de índices llega hasta 1950; intradía FMP cubre años: dejamos que
    # el frontend pare cuando una página vuelva vacía.
    has_more = len(bars) > 0

    result = {
        "symbol": symbol,
        "interval": interval,
        "source": "fmp_index",
        "data": bars,
        "count": len(bars),
        "oldest_time": oldest_time,
        "has_more": has_more,
        "cached": False,
        "fetched_at": datetime.now().isoformat(),
    }

    if redis_client and bars:
        try:
            await redis_client.set(cache_key, result, ttl=config["cache_ttl"])
        except Exception:
            pass

    data = await _stitch_live_bar(
        bars, symbol, interval, is_latest_request, allow_hydrate=False
    )
    return {**result, "data": data, "count": len(data)}


async def _recycled_symbol_floor(symbol: str, head: str) -> Optional[int]:
    """
    Detect a recycled ticker and return the Unix timestamp floor below which its
    Polygon history belongs to a PREVIOUS, unrelated issuer.

    `symbol` is a predecessor in a ticker chain whose head is `head`, but the
    symbol has since been reassigned to a DIFFERENT, currently-trading security
    (different composite_figi).

    Example: the chain ["SPCX","SPCK"] is valid for the SPAC ETF (SPCX→SPCK
    rename). But SPCX was later relisted as Space Exploration Technologies — a
    different FIGI, list_date 2026-06-12. Polygon still serves the ETF's
    2020-2026 aggregates under the SPCX symbol, so even fetching SPCX directly
    mixes both issuers. We return the new entity's list_date as a floor so the
    caller can drop the prior issuer's bars.

    Returns:
        * Unix timestamp (int) of the current entity's list_date when the symbol
          is a recycled security (clip everything older).
        * None when the symbol is NOT recycled (e.g. FB→META keeps FIGI
          continuity) — the chain and full history must be preserved untouched.

    Conservative: only treats the symbol as recycled when both composite_figi
    values are known, they differ, and `symbol` is actively trading right now.
    """
    if not timescale_client:
        return None
    try:
        rows = await timescale_client.fetch(
            """
            SELECT symbol, composite_figi, is_actively_trading, list_date
            FROM tickers_unified
            WHERE symbol = ANY($1::text[])
            """,
            [symbol.upper(), head.upper()],
        )
    except Exception as e:
        logger.warning("recycled_check_failed", symbol=symbol, head=head, error=str(e))
        return None

    by_sym = {str(r["symbol"]).upper(): r for r in rows}
    sym_row = by_sym.get(symbol.upper())
    head_row = by_sym.get(head.upper())
    if not sym_row or not head_row:
        return None

    sym_figi = sym_row["composite_figi"]
    head_figi = head_row["composite_figi"]
    if not sym_figi or not head_figi or sym_figi == head_figi:
        return None
    if not sym_row["is_actively_trading"]:
        return None

    list_date = sym_row["list_date"]
    if not list_date:
        # Recycled but no list_date to clip on — signal recycling with a 0 floor
        # so the chain is still dropped (no redirect), even if we can't trim.
        return 0
    return _list_date_to_ts(list_date) or 0


def _list_date_to_ts(list_date) -> Optional[int]:
    """Convert a DATE/'YYYY-MM-DD' value into a UTC midnight Unix timestamp."""
    if not list_date:
        return None
    try:
        from datetime import datetime as _dt, date as _date, time as _time, timezone as _tz
        if isinstance(list_date, str):
            list_date = _dt.strptime(list_date[:10], "%Y-%m-%d").date()
        if isinstance(list_date, _dt):
            list_date = list_date.date()
        if not isinstance(list_date, _date):
            return None
        return int(_dt.combine(list_date, _time.min, tzinfo=_tz.utc).timestamp())
    except Exception:
        return None


async def _current_listing_start_ts(symbol: str) -> Optional[int]:
    """
    Unix timestamp of when the CURRENT entity began trading under `symbol`.

    This is the most recent `ticker_change` event date from Polygon — the point
    from which the symbol's aggregates belong to today's issuer. Bars before it
    belong to a PRIOR issuer that used the same symbol and must be trimmed.

    Why not list_date? list_date tracks the ENTITY's first listing under ANY
    symbol (META = 2012-05-18, Facebook's IPO), so it does NOT mark when the
    symbol changed hands. The Roundhill Metaverse ETF traded as META from
    2021-06 to 2022-06; only the 2022-06-09 ticker_change date correctly
    separates it from Meta Platforms.

    Resolution order: Redis cache → Polygon events → list_date fallback.
    Cached 7 days. Returns None when nothing is resolvable (no trim).
    """
    symbol = symbol.upper()
    cache_key = "ticker:listing_start"
    if redis_client:
        try:
            cached = await redis_client.hget(cache_key, symbol)
            if cached is not None:
                val = int(cached)
                return None if val < 0 else val
        except Exception:
            pass

    resolved: Optional[int] = None
    try:
        data = await http_clients.polygon.get_ticker_events(symbol)
        events = (data.get("results", {}) or {}).get("events", []) or []
        dates = [
            e.get("date")
            for e in events
            if (e.get("ticker_change", {}) or {}).get("ticker", "").upper() == symbol
            and e.get("date")
        ]
        if dates:
            resolved = _list_date_to_ts(max(dates))
    except Exception as e:
        logger.warning("listing_start_events_failed", symbol=symbol, error=str(e))

    if resolved is None:
        resolved = await _list_date_floor(symbol)

    if redis_client:
        try:
            await redis_client.hset(cache_key, symbol, resolved if resolved is not None else -1)
            await redis_client.client.expire(cache_key, 7 * 86400)
        except Exception:
            pass
    return resolved


async def _list_date_floor(symbol: str) -> Optional[int]:
    """
    Return the Unix timestamp of `symbol`'s list_date, used to trim bars that
    predate the current security's listing.

    Polygon assigns list_date per ENTITY (e.g. META = 2012-05-18, the original
    Facebook IPO), so for a normal or renamed ticker this is older than any bar
    it has and the trim is a no-op. It only removes data when Polygon serves
    aggregates from BEFORE the listing under the same symbol — the signature of
    a recycled ticker (e.g. SPCX: SPAC ETF era under SpaceX's symbol).
    """
    if not timescale_client:
        return None
    try:
        row = await timescale_client.fetchrow(
            "SELECT list_date FROM tickers_unified WHERE symbol = $1",
            symbol.upper(),
        )
    except Exception as e:
        logger.warning("list_date_lookup_failed", symbol=symbol, error=str(e))
        return None
    if not row:
        return None
    return _list_date_to_ts(row["list_date"])


@app.get("/api/v1/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    interval: str = Query(default="1day", description="Chart interval: 1min, 5min, 15min, 30min, 1hour, 4hour, 1day"),
    before: Optional[int] = Query(default=None, description="Load bars before this Unix timestamp (for lazy loading)"),
    after: Optional[int] = Query(default=None, description="Load bars after this Unix timestamp (for gap recovery)"),
    to: Optional[int] = Query(default=None, description="Upper bound Unix timestamp — return bars up to this time (for replay)"),
    limit: Optional[int] = Query(default=None, description="Number of bars to load (default: 500 for intraday, 1000 for daily)"),
    force_refresh: bool = Query(default=False, description="Force refresh from API")
):
    """
    Get OHLCV chart data - TradingView Style with Lazy Loading.
    
    Strategy:
    - First call (no 'before'/'after'/'to'): Returns most recent ~500 bars
    - with 'before': Returns older bars for infinite scroll
    - with 'after': Returns bars newer than timestamp (gap recovery on tab resume)
    - with 'to': Returns bars ending at this timestamp (for replay mode)
    
    Sources:
    - Intraday (1min-4hour): Polygon API
    - Daily (1day): FMP API
    
    Frontend usage:
    1. Initial: GET /chart/AAPL?interval=1hour
    2. Load more: GET /chart/AAPL?interval=1hour&before=<oldest_time>
    3. Gap recovery: GET /chart/AAPL?interval=1min&after=<last_bar_time>
    4. Replay:    GET /chart/AAPL?interval=5min&to=<replay_timestamp>
    """
    global redis_client
    
    symbol = symbol.upper()
    interval = interval.lower()
    
    # Validate interval
    if interval not in CHART_INTERVALS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid interval. Supported: {', '.join(CHART_INTERVALS.keys())}"
        )
    
    config = CHART_INTERVALS[interval]
    bars_limit = limit or config["bars_per_page"]
    
    # Índices sintéticos TRDL INDEX (TRDL:TICK, TRDL:TICKC, TRDL:ADD):
    # no existen en Polygon — histórico desde nuestra tabla minute_bars
    if symbol.startswith("TRDL:"):
        return await _get_internal_index_chart(symbol, interval, before, after, to, bars_limit)

    # Índices bursátiles (SPX, VIX, ^GDAXI...): histórico desde FMP.
    # Acepta alias interno (SPX) y forma FMP (^GSPC) — normaliza al interno.
    index_symbol = normalize_index_symbol(symbol)
    if index_symbol:
        return await _get_fmp_index_chart(
            index_symbol, interval, before, after, to, bars_limit, force_refresh
        )
    
    # Fechas SIEMPRE en ET: un timestamp de las 19:30 ET es "hoy" para el
    # mercado aunque en UTC ya sea mañana.
    from datetime import datetime as dt
    if before:
        to_date = dt.fromtimestamp(before - 1, tz=ET_TZ).strftime("%Y-%m-%d")
    elif to:
        to_date = dt.fromtimestamp(to, tz=ET_TZ).strftime("%Y-%m-%d")
    else:
        to_date = datetime.now(tz=ET_TZ).strftime("%Y-%m-%d")
    
    range_key = f"after:{after}" if after else (f"to:{to}" if to else (before or 'latest'))
    cache_key = f"chart:v3:{symbol}:{interval}:{range_key}:{bars_limit}"

    # "Latest" requests (no before / no to) and "after" requests both want
    # the live bar stitched at the tail. Historical chunks (before) and
    # replay (to) don't.
    is_latest_request = before is None and to is None

    try:
        # Check cache first
        if not force_refresh and redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("chart_cache_hit", symbol=symbol, interval=interval, before=before)
                cached_data = cached.get("data", [])
                stitched_data = await _stitch_live_bar(
                    cached_data, symbol, interval, is_latest_request
                )
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "source": cached.get("source", "unknown"),
                    "data": stitched_data,
                    "count": len(stitched_data),
                    "oldest_time": cached.get("oldest_time"),
                    "has_more": cached.get("has_more", False),
                    "cached": True,
                    "fetched_at": cached.get("fetched_at")
                }
        
        chart_data = []
        oldest_time = None
        source = "unknown"
        
        # Unified Polygon path for all intervals (with ticker chaining)
        requested_symbol = symbol
        chain = await get_ticker_chain(symbol, redis_client)

        # Recycled-symbol guard: when the user requests a chain PREDECESSOR
        # (not the head) and that symbol has been reassigned to a different
        # live security, two things are wrong: (1) the chain would redirect to
        # the old issuer's data, and (2) Polygon serves the prior issuer's
        # aggregates under the SAME symbol. So we drop the chain AND record a
        # `recycled_floor` (the new entity's list_date) to trim older bars that
        # belong to the previous issuer. Symbols pinned in MANUAL_CHAIN_OVERRIDES
        # are left untouched (human decisions win, e.g. FB→META).
        recycled_floor: Optional[int] = None
        if (
            chain
            and requested_symbol.upper() != chain[-1].upper()
            and requested_symbol.upper() not in MANUAL_CHAIN_OVERRIDES
        ):
            recycled_floor = await _recycled_symbol_floor(requested_symbol, chain[-1])
            if recycled_floor is not None:
                logger.info(
                    "chart_chain_skipped_recycled_symbol",
                    requested=requested_symbol,
                    chain=chain,
                    floor=recycled_floor,
                )
                chain = None

        if chain:
            # If user requested an old/legacy symbol (e.g. XXII), anchor fetch on
            # the latest symbol in chain (e.g. CEP) so chart includes recent bars.
            effective_symbol = chain[-1]
            if effective_symbol != requested_symbol:
                logger.info(
                    "chart_symbol_resolved_to_latest_chain_member",
                    requested=requested_symbol,
                    effective=effective_symbol,
                    chain=chain
                )
            # Trim the chain head to the date its current issuer took the
            # symbol, so a prior issuer's bars under the same symbol (e.g. the
            # Metaverse ETF that traded as META before Meta Platforms) are
            # dropped while the predecessors still supply older history.
            head_floor = await _current_listing_start_ts(effective_symbol)
            chart_data, oldest_time = await fetch_chained_polygon_data(
                effective_symbol, config["polygon_multiplier"], config["polygon_timespan"],
                to_date, bars_limit, before, chain, fetch_polygon_chunk, fetch_fmp_chunk,
                head_floor=head_floor,
            )
        else:
            chart_data, oldest_time = await fetch_polygon_chunk(
                symbol,
                config["polygon_multiplier"],
                config["polygon_timespan"],
                to_date,
                bars_limit,
                before_timestamp=before,
                to_timestamp=to,
                lookahead=REPLAY_LOOKAHEAD_BARS if to else 0
            )
            # No chain in play: trim any bars predating the date this symbol's
            # current issuer took it. Harmless for normal tickers; removes a
            # prior issuer's history under a recycled symbol (e.g. SPCX).
            if recycled_floor is None:
                recycled_floor = await _current_listing_start_ts(symbol)
        source = "polygon"

        # Trim bars that predate a recycled symbol's current listing — those
        # belong to a prior, unrelated issuer that used the same ticker.
        if recycled_floor and chart_data:
            before_trim = len(chart_data)
            chart_data = [b for b in chart_data if b["time"] >= recycled_floor]
            if len(chart_data) < before_trim:
                # Reached the start of the current entity: nothing older to load.
                oldest_time = chart_data[0]["time"] if chart_data else None
                has_more_override = False
            else:
                has_more_override = None
        else:
            has_more_override = None

        if after and chart_data:
            chart_data = [b for b in chart_data if b["time"] > after]
        # El recorte por `to` NO se hace aqui: lo hace fetch_polygon_chunk, que
        # ancla la ventana en el instante y devuelve las barras previas mas un
        # colchon posterior (REPLAY_LOOKAHEAD_BARS). Antes no se anclaba en
        # ningun sitio y el replay recibia la cola de la sesion: cero pasado.
        
        has_more = oldest_time is not None
        if has_more_override is not None:
            has_more = has_more_override
        
        # Short TTL for gap recovery (fresh data), longer for historical chunks
        if after:
            cache_ttl = 10  # 10s — data is near-realtime
        elif before:
            cache_ttl = 86400  # 24h for historical chunks
        else:
            cache_ttl = config["cache_ttl"]
        result = {
            "data": chart_data,
            "source": source,
            "oldest_time": oldest_time,
            "has_more": has_more,
            "fetched_at": datetime.now().isoformat()
        }
        
        if redis_client and chart_data:
            await redis_client.set(cache_key, result, ttl=cache_ttl)
            logger.info("chart_chunk_cached", symbol=symbol, interval=interval, bars=len(chart_data), before=before)

        # Stitch live in-formation bar from bar_builder's Redis store.
        # This runs AFTER cache write so cache stores raw REST data and the
        # live bar is always fresh on every request (no caching of volatile data).
        stitched_data = await _stitch_live_bar(
            chart_data, symbol, interval, is_latest_request
        )

        return {
            "symbol": symbol,
            "interval": interval,
            "source": source,
            "data": stitched_data,
            "count": len(stitched_data),
            "oldest_time": oldest_time,
            "has_more": has_more,
            "cached": False,
            "fetched_at": result["fetched_at"]
        }
    
    except httpx.HTTPError as e:
        logger.error("chart_http_error", symbol=symbol, interval=interval, error=str(e))
        raise HTTPException(status_code=502, detail=f"API error: {str(e)}")
    except Exception as e:
        logger.error("chart_error", symbol=symbol, interval=interval, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/scanner")
async def websocket_scanner(
    websocket: WebSocket,
    token: str = Query(None)  # Token JWT en query param: ws://...?token=xxx
):
    """
    WebSocket para datos del scanner en tiempo real
    
    🔒 AUTENTICACIÓN:
    - Requiere token JWT en query param: ws://host/ws/scanner?token=<jwt>
    - Para refresh de token (sin desconectar): {"action": "refresh_token", "token": "<new_jwt>"}
    
    El cliente puede enviar comandos:
    - {"action": "subscribe", "symbols": ["AAPL", "TSLA"]}
    - {"action": "unsubscribe", "symbols": ["AAPL"]}
    - {"action": "subscribe_all"}
    - {"action": "refresh_token", "token": "<new_jwt>"}
    
    El servidor envía:
    - {"type": "rvol", "symbol": "AAPL", "data": {...}}
    - {"type": "aggregate", "symbol": "AAPL", "data": {...}}
    """
    # =============================================
    # AUTENTICACIÓN AL CONECTAR
    # =============================================
    user = None
    ws_auth_enabled = getattr(settings, 'auth_enabled', False)
    
    if ws_auth_enabled:
        if not token:
            logger.warning("ws_connection_rejected reason=missing_token")
            await websocket.close(code=4001, reason="Token required")
            return
        
        try:
            user = await clerk_jwt_verifier.verify_token(token)
            logger.info(f"ws_authenticated user_id={user.id}")
        except Exception as e:
            logger.warning(f"ws_connection_rejected reason=invalid_token error={e}")
            await websocket.close(code=4003, reason="Invalid token")
            return
    
    connection_id = str(uuid.uuid4())
    
    await connection_manager.connect(websocket, connection_id)
    
    try:
        # Enviar mensaje de bienvenida
        await connection_manager.send_personal_message(
            {
                "type": "connected",
                "connection_id": connection_id,
                "message": "Connected to Tradeul Scanner",
                "timestamp": datetime.now().isoformat()
            },
            connection_id
        )
        
        # Loop para recibir comandos del cliente
        while True:
            data = await websocket.receive_json()
            
            action = data.get("action")
            
            if action == "subscribe":
                symbols = set(data.get("symbols", []))
                connection_manager.subscribe(connection_id, symbols)
                
                await connection_manager.send_personal_message(
                    {
                        "type": "subscribed",
                        "symbols": list(symbols),
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
            
            elif action == "unsubscribe":
                symbols = set(data.get("symbols", []))
                connection_manager.unsubscribe(connection_id, symbols)
                
                await connection_manager.send_personal_message(
                    {
                        "type": "unsubscribed",
                        "symbols": list(symbols),
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
            
            elif action == "subscribe_all":
                connection_manager.subscribe(connection_id, {"*"})
                
                await connection_manager.send_personal_message(
                    {
                        "type": "subscribed_all",
                        "message": "Subscribed to all tickers",
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
            
            elif action == "refresh_token":
                # Refresh token sin desconectar (Clerk tokens expiran en 60s)
                new_token = data.get("token")
                if new_token and ws_auth_enabled:
                    try:
                        user = await clerk_jwt_verifier.verify_token(new_token)
                        logger.debug(f"ws_token_refreshed user_id={user.id}")
                        await connection_manager.send_personal_message(
                            {
                                "type": "token_refreshed",
                                "success": True,
                                "timestamp": datetime.now().isoformat()
                            },
                            connection_id
                        )
                    except Exception as e:
                        logger.warning(f"ws_token_refresh_failed error={e}")
                        await connection_manager.send_personal_message(
                            {
                                "type": "token_refresh_failed",
                                "error": str(e),
                                "timestamp": datetime.now().isoformat()
                            },
                            connection_id
                        )
            
            elif action == "ping":
                await connection_manager.send_personal_message(
                    {
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    },
                    connection_id
                )
    
    except WebSocketDisconnect:
        connection_manager.disconnect(connection_id)
        logger.info("websocket_disconnected", connection_id=connection_id)
    
    except Exception as e:
        logger.error(
            "websocket_error",
            connection_id=connection_id,
            error=str(e)
        )
        connection_manager.disconnect(connection_id)


# ============================================================================
# Eleven Labs TTS Proxy (para evitar CORS)
# ============================================================================

@app.post("/api/v1/tts/speak")
async def text_to_speech(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user)  # 🔒 Requiere auth - endpoint costoso
):
    """
    Proxy para Eleven Labs TTS - evita problemas de CORS
    PROTEGIDO: Requiere autenticación (endpoint costoso - Eleven Labs $$$)
    """
    logger.info(f"tts_request user_id={user.id}")
    try:
        body = await request.json()
        text = body.get("text", "")
        voice_id = body.get("voice_id", "21m00Tcm4TlvDq8ikWAM")  # Rachel
        language_code = body.get("language_code", "es")  # Forzar español por defecto
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        if not http_clients.elevenlabs:
            raise HTTPException(status_code=503, detail="TTS service not configured")
        
        # Usar cliente Eleven Labs con connection pooling
        audio_content = await http_clients.elevenlabs.text_to_speech(
            text=text,
            voice_id=voice_id,
            language_code=language_code
        )
        
        return Response(
            content=audio_content,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache"
            }
        )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS service timeout")
    except httpx.HTTPStatusError as e:
        logger.error(f"Eleven Labs error: {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail="TTS service error")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "services.api_gateway.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=None  # Usar nuestro logger personalizado
    )

