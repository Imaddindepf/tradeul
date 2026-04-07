"""
Analysis Router
Endpoints de análisis usando exclusivamente el schema dilutiontracker v2.
Fuente única: tablas tickers, instruments, *_details, completed_offerings.
"""

import sys
sys.path.append('/app')

from fastapi import APIRouter, HTTPException

from shared.utils.timescale_client import TimescaleClient
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

from strategies.search_tracker import SearchTracker
from repositories.instrument_context_repository import InstrumentContextRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/validate/{ticker}")
async def validate_ticker(ticker: str):
    """
    Validar si un ticker existe en dilutiontracker v2.

    Returns:
      200 + {valid: true}  → ticker found
      200 + {valid: false} → ticker explicitly NOT in DB
      503                  → DB temporarily unavailable (frontend treats as 'proceed optimistically')
    """
    import asyncio
    ticker = ticker.upper()
    last_exc = None
    for attempt in range(3):
        db = TimescaleClient()
        try:
            await db.connect(min_size=1, max_size=3)
            try:
                result = await db.fetchrow(
                    "SELECT ticker, company AS company_name FROM tickers WHERE ticker = $1",
                    ticker,
                )
                if not result:
                    return {"valid": False, "ticker": ticker, "message": "Ticker not found"}
                return {
                    "valid": True,
                    "ticker": ticker,
                    "company_name": result["company_name"],
                    "sector": None,
                }
            finally:
                await db.disconnect()
        except Exception as e:
            last_exc = e
            logger.warning("validate_ticker_attempt_failed", ticker=ticker, attempt=attempt + 1, error=str(e))
            if attempt < 2:
                await asyncio.sleep(0.3 * (attempt + 1))  # 0.3s, 0.6s backoff

    # All 3 attempts failed → return 503 so frontend treats it as 'error' (not 'not_found')
    logger.error("validate_ticker_all_attempts_failed", ticker=ticker, error=str(last_exc))
    raise HTTPException(status_code=503, detail="DB temporarily unavailable")


@router.get("/trending")
async def get_trending_tickers(limit: int = 50):
    """Tickers más buscados, basado en contadores Redis."""
    try:
        redis = RedisClient()
        await redis.connect()
        try:
            tracker = SearchTracker(db=None, redis=redis)
            trending = await tracker.get_trending_tickers(days=7, limit=limit)
            return {"trending": trending, "period": "7_days", "count": len(trending)}
        finally:
            await redis.disconnect()
    except Exception as e:
        logger.error("get_trending_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}")
async def get_ticker_analysis(ticker: str):
    """
    Análisis completo de un ticker.
    Lee exclusivamente del schema dilutiontracker v2 — sin llamadas externas.
    """
    try:
        ticker = ticker.upper()
        db = TimescaleClient()
        await db.connect(min_size=1, max_size=2)
        redis = RedisClient()
        await redis.connect()
        try:
            # Registrar búsqueda en Redis
            # La tabla dilution_searches no existe en el schema v2, solo usamos Redis
            tracker = SearchTracker(db=None, redis=redis)
            await tracker.track_search(ticker)

            context_repo = InstrumentContextRepository(db)
            context = await context_repo.get_ticker_context(
                ticker=ticker,
                include_completed_offerings=True,
            )
            if not context:
                raise HTTPException(
                    status_code=404,
                    detail=f"Ticker {ticker} not found",
                )

            ti = context.ticker_info

            def _f(val):
                """Convertir Decimal/int a float, o None."""
                return float(val) if val is not None else None

            return {
                "summary": {
                    "ticker": ti.ticker,
                    "company_name": ti.company,
                    "sector": None,
                    "industry": None,
                    "market_cap": _f(ti.market_cap),
                    "shares_outstanding": _f(ti.shares_outstanding),
                    "free_float": _f(ti.float_shares),
                    "institutional_ownership": _f(ti.inst_ownership),
                    "last_price": _f(ti.last_price),
                    "exchange": None,
                },
                "cash_runway": None,
                "dilution_history": {"history": []},
                "holders": [],
                "filings": [],
                "financials": [],
                "dilution": {
                    "profile": {
                        "symbol": ti.ticker,
                        "current_price": _f(ti.last_price),
                        "shares_outstanding": _f(ti.shares_outstanding),
                        "completed_offerings": [
                            {
                                "ticker": item.ticker,
                                "offering_date": item.offering_date.isoformat() if item.offering_date else None,
                                "offering_type": item.offering_type,
                                "method": item.method,
                                "shares_offered": _f(item.shares),
                                "price_per_share": _f(item.price),
                                "amount_raised": _f(item.amount),
                            }
                            for item in context.completed_offerings
                        ],
                    },
                },
            }

        finally:
            await db.disconnect()
            await redis.disconnect()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_ticker_analysis_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{ticker}/refresh")
async def refresh_ticker_data(ticker: str):
    """Invalidar cache Redis de un ticker."""
    try:
        ticker = ticker.upper()
        redis = RedisClient()
        await redis.connect()
        try:
            await redis.delete(f"dilution:analysis:{ticker}")
            await redis.delete(f"sec_dilution:profile:{ticker}")
            logger.info("ticker_cache_invalidated", ticker=ticker)
            return {"ticker": ticker, "status": "refreshed"}
        finally:
            await redis.disconnect()
    except Exception as e:
        logger.error("refresh_ticker_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
