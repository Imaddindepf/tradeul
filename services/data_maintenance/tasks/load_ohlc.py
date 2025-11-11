"""
Load OHLC Daily Task
Carga datos OHLC diarios desde Polygon para cálculo de ATR
"""

import asyncio
import sys
sys.path.append('/app')

from datetime import date, timedelta
from typing import Dict
import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

# Importar lógica del script existente
from scripts.load_daily_ohlc import (
    get_trading_days,
    fetch_daily_bars,
    POLYGON_API_KEY,
    MARKET_HOLIDAYS
)

logger = get_logger(__name__)


class LoadOHLCTask:
    """
    Tarea: Cargar datos OHLC diarios
    
    - Carga últimos 30 días de OHLC para cálculo de ATR
    - Usa script existente load_daily_ohlc.py
    - Actualiza market_data_daily en TimescaleDB
    """
    
    name = "ohlc_daily"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar carga de OHLC
        
        Args:
            target_date: Fecha objetivo (normalmente día anterior)
        
        Returns:
            Dict con resultado: success, records_inserted, error
        """
        logger.info(
            "ohlc_task_starting",
            target_date=target_date.isoformat()
        )
        
        try:
            # Obtener últimos 30 días de trading
            trading_days = get_trading_days(30)
            
            # Obtener símbolos activos del universo
            symbols = await self._get_active_symbols()
            
            if not symbols:
                logger.warning("no_symbols_found")
                return {
                    "success": False,
                    "error": "No symbols found in universe"
                }
            
            logger.info(
                "ohlc_symbols_loaded",
                count=len(symbols),
                days=len(trading_days),
                start=trading_days[0].isoformat(),
                end=trading_days[-1].isoformat()
            )
            
            # Procesar en paralelo con límite de concurrencia
            async with httpx.AsyncClient() as client:
                records_inserted = 0
                semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests
                
                async def load_with_semaphore(symbol: str):
                    async with semaphore:
                        return await self._load_symbol(client, symbol, trading_days)
                
                tasks = [load_with_semaphore(sym) for sym in symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, int):
                        records_inserted += result
            
            logger.info(
                "ohlc_task_completed",
                symbols_processed=len(symbols),
                records_inserted=records_inserted
            )
            
            return {
                "success": True,
                "symbols_processed": len(symbols),
                "records_inserted": records_inserted
            }
        
        except Exception as e:
            logger.error(
                "ohlc_task_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_active_symbols(self) -> list:
        """Obtener símbolos activos del universo"""
        try:
            query = """
                SELECT DISTINCT symbol 
                FROM ticker_universe 
                WHERE status = 'active'
                ORDER BY symbol
            """
            rows = await self.db.fetch(query)
            return [row['symbol'] for row in rows]
        
        except Exception as e:
            logger.error("failed_to_get_symbols", error=str(e))
            return []
    
    async def _load_symbol(
        self, 
        client: httpx.AsyncClient, 
        symbol: str, 
        trading_days: list
    ) -> int:
        """Cargar OHLC para un símbolo"""
        start_date = trading_days[0]
        end_date = trading_days[-1]
        
        bars = await self._fetch_bars(client, symbol, start_date, end_date)
        if not bars:
            return 0
        
        # Preparar datos para inserción
        records = []
        for bar in bars:
            bar_date = date.fromtimestamp(bar['t'] / 1000)
            records.append((
                bar_date,
                symbol,
                bar['o'],  # open
                bar['h'],  # high
                bar['l'],  # low
                bar['c'],  # close
                bar['v'],  # volume
                bar.get('vw'),  # vwap
                bar.get('n')   # trades_count
            ))
        
        # Inserción batch con ON CONFLICT (update existentes)
        query = """
            INSERT INTO market_data_daily 
            (date, symbol, open, high, low, close, volume, vwap, trades_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (date, symbol) 
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                vwap = EXCLUDED.vwap,
                trades_count = EXCLUDED.trades_count
        """
        
        try:
            await self.db.executemany(query, records)
            return len(records)
        except Exception as e:
            logger.error(
                "failed_to_insert_ohlc",
                symbol=symbol,
                error=str(e)
            )
            return 0
    
    async def _fetch_bars(
        self, 
        client: httpx.AsyncClient, 
        symbol: str, 
        start_date: date, 
        end_date: date
    ) -> list:
        """Obtener barras diarias de Polygon"""
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}"
        try:
            resp = await client.get(
                url, 
                params={"adjusted": "true", "sort": "asc", "apiKey": POLYGON_API_KEY}, 
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get('results', [])
        except Exception as e:
            logger.debug(f"Error fetching {symbol}: {e}")
        return []

