"""
API Gateway - Main Entry Point

Gateway principal para el frontend web:
- REST API para consultas
- WebSocket para datos en tiempo real
- Agregación de múltiples servicios
"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import Optional, List
import structlog
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse, Response, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from shared.config.settings import settings
from shared.config.fmp_endpoints import FMPEndpoints
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
from routers.watchlist_router import router as watchlist_router
from http_clients import http_clients, HTTPClientManager
from auth import clerk_jwt_verifier, PassiveAuthMiddleware, get_current_user, AuthenticatedUser

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
    set_user_filters_timescale_client(timescale_client)  # Para user_filters
    set_user_filters_redis(redis_client)  # Para notificar al scanner cuando cambian filtros
    set_screener_templates_timescale_client(timescale_client)  # Para screener_templates
    set_symbols_timescale_client(timescale_client)  # Para symbols (indexed query ~150ms)
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
    
    # Inicializar HTTP Clients con connection pooling
    # Esto evita crear conexiones por request - CRÍTICO para latencia
    await http_clients.initialize(
        polygon_api_key=settings.POLYGON_API_KEY,
        fmp_api_key=settings.FMP_API_KEY,
        sec_api_key=getattr(settings, 'SEC_API_IO_KEY', None),
        elevenlabs_api_key=os.getenv("ELEVEN_LABS_API_KEY"),
    )
    logger.info("http_clients_initialized_with_pooling")
    
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
    lifespan=lifespan
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
app.include_router(user_filters_router)
app.include_router(screener_templates_router)
app.include_router(financials_router)
app.include_router(watchlist_router)
app.include_router(proxy_router)  # Incluye endpoints de dilution, SEC filings, etc.
app.include_router(realtime_router)  # Real-time ticker data for charts
app.include_router(ratio_analysis_router)  # Ratio analysis entre dos activos
app.include_router(morning_news_router)  # Morning News Call diario
app.include_router(insights_router)  # TradeUL Insights (Morning, Mid-Morning, etc.)
app.include_router(symbols_router)  # Symbol lookups (market cap filtering for AI agent)
app.include_router(heatmap_router)  # Market heatmap visualization
app.include_router(scanner_router)  # Scanner filtered tickers


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
        
        technical, insider, fundamentals = await asyncio.gather(
            technical_task, insider_task, fundamentals_task,
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
        
        # 3. Combinar todos los datos
        enriched_metadata = {
            **db_metadata,
            "technical_daily": technical,      # RSI, MA, 52W - DIARIOS
            "insider_summary": insider,        # Resumen + CEO/CFO
            "price_snapshot": price,           # Precio actual
            "fundamentals_xbrl": fundamentals  # P/E, P/B, P/S desde SEC (NUEVO)
        }
        
        local_time = round((time.time() - start_time) * 1000)
        logger.info("fan_local_data_collected", 
                   ticker=ticker, 
                   local_time_ms=local_time,
                   has_metadata=bool(db_metadata),
                   has_technical=bool(technical),
                   has_insider=bool(insider),
                   has_price=bool(price),
                   has_fundamentals=bool(fundamentals))
        
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
    limit: int = Query(50, ge=1, le=2000, description="Limit results")
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
            limit=limit
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
):
    """
    Get earnings calendar for a specific date.
    Returns both scheduled and reported earnings.
    """
    from datetime import datetime, date as date_type
    
    try:
        # Parse date or use today
        if date:
            target_date = date_type.fromisoformat(date)
        else:
            target_date = datetime.now().date()
        
        # Build query
        query = """
            SELECT 
                symbol, company_name, report_date, time_slot, fiscal_quarter,
                eps_estimate, eps_actual, eps_surprise_pct, beat_eps,
                revenue_estimate, revenue_actual, revenue_surprise_pct, beat_revenue,
                guidance_direction, guidance_commentary, key_highlights,
                market_cap, sector, status, source, created_at
            FROM earnings_calendar
            WHERE report_date = $1
        """
        params = [target_date]
        
        if status:
            query += " AND status = $2"
            params.append(status)
        
        if time_slot:
            param_num = len(params) + 1
            query += f" AND time_slot = ${param_num}"
            params.append(time_slot.upper())
        
        query += " ORDER BY time_slot, symbol"
        
        rows = await timescale_client.fetch(query, *params)
        
        # Process results
        reports = []
        total_bmo = 0
        total_amc = 0
        total_reported = 0
        total_scheduled = 0
        
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
        
        return {
            "date": str(target_date),
            "reports": reports,
            "total_bmo": total_bmo,
            "total_amc": total_amc,
            "total_reported": total_reported,
            "total_scheduled": total_scheduled
        }
        
    except Exception as e:
        logger.error(f"earnings_calendar_error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/earnings/ticker/{symbol}")
async def get_earnings_by_ticker(
    symbol: str,
    limit: int = Query(10, ge=1, le=50, description="Number of recent earnings"),
):
    """
    Get earnings history for a specific ticker.
    """
    try:
        query = """
            SELECT 
                symbol, company_name, report_date, time_slot, fiscal_quarter,
                eps_estimate, eps_actual, eps_surprise_pct, beat_eps,
                revenue_estimate, revenue_actual, revenue_surprise_pct, beat_revenue,
                guidance_direction, guidance_commentary, key_highlights,
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
        
        return {
            "symbol": symbol.upper(),
            "earnings": reports,
            "count": len(reports)
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

CHART_INTERVALS = {
    "1min": {"polygon_timespan": "minute", "polygon_multiplier": 1, "cache_ttl": 30, "bars_per_page": 500},   # 30s cache - datos muy frescos
    "5min": {"polygon_timespan": "minute", "polygon_multiplier": 5, "cache_ttl": 120, "bars_per_page": 500},  # 2 min cache
    "15min": {"polygon_timespan": "minute", "polygon_multiplier": 15, "cache_ttl": 300, "bars_per_page": 500}, # 5 min cache
    "30min": {"polygon_timespan": "minute", "polygon_multiplier": 30, "cache_ttl": 600, "bars_per_page": 500}, # 10 min cache
    "1hour": {"polygon_timespan": "hour", "polygon_multiplier": 1, "cache_ttl": 1800, "bars_per_page": 500},   # 30 min cache
    "4hour": {"polygon_timespan": "hour", "polygon_multiplier": 4, "cache_ttl": 3600, "bars_per_page": 500},   # 1h cache
    "1day": {"source": "fmp", "cache_ttl": 14400, "bars_per_page": 1000},  # 4h cache - FMP para daily
}

POLYGON_AGGS_URL = "https://api.polygon.io/v2/aggs/ticker"
FMP_DAILY_URL = "https://financialmodelingprep.com/api/v3/historical-price-full"


async def fetch_polygon_chunk(
    symbol: str,
    multiplier: int,
    timespan: str,
    to_date: str,
    limit: int = 500,
    before_timestamp: Optional[int] = None
) -> tuple[List[dict], Optional[int]]:
    """
    Fetch chart data from Polygon - optimized for speed.
    Uses 50000 limit to get all data in one request.
    Returns (bars, oldest_timestamp) for lazy loading pagination.
    
    NOTA: Usa http_clients.polygon con connection pooling.
    """
    from datetime import datetime as dt, timedelta
    
    # Parse to_date
    try:
        to_dt = dt.strptime(to_date, "%Y-%m-%d")
    except:
        to_dt = dt.now()
    
    # Smart from_date based on desired bars and timeframe
    # ~7 trading hours per day, ~21 trading days per month
    if timespan == "minute":
        # Minutes: need more days for same number of bars
        bars_per_day = 390 // multiplier  # 390 min trading day
        # When loading more (before_timestamp set), need to go further back
        days_needed = max(10, (limit // bars_per_day) + 10)
    else:
        # Hours: ~7 trading hours per day
        bars_per_day = 7 // multiplier
        days_needed = max(30, (limit // max(1, bars_per_day)) + 10)
    
    from_date = (to_dt - timedelta(days=days_needed)).strftime("%Y-%m-%d")
    
    # Usar cliente Polygon con connection pooling
    data = await http_clients.polygon.get_aggregates(
        symbol=symbol,
        multiplier=multiplier,
        timespan=timespan,
        from_date=from_date,
        to_date=to_date,
        limit=50000  # Max limit - get all in one request
    )
    
    results = data.get("results", [])
    
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
    
    # Take only the last 'limit' bars (most recent of the filtered set) if we got more
    full_count = len(all_bars)
    if len(all_bars) > limit:
        all_bars = all_bars[-limit:]
    
    # Determine if there's more data available (for lazy loading)
    oldest_time = all_bars[0]["time"] if all_bars else None
    has_more = full_count >= limit or data.get("next_url") is not None
    
    logger.info("polygon_chunk_fetched", symbol=symbol, bars=len(all_bars), total_available=full_count, oldest=oldest_time, before=before_timestamp)
    return all_bars, oldest_time if has_more else None


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


@app.get("/api/v1/chart/{symbol}")
async def get_chart_data(
    symbol: str,
    interval: str = Query(default="1day", description="Chart interval: 1min, 5min, 15min, 30min, 1hour, 4hour, 1day"),
    before: Optional[int] = Query(default=None, description="Load bars before this Unix timestamp (for lazy loading)"),
    limit: Optional[int] = Query(default=None, description="Number of bars to load (default: 500 for intraday, 1000 for daily)"),
    force_refresh: bool = Query(default=False, description="Force refresh from API")
):
    """
    Get OHLCV chart data - TradingView Style with Lazy Loading.
    
    Strategy:
    - First call (no 'before'): Returns most recent ~500 bars (fast!)
    - Subsequent calls (with 'before'): Returns older bars for infinite scroll
    
    Sources:
    - Intraday (1min-4hour): Polygon API
    - Daily (1day): FMP API
    
    Response:
    {
        "symbol": "AAPL",
        "interval": "1hour",
        "source": "polygon" | "fmp",
        "data": [...],
        "count": 500,
        "oldest_time": 1699876800,  // For next "load more" call
        "has_more": true,
        "cached": false
    }
    
    Frontend usage:
    1. Initial: GET /chart/AAPL?interval=1hour
    2. Load more: GET /chart/AAPL?interval=1hour&before=<oldest_time>
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
    
    # Calculate to_date from 'before' parameter or use today
    if before:
        from datetime import datetime as dt
        to_date = dt.fromtimestamp(before - 1).strftime("%Y-%m-%d")
    else:
        to_date = datetime.now().strftime("%Y-%m-%d")
    
    # Cache key includes the 'before' for proper chunked caching
    cache_key = f"chart:v3:{symbol}:{interval}:{before or 'latest'}:{bars_limit}"
    
    try:
        # Check cache first
        if not force_refresh and redis_client:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug("chart_cache_hit", symbol=symbol, interval=interval, before=before)
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "source": cached.get("source", "unknown"),
                    "data": cached.get("data", []),
                    "count": len(cached.get("data", [])),
                    "oldest_time": cached.get("oldest_time"),
                    "has_more": cached.get("has_more", False),
                    "cached": True,
                    "fetched_at": cached.get("fetched_at")
                }
        
        chart_data = []
        oldest_time = None
        source = "unknown"
        
        # Usar clientes HTTP con connection pooling (ya inicializados)
        if interval == "1day":
            # Use FMP for daily data (primary source)
            chart_data, oldest_time = await fetch_fmp_chunk(
                symbol, to_date, bars_limit
            )
            source = "fmp"
            
            # FALLBACK: Si FMP no tiene datos, usar Polygon
            # Esto cubre warrants, OTC, y tickers que FMP no soporta
            if not chart_data:
                logger.info("fmp_no_data_fallback_polygon", symbol=symbol)
                chart_data, oldest_time = await fetch_polygon_daily_chunk(
                    symbol, to_date, bars_limit
                )
                source = "polygon"  # Update source to reflect actual data provider
        else:
            # Use Polygon for intraday data
            chart_data, oldest_time = await fetch_polygon_chunk(
                symbol,
                config["polygon_multiplier"],
                config["polygon_timespan"],
                to_date,
                bars_limit,
                before_timestamp=before  # Pass the before timestamp for filtering
            )
            source = "polygon"
        
        has_more = oldest_time is not None
        
        # Cache the result (longer TTL for historical data)
        cache_ttl = config["cache_ttl"] if not before else 86400  # 24h for historical chunks
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
        
        return {
            "symbol": symbol,
            "interval": interval,
            "source": source,
            "data": chart_data,
            "count": len(chart_data),
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

