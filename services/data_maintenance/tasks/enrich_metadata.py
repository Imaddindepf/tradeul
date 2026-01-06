"""
Enrich Metadata Task
Enriquece metadata de tickers: market cap, float, sector, industry

Usa Polygon como fuente principal y FMP como fallback.
"""

import asyncio
import os
import sys
sys.path.append('/app')

from datetime import date
from typing import Dict, List, Optional
import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.utils.polygon_helpers import get_free_float_with_fallback

# API Keys desde environment
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
FMP_API_KEY = os.getenv("FMP_API_KEY", "CKIRTsvk5eIpetoB8FbvOuw2wW8kNJ5B")

logger = get_logger(__name__)


class EnrichMetadataTask:
    """
    Tarea: Enriquecer metadata de tickers
    
    - Market cap
    - Free float (from Polygon /stocks/vX/float)
    - Free float percent
    - Shares outstanding
    - Sector
    - Industry
    - Description
    - CIK
    - Beta
    
    Flujo:
    1. Obtener datos de Polygon
    2. Si faltan campos críticos, intentar con FMP
    3. Actualizar BD con datos combinados
    """
    
    name = "metadata_enrich"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar enriquecimiento de metadata
        
        Args:
            target_date: Fecha objetivo (no usado, metadata es actual)
        
        Returns:
            Dict con resultado
        """
        logger.info("metadata_enrich_task_starting")
        
        try:
            # Obtener símbolos que necesitan enriquecimiento
            symbols = await self._get_symbols_to_enrich()
            
            if not symbols:
                logger.info("no_symbols_need_enrichment")
                return {
                    "success": True,
                    "symbols_processed": 0,
                    "enriched": 0,
                    "message": "No symbols need enrichment"
                }
            
            logger.info(
                "metadata_enriching_symbols",
                count=len(symbols)
            )
            
            # Enriquecer en paralelo con alta concurrencia
            async with httpx.AsyncClient(timeout=15.0) as client:
                enriched_count = 0
                failed_count = 0
                polygon_only = 0
                fmp_fallback_used = 0
                processed = 0
                semaphore = asyncio.Semaphore(30)  # Alta concurrencia
                
                async def enrich_with_semaphore(symbol: str):
                    nonlocal polygon_only, fmp_fallback_used, processed
                    async with semaphore:
                        result, used_fmp = await self._enrich_symbol(client, symbol)
                        if result and used_fmp:
                            fmp_fallback_used += 1
                        elif result:
                            polygon_only += 1
                        processed += 1
                        if processed % 500 == 0:
                            logger.info("enrich_progress", processed=processed, total=len(symbols))
                        return result
                
                tasks = [enrich_with_semaphore(sym) for sym in symbols]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if result is True:
                        enriched_count += 1
                    elif isinstance(result, Exception):
                        failed_count += 1
            
            logger.info(
                "metadata_enrich_task_completed",
                symbols_processed=len(symbols),
                enriched=enriched_count,
                failed=failed_count,
                polygon_only=polygon_only,
                fmp_fallback_used=fmp_fallback_used
            )
            
            return {
                "success": True,
                "symbols_processed": len(symbols),
                "enriched": enriched_count,
                "failed": failed_count,
                "polygon_only": polygon_only,
                "fmp_fallback_used": fmp_fallback_used
            }
        
        except Exception as e:
            logger.error(
                "metadata_enrich_task_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _get_symbols_to_enrich(self, limit: int = 15000) -> List[str]:
        """
        Obtener símbolos que necesitan enriquecimiento
        
        NOTA: Esta tarea ahora solo se usa como FALLBACK.
        El refresh principal de metadata se hace a las 1:00 AM en refresh_all_metadata.py
        
        Criterios:
        - Activos (is_actively_trading = true)
        - Sin company_name, sin exchange, sin market_cap, sin sector, sin shares_outstanding, o sin cik
        - Límite alto (15000) para cubrir todo el universo
        """
        try:
            query = """
                SELECT symbol
                FROM tickers_unified
                WHERE is_actively_trading = true
                  AND (
                    company_name IS NULL OR company_name = ''
                    OR exchange IS NULL OR exchange = ''
                    OR market_cap IS NULL
                    OR sector IS NULL
                    OR shares_outstanding IS NULL
                    OR cik IS NULL
                  )
                ORDER BY symbol
                LIMIT $1
            """
            rows = await self.db.fetch(query, limit)
            symbols = [row['symbol'] for row in rows]
            
            logger.info(
                "symbols_to_enrich_found",
                count=len(symbols)
            )
            
            return symbols
        
        except Exception as e:
            logger.error("failed_to_get_symbols_to_enrich", error=str(e))
            return []
    
    async def _enrich_symbol(self, client: httpx.AsyncClient, symbol: str) -> tuple[bool, bool]:
        """
        Enriquecer un símbolo con datos de Polygon + FMP fallback
        
        Returns:
            Tuple (success: bool, used_fmp_fallback: bool)
        """
        used_fmp = False
        
        try:
            # 1. Intentar Polygon primero
            polygon_data = await self._fetch_from_polygon(client, symbol)
            
            # 2. Extraer campos de Polygon
            company_name = polygon_data.get('name') if polygon_data else None
            exchange = polygon_data.get('primary_exchange') if polygon_data else None
            market_cap = polygon_data.get('market_cap') if polygon_data else None
            shares_outstanding = (
                polygon_data.get('share_class_shares_outstanding') or 
                polygon_data.get('weighted_shares_outstanding')
            ) if polygon_data else None
            sector = polygon_data.get('sic_description') if polygon_data else None
            industry = polygon_data.get('sic_description') if polygon_data else None
            cik = polygon_data.get('cik') if polygon_data else None
            description = polygon_data.get('description') if polygon_data else None
            homepage_url = polygon_data.get('homepage_url') if polygon_data else None
            total_employees = polygon_data.get('total_employees') if polygon_data else None
            ticker_type = polygon_data.get('type') if polygon_data else None
            
            # 2.5 Obtener FREE FLOAT (Polygon primero, FMP fallback)
            # Polygon solo tiene datos para CS, FMP tiene para más tipos
            free_float = None
            free_float_percent = None
            free_float_data = await get_free_float_with_fallback(symbol)
            if free_float_data:
                free_float = free_float_data.get('free_float')
                free_float_percent = free_float_data.get('free_float_percent')
                logger.debug(
                    "free_float_obtained",
                    symbol=symbol,
                    free_float=free_float,
                    source=free_float_data.get('source')
                )
            
            # 3. Si faltan campos críticos, usar FMP como fallback
            needs_fmp = (
                company_name is None or
                exchange is None or
                market_cap is None or 
                shares_outstanding is None or 
                sector is None or
                cik is None
            )
            
            fmp_data = None
            if needs_fmp:
                fmp_data = await self._fetch_from_fmp(client, symbol)
                if fmp_data:
                    used_fmp = True
                    # Completar campos faltantes con FMP
                    company_name = company_name or fmp_data.get('companyName')
                    exchange = exchange or fmp_data.get('exchange')
                    market_cap = market_cap or fmp_data.get('mktCap')
                    shares_outstanding = shares_outstanding or fmp_data.get('sharesOutstanding')
                    sector = sector or fmp_data.get('sector')
                    industry = industry or fmp_data.get('industry')
                    cik = cik or fmp_data.get('cik')
                    description = description or fmp_data.get('description')
                    homepage_url = homepage_url or fmp_data.get('website')
                    total_employees = total_employees or self._safe_int(fmp_data.get('fullTimeEmployees'))
            
            # 4. Obtener beta de FMP si no lo tenemos
            beta = None
            if fmp_data:
                beta = fmp_data.get('beta')
            
            # 5. Actualizar BD
            if company_name or market_cap or shares_outstanding or sector or cik:
                await self._update_metadata(
                    symbol=symbol,
                    company_name=company_name,
                    exchange=exchange,
                    market_cap=market_cap,
                    free_float=free_float,
                    free_float_percent=free_float_percent,
                    shares_outstanding=shares_outstanding,
                    sector=sector,
                    industry=industry,
                    cik=cik,
                    description=description,
                    homepage_url=homepage_url,
                    total_employees=total_employees,
                    beta=beta
                )
                
                logger.debug(
                    "symbol_enriched",
                    symbol=symbol,
                    has_company_name=company_name is not None,
                    has_exchange=exchange is not None,
                    has_market_cap=market_cap is not None,
                    has_sector=sector is not None,
                    used_fmp=used_fmp
                )
                
                return True, used_fmp
            
            return False, False
        
        except Exception as e:
            logger.debug(f"Failed to enrich {symbol}: {e}")
            return False, False
    
    async def _fetch_from_polygon(self, client: httpx.AsyncClient, symbol: str, retries: int = 2) -> Optional[Dict]:
        """Obtener detalles del ticker desde Polygon con reintentos"""
        url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
        
        for attempt in range(retries + 1):
            try:
                resp = await client.get(
                    url,
                    params={"apiKey": POLYGON_API_KEY}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get('results')
                elif resp.status_code == 429:
                    await asyncio.sleep(1 + attempt)
                elif resp.status_code == 404:
                    return None  # No reintentar 404
            except Exception as e:
                if attempt == retries:
                    logger.debug(f"Polygon error for {symbol}: {e}")
                await asyncio.sleep(0.5)
        
        return None
    
    async def _fetch_from_fmp(self, client: httpx.AsyncClient, symbol: str, retries: int = 2) -> Optional[Dict]:
        """Obtener detalles del ticker desde FMP (fallback) con reintentos"""
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        
        for attempt in range(retries + 1):
            try:
                resp = await client.get(
                    url,
                    params={"apikey": FMP_API_KEY}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        return data[0]
                    return None
                elif resp.status_code == 429:
                    await asyncio.sleep(1 + attempt)
                elif resp.status_code == 404:
                    return None
            except Exception as e:
                if attempt == retries:
                    logger.debug(f"FMP error for {symbol}: {e}")
                await asyncio.sleep(0.5)
        
        return None
    
    async def _update_metadata(
        self,
        symbol: str,
        company_name: Optional[str] = None,
        exchange: Optional[str] = None,
        market_cap: Optional[float] = None,
        free_float: Optional[int] = None,
        free_float_percent: Optional[float] = None,
        shares_outstanding: Optional[int] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        cik: Optional[str] = None,
        description: Optional[str] = None,
        homepage_url: Optional[str] = None,
        total_employees: Optional[int] = None,
        beta: Optional[float] = None
    ):
        """Actualizar metadata en tickers_unified
        
        NOTA: Esta tarea ahora solo se usa como FALLBACK para tickers nuevos.
        El refresh principal de metadata se hace a las 1:00 AM en refresh_all_metadata.py
        """
        query = """
            INSERT INTO tickers_unified (
                symbol, company_name, exchange, market_cap, free_float, free_float_percent,
                shares_outstanding, sector, industry, cik, description, homepage_url,
                total_employees, beta, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
            ON CONFLICT (symbol)
            DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, tickers_unified.company_name),
                exchange = COALESCE(EXCLUDED.exchange, tickers_unified.exchange),
                market_cap = COALESCE(EXCLUDED.market_cap, tickers_unified.market_cap),
                free_float = COALESCE(EXCLUDED.free_float, tickers_unified.free_float),
                free_float_percent = COALESCE(EXCLUDED.free_float_percent, tickers_unified.free_float_percent),
                shares_outstanding = COALESCE(EXCLUDED.shares_outstanding, tickers_unified.shares_outstanding),
                sector = COALESCE(EXCLUDED.sector, tickers_unified.sector),
                industry = COALESCE(EXCLUDED.industry, tickers_unified.industry),
                cik = COALESCE(EXCLUDED.cik, tickers_unified.cik),
                description = COALESCE(EXCLUDED.description, tickers_unified.description),
                homepage_url = COALESCE(EXCLUDED.homepage_url, tickers_unified.homepage_url),
                total_employees = COALESCE(EXCLUDED.total_employees, tickers_unified.total_employees),
                beta = COALESCE(EXCLUDED.beta, tickers_unified.beta),
                updated_at = NOW()
        """
        
        try:
            await self.db.execute(
                query,
                symbol, 
                company_name,
                exchange,
                int(market_cap) if market_cap else None,
                int(free_float) if free_float else None,
                float(free_float_percent) if free_float_percent else None,
                int(shares_outstanding) if shares_outstanding else None,
                sector, 
                industry,
                cik,
                description,
                homepage_url,
                int(total_employees) if total_employees else None,
                float(beta) if beta else None
            )
        except Exception as e:
            logger.error(
                "failed_to_update_metadata",
                symbol=symbol,
                error=str(e)
            )
    
    def _safe_int(self, value) -> Optional[int]:
        """Convertir valor a int de forma segura"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                # Limpiar string de caracteres no numéricos
                value = ''.join(filter(str.isdigit, value))
            return int(value) if value else None
        except (ValueError, TypeError):
            return None
