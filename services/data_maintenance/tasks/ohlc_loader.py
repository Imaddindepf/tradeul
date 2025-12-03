"""
OHLC Loader
===========

Carga datos OHLC diarios de Polygon API para una fecha específica.

Lógica simple:
1. Verificar si el día ya tiene datos completos (>= 10,000 símbolos)
2. Si sí: skip (ya está cargado)
3. Si no: cargar desde Polygon API

NO intenta cargar múltiples días ni "detectar días faltantes".
El scheduler se encarga de llamar con la fecha correcta.
"""

import asyncio
from datetime import date
from typing import Dict, List
import httpx

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

# Mínimo de símbolos para considerar un día "completo"
MIN_SYMBOLS_COMPLETE = 10000


class OHLCLoader:
    """
    Cargador de datos OHLC diarios
    """
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def load_day(self, target_date: date) -> Dict:
        """
        Cargar datos OHLC para un día específico
        
        Args:
            target_date: Fecha a cargar
            
        Returns:
            Dict con resultado
        """
        logger.info("ohlc_loader_starting", target_date=str(target_date))
        
        # 1. Verificar si ya está completo
        existing_count = await self._count_existing(target_date)
        
        if existing_count >= MIN_SYMBOLS_COMPLETE:
            logger.info(
                "ohlc_day_already_complete",
                target_date=str(target_date),
                existing_count=existing_count
            )
            return {
                "success": True,
                "action": "skipped",
                "reason": "Day already complete",
                "existing_count": existing_count
            }
        
        # 2. Obtener lista de símbolos activos
        symbols = await self._get_active_symbols()
        
        if not symbols:
            return {
                "success": False,
                "error": "No active symbols found"
            }
        
        logger.info(
            "ohlc_loading_day",
            target_date=str(target_date),
            symbols_count=len(symbols),
            existing_count=existing_count
        )
        
        # 3. Cargar datos desde Polygon
        inserted = 0
        failed = 0
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Procesar en batches con concurrencia limitada
            semaphore = asyncio.Semaphore(20)
            
            async def load_symbol(symbol: str) -> int:
                async with semaphore:
                    return await self._load_symbol_ohlc(client, symbol, target_date)
            
            tasks = [load_symbol(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                elif isinstance(result, int):
                    inserted += result
                else:
                    failed += 1
        
        # 4. Verificar resultado
        final_count = await self._count_existing(target_date)
        success = final_count >= MIN_SYMBOLS_COMPLETE
        
        logger.info(
            "ohlc_loader_completed",
            target_date=str(target_date),
            records_inserted=inserted,
            failed=failed,
            final_count=final_count,
            success=success
        )
        
        return {
            "success": success,
            "records_inserted": inserted,
            "symbols_failed": failed,
            "final_count": final_count,
            "target_date": str(target_date)
        }
    
    async def _count_existing(self, target_date: date) -> int:
        """Contar registros existentes para una fecha"""
        query = """
            SELECT COUNT(DISTINCT symbol) as count
            FROM market_data_daily
            WHERE trading_date = $1
        """
        rows = await self.db.fetch(query, target_date)
        return rows[0]["count"] if rows else 0
    
    async def _get_active_symbols(self) -> List[str]:
        """Obtener símbolos activos"""
        query = """
            SELECT symbol
            FROM tickers_unified
            WHERE is_actively_trading = true
            ORDER BY symbol
        """
        rows = await self.db.fetch(query)
        return [row["symbol"] for row in rows]
    
    async def _load_symbol_ohlc(
        self,
        client: httpx.AsyncClient,
        symbol: str,
        target_date: date
    ) -> int:
        """Cargar OHLC para un símbolo"""
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{target_date}/{target_date}"
        
        try:
            resp = await client.get(
                url,
                params={
                    "adjusted": "true",
                    "apiKey": settings.POLYGON_API_KEY
                }
            )
            
            if resp.status_code != 200:
                return 0
            
            data = resp.json()
            results = data.get("results", [])
            
            if not results:
                return 0
            
            bar = results[0]
            
            # Insertar en base de datos
            query = """
                INSERT INTO market_data_daily 
                (trading_date, symbol, open, high, low, close, volume, vwap, trades_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (trading_date, symbol) 
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    vwap = EXCLUDED.vwap,
                    trades_count = EXCLUDED.trades_count
            """
            
            await self.db.execute(
                query,
                target_date,
                symbol,
                bar["o"],
                bar["h"],
                bar["l"],
                bar["c"],
                bar["v"],
                bar.get("vw"),
                bar.get("n")
            )
            
            return 1
            
        except Exception as e:
            logger.debug(f"Failed to load OHLC for {symbol}: {e}")
            return 0

