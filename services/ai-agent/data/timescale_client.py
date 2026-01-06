"""
TimescaleDB Client for AI Agent
Provides access to SEC filings, dilution data, and historical market data
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
import structlog

logger = structlog.get_logger(__name__)


class AgentTimescaleClient:
    """
    Cliente TimescaleDB para el AI Agent.
    
    Capacidades:
    - SEC Filings
    - Dilution profiles (warrants, ATMs, shelf registrations)
    - Market data daily
    """
    
    def __init__(self):
        self.database_url = self._build_database_url()
        self._pool: Optional[asyncpg.Pool] = None
    
    def _build_database_url(self) -> str:
        host = os.getenv("POSTGRES_HOST", "timescaledb")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "tradeul_user")
        password = os.getenv("POSTGRES_PASSWORD", "")
        db = os.getenv("POSTGRES_DB", "tradeul")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    async def connect(self):
        """Establece conexion con la base de datos"""
        try:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("timescale_connected")
        except Exception as e:
            logger.error("timescale_connection_error", error=str(e))
            raise
    
    async def close(self):
        """Cierra la conexion"""
        if self._pool:
            await self._pool.close()
    
    # =============================================
    # SEC DILUTION DATA
    # =============================================
    
    async def get_dilution_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el perfil de dilucion completo para un ticker.
        
        Returns:
            Dict con warrants, ATMs, shelf registrations, etc.
        """
        if not self._pool:
            return None
        
        try:
            async with self._pool.acquire() as conn:
                # Profile principal
                profile = await conn.fetchrow("""
                    SELECT ticker, cik, company_name, current_price,
                           shares_outstanding, free_float, last_scraped_at
                    FROM sec_dilution_profiles
                    WHERE ticker = $1
                """, symbol.upper())
                
                if not profile:
                    return None
                
                # Warrants activos
                warrants = await conn.fetch("""
                    SELECT warrant_type, exercise_price, shares_underlying,
                           expiration_date, is_exercisable, status
                    FROM sec_warrant_agreements
                    WHERE ticker = $1 AND status = 'active'
                    ORDER BY expiration_date
                """, symbol.upper())
                
                # ATM offerings activos
                atms = await conn.fetch("""
                    SELECT total_authorized, total_sold, remaining_capacity,
                           agent_name, effective_date, status
                    FROM sec_atm_offerings
                    WHERE ticker = $1 AND status = 'active'
                    ORDER BY effective_date DESC
                """, symbol.upper())
                
                # Shelf registrations
                shelfs = await conn.fetch("""
                    SELECT total_amount, remaining_amount, effective_date,
                           expiration_date, status
                    FROM sec_shelf_registrations
                    WHERE ticker = $1 AND status = 'active'
                    ORDER BY expiration_date DESC
                """, symbol.upper())
                
                return {
                    "ticker": profile["ticker"],
                    "company_name": profile["company_name"],
                    "shares_outstanding": profile["shares_outstanding"],
                    "free_float": profile["free_float"],
                    "last_updated": profile["last_scraped_at"].isoformat() if profile["last_scraped_at"] else None,
                    "warrants": [dict(w) for w in warrants],
                    "atm_offerings": [dict(a) for a in atms],
                    "shelf_registrations": [dict(s) for s in shelfs],
                    "warrant_count": len(warrants),
                    "has_active_atm": len(atms) > 0,
                    "has_shelf": len(shelfs) > 0
                }
        
        except Exception as e:
            logger.error("dilution_profile_error", symbol=symbol, error=str(e))
            return None
    
    async def get_warrants(self, symbol: str) -> List[Dict[str, Any]]:
        """Obtiene todos los warrants de un ticker"""
        if not self._pool:
            return []
        
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT warrant_type, exercise_price, shares_underlying,
                           expiration_date, is_exercisable, status,
                           cashless_exercise, anti_dilution
                    FROM sec_warrant_agreements
                    WHERE ticker = $1
                    ORDER BY expiration_date
                """, symbol.upper())
                
                return [dict(r) for r in rows]
        
        except Exception as e:
            logger.error("warrants_error", symbol=symbol, error=str(e))
            return []
    
    # =============================================
    # SEC FILINGS
    # =============================================
    
    async def get_sec_filings(
        self,
        symbol: str,
        form_types: List[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Obtiene SEC filings de un ticker.
        
        Args:
            symbol: Ticker symbol
            form_types: Lista de tipos (8-K, 10-K, S-1, etc.)
            limit: Maximo de resultados
        """
        if not self._pool:
            return []
        
        try:
            async with self._pool.acquire() as conn:
                if form_types:
                    rows = await conn.fetch("""
                        SELECT form_type, filing_date, accession_number,
                               primary_document, description
                        FROM sec_filings
                        WHERE ticker = $1 AND form_type = ANY($2)
                        ORDER BY filing_date DESC
                        LIMIT $3
                    """, symbol.upper(), form_types, limit)
                else:
                    rows = await conn.fetch("""
                        SELECT form_type, filing_date, accession_number,
                               primary_document, description
                        FROM sec_filings
                        WHERE ticker = $1
                        ORDER BY filing_date DESC
                        LIMIT $2
                    """, symbol.upper(), limit)
                
                return [dict(r) for r in rows]
        
        except Exception as e:
            logger.error("sec_filings_error", symbol=symbol, error=str(e))
            return []
    
    # =============================================
    # MARKET DATA DAILY
    # =============================================
    
    async def get_daily_bars(
        self,
        symbol: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Obtiene barras diarias de la base de datos local.
        Mas rapido que Polygon para datos que ya tenemos.
        """
        if not self._pool:
            return []
        
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT trading_date, symbol, open, high, low, close, volume, vwap
                    FROM market_data_daily
                    WHERE symbol = $1
                    ORDER BY trading_date DESC
                    LIMIT $2
                """, symbol.upper(), days)
                
                return [
                    {
                        "date": r["trading_date"].isoformat(),
                        "symbol": r["symbol"],
                        "open": float(r["open"]),
                        "high": float(r["high"]),
                        "low": float(r["low"]),
                        "close": float(r["close"]),
                        "volume": int(r["volume"]),
                        "vwap": float(r["vwap"]) if r["vwap"] else None
                    }
                    for r in rows
                ]
        
        except Exception as e:
            logger.error("daily_bars_error", symbol=symbol, error=str(e))
            return []
    
    # =============================================
    # TICKERS WITH DILUTION
    # =============================================
    
    async def get_tickers_with_warrants(self, min_warrants: int = 1) -> List[Dict[str, Any]]:
        """Obtiene tickers que tienen warrants activos"""
        if not self._pool:
            return []
        
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT p.ticker, p.company_name, p.shares_outstanding,
                           COUNT(w.id) as warrant_count,
                           SUM(w.shares_underlying) as total_warrant_shares
                    FROM sec_dilution_profiles p
                    JOIN sec_warrant_agreements w ON p.ticker = w.ticker
                    WHERE w.status = 'active'
                    GROUP BY p.ticker, p.company_name, p.shares_outstanding
                    HAVING COUNT(w.id) >= $1
                    ORDER BY warrant_count DESC
                """, min_warrants)
                
                return [dict(r) for r in rows]
        
        except Exception as e:
            logger.error("tickers_with_warrants_error", error=str(e))
            return []
    
    async def get_tickers_with_atm(self) -> List[Dict[str, Any]]:
        """Obtiene tickers con ATM offerings activos"""
        if not self._pool:
            return []
        
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT p.ticker, p.company_name, 
                           a.remaining_capacity, a.total_authorized, a.total_sold
                    FROM sec_dilution_profiles p
                    JOIN sec_atm_offerings a ON p.ticker = a.ticker
                    WHERE a.status = 'active'
                    ORDER BY a.remaining_capacity DESC
                """)
                
                return [dict(r) for r in rows]
        
        except Exception as e:
            logger.error("tickers_with_atm_error", error=str(e))
            return []

