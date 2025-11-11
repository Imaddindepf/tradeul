"""
Enrich Metadata Task
Enriquece metadata de tickers: market cap, float, sector, industry
"""

import asyncio
import sys
sys.path.append('/app')

from datetime import date
from typing import Dict, List, Optional
import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

POLYGON_API_KEY = "vjzI76TMiepqrMZKphpfs3SA54JFkhEx"

logger = get_logger(__name__)


class EnrichMetadataTask:
    """
    Tarea: Enriquecer metadata de tickers
    
    - Market cap
    - Float shares
    - Shares outstanding
    - Sector
    - Industry
    - Description
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
            # Priorizar: sin market_cap, sin sector, actualizados hace más de 7 días
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
            
            # Enriquecer en paralelo con rate limiting
            async with httpx.AsyncClient() as client:
                enriched_count = 0
                failed_count = 0
                semaphore = asyncio.Semaphore(5)  # Max 5 concurrent (Polygon rate limit)
                
                async def enrich_with_semaphore(symbol: str):
                    async with semaphore:
                        # Rate limiting: ~5 req/s = 200ms entre requests
                        await asyncio.sleep(0.2)
                        return await self._enrich_symbol(client, symbol)
                
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
                failed=failed_count
            )
            
            return {
                "success": True,
                "symbols_processed": len(symbols),
                "enriched": enriched_count,
                "failed": failed_count
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
    
    async def _get_symbols_to_enrich(self, limit: int = 500) -> List[str]:
        """
        Obtener símbolos que necesitan enriquecimiento
        
        Criterios:
        - Activos en ticker_universe
        - Sin market_cap o sin sector
        - O metadata_updated_at > 7 días (opcional)
        """
        try:
            query = """
                SELECT tu.symbol
                FROM ticker_universe tu
                LEFT JOIN ticker_metadata tm ON tu.symbol = tm.symbol
                WHERE tu.status = 'active'
                  AND (
                    tm.symbol IS NULL
                    OR tm.market_cap IS NULL
                    OR tm.sector IS NULL
                  )
                ORDER BY tu.symbol
                LIMIT $1
            """
            rows = await self.db.fetch(query, limit)
            return [row['symbol'] for row in rows]
        
        except Exception as e:
            logger.error("failed_to_get_symbols_to_enrich", error=str(e))
            return []
    
    async def _enrich_symbol(self, client: httpx.AsyncClient, symbol: str) -> bool:
        """Enriquecer un símbolo con datos de Polygon"""
        try:
            # Fetch ticker details from Polygon
            details = await self._fetch_ticker_details(client, symbol)
            
            if not details:
                return False
            
            # Extract metadata
            market_cap = details.get('market_cap')
            weighted_shares_outstanding = details.get('weighted_shares_outstanding')
            share_class_shares_outstanding = details.get('share_class_shares_outstanding')
            
            # Calcular float (aproximación)
            # Float = shares outstanding - restricted shares
            # Como no tenemos restricted, usamos share_class si está disponible
            float_shares = share_class_shares_outstanding or weighted_shares_outstanding
            
            sector = details.get('sic_description') or details.get('sector')
            industry = details.get('industry')
            description = details.get('description')
            
            # Update database
            await self._update_metadata(
                symbol=symbol,
                market_cap=market_cap,
                float_shares=float_shares,
                shares_outstanding=weighted_shares_outstanding,
                sector=sector,
                industry=industry,
                description=description
            )
            
            logger.debug(
                "symbol_enriched",
                symbol=symbol,
                has_market_cap=market_cap is not None,
                has_sector=sector is not None
            )
            
            return True
        
        except Exception as e:
            logger.debug(f"Failed to enrich {symbol}: {e}")
            return False
    
    async def _fetch_ticker_details(self, client: httpx.AsyncClient, symbol: str) -> Optional[Dict]:
        """Obtener detalles del ticker desde Polygon"""
        url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
        
        try:
            resp = await client.get(
                url,
                params={"apiKey": POLYGON_API_KEY},
                timeout=10.0
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get('results')
            elif resp.status_code == 429:
                # Rate limited
                logger.warning(f"Rate limited on {symbol}, waiting...")
                await asyncio.sleep(1)
                return None
        
        except Exception as e:
            logger.debug(f"Error fetching details for {symbol}: {e}")
        
        return None
    
    async def _update_metadata(
        self,
        symbol: str,
        market_cap: Optional[float],
        float_shares: Optional[int],
        shares_outstanding: Optional[int],
        sector: Optional[str],
        industry: Optional[str],
        description: Optional[str]
    ):
        """Actualizar metadata en ticker_metadata"""
        query = """
            INSERT INTO ticker_metadata (
                symbol, market_cap, float_shares, shares_outstanding,
                sector, industry, description, metadata_updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
            ON CONFLICT (symbol)
            DO UPDATE SET
                market_cap = COALESCE(EXCLUDED.market_cap, ticker_metadata.market_cap),
                float_shares = COALESCE(EXCLUDED.float_shares, ticker_metadata.float_shares),
                shares_outstanding = COALESCE(EXCLUDED.shares_outstanding, ticker_metadata.shares_outstanding),
                sector = COALESCE(EXCLUDED.sector, ticker_metadata.sector),
                industry = COALESCE(EXCLUDED.industry, ticker_metadata.industry),
                description = COALESCE(EXCLUDED.description, ticker_metadata.description),
                metadata_updated_at = NOW()
        """
        
        try:
            await self.db.execute(
                query,
                symbol, market_cap, float_shares, shares_outstanding,
                sector, industry, description
            )
        except Exception as e:
            logger.error(
                "failed_to_update_metadata",
                symbol=symbol,
                error=str(e)
            )

