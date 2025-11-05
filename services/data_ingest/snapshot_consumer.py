"""
Snapshot Consumer
Fetches snapshots from Polygon and publishes to Redis
"""

import time
from datetime import datetime
from typing import Optional, List, Dict, Any
import httpx

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.polygon import PolygonSnapshot, PolygonSnapshotResponse
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SnapshotConsumer:
    """
    Consumes snapshots from Polygon API
    """
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.base_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
        self.api_key = settings.polygon_api_key
        
        # Statistics
        self.total_snapshots = 0
        self.total_tickers_processed = 0
        self.last_snapshot_time: Optional[datetime] = None
        self.last_snapshot_count = 0
        self.errors = 0
        self.start_time = time.time()
    
    async def consume_snapshot(self) -> int:
        """
        Fetch snapshot from Polygon and publish to Redis
        
        Returns:
            Number of tickers processed
        """
        start = time.time()
        
        try:
            logger.info("Fetching snapshot from Polygon")
            
            # Fetch snapshot
            snapshots = await self._fetch_polygon_snapshot()
            
            if not snapshots:
                logger.warning("No snapshots returned from Polygon")
                return 0
            
            # Publish to Redis
            published_count = await self._publish_snapshots(snapshots)
            
            # Update statistics
            self.total_snapshots += 1
            self.total_tickers_processed += published_count
            self.last_snapshot_time = datetime.now()
            self.last_snapshot_count = published_count
            
            elapsed = time.time() - start
            
            logger.info(
                "Snapshot consumed",
                tickers=published_count,
                elapsed_ms=int(elapsed * 1000)
            )
            
            return published_count
        
        except Exception as e:
            self.errors += 1
            logger.error("Error consuming snapshot", error=str(e))
            raise
    
    async def _fetch_polygon_snapshot(self) -> List[PolygonSnapshot]:
        """Fetch snapshot from Polygon API"""
        try:
            params = {
                "apiKey": self.api_key,
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.base_url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Parse response con tolerancia (no all-or-nothing)
                    tickers_raw = data.get("tickers", [])
                    if not isinstance(tickers_raw, list):
                        logger.warning("Unexpected response format from Polygon")
                        return []

                    parsed: List[PolygonSnapshot] = []
                    failed_parse_count = 0
                    for t in tickers_raw:
                        try:
                            parsed.append(PolygonSnapshot(**t))
                        except Exception:
                            failed_parse_count += 1

                    # Log estadística de parsing para detectar problemas reales de validación
                    logger.info(
                        "polygon_parse_stats",
                        raw_total=len(tickers_raw),
                        parsed=len(parsed),
                        failed_parse=failed_parse_count
                    )

                    return parsed
                
                elif response.status_code == 429:
                    logger.warning("Rate limited by Polygon API")
                    return []
                
                else:
                    logger.error(
                        "Error fetching from Polygon",
                        status_code=response.status_code,
                        response=response.text[:200]
                    )
                    return []
        
        except httpx.TimeoutException:
            logger.error("Timeout fetching from Polygon")
            return []
        
        except Exception as e:
            logger.error("Exception fetching from Polygon", error=str(e))
            return []
    
    async def _publish_snapshots(self, snapshots: List[PolygonSnapshot]) -> int:
        """
        NUEVO: Guarda snapshot completo en Redis key (no stream)
        
        Esto evita backlog y asegura que Scanner siempre procesa
        datos del mismo momento en tiempo.
        
        Args:
            snapshots: List of Polygon snapshots
        
        Returns:
            Number of snapshots published
        """
        try:
            # Convertir todos los snapshots a JSON con FILTRO de precio mínimo
            # IMPORTANTE: Agregar campos @property manualmente
            snapshot_list = []
            skipped_low_price = 0
            price_sources = {"lastTrade": 0, "day": 0, "prevDay": 0, "none": 0}
            raw_under_0_5 = 0  # Contador de cuántos en raw tienen precio < 0.5
            for s in snapshots:
                # Filtro temprano: descartar tickers con precio actual < 0.5
                cp = s.current_price
                # Contar cuántos del raw tienen precio < 0.5 o None (para comparar con script)
                if cp is None or cp < 0.5:
                    raw_under_0_5 += 1
                # Medir fuente de precio
                if s.lastTrade and s.lastTrade.p and s.lastTrade.p > 0:
                    price_sources["lastTrade"] += 1
                elif s.day and s.day.c and s.day.c > 0:
                    price_sources["day"] += 1
                elif s.prevDay and s.prevDay.c and s.prevDay.c > 0:
                    price_sources["prevDay"] += 1
                else:
                    price_sources["none"] += 1
                # Filtrar: descartar si precio None o < 0.5
                if cp is None or cp < 0.5:
                    skipped_low_price += 1
                    continue
                ticker_dict = s.model_dump(mode='json')
                # Agregar computed fields que no se incluyen automáticamente
                ticker_dict['current_price'] = cp
                ticker_dict['current_volume'] = s.current_volume
                snapshot_list.append(ticker_dict)
            
            # Metadata del snapshot
            snapshot_data = {
                "timestamp": datetime.now().isoformat(),
                "count": len(snapshot_list),
                "tickers": snapshot_list
            }
            
            # Guardar snapshot COMPLETO en key fijo
            # El scanner leerá de aquí cuando esté listo
            await self.redis.set(
                "snapshot:polygon:latest",
                snapshot_data,
                ttl=60  # 60 segundos (si no se procesa en 1 min, ya es viejo)
            )
            
            # Log de estadísticas de filtro por precio
            logger.info(
                "low_price_filter_applied",
                raw_total=len(snapshots),
                raw_under_0_5=raw_under_0_5,
                kept=len(snapshot_list),
                filtered_low_price=skipped_low_price,
                price_sources=price_sources
            )

            logger.debug(f"Saved complete snapshot to Redis", count=len(snapshots))
            
            return len(snapshots)
        
        except Exception as e:
            logger.error("Error saving snapshot", error=str(e))
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics"""
        uptime = time.time() - self.start_time
        
        return {
            "total_snapshots": self.total_snapshots,
            "total_tickers_processed": self.total_tickers_processed,
            "last_snapshot_time": self.last_snapshot_time.isoformat() if self.last_snapshot_time else None,
            "last_snapshot_count": self.last_snapshot_count,
            "errors": self.errors,
            "uptime_seconds": int(uptime),
            "avg_tickers_per_snapshot": (
                self.total_tickers_processed / self.total_snapshots
                if self.total_snapshots > 0 else 0
            ),
            "stream_name": settings.stream_raw_snapshots,
        }

