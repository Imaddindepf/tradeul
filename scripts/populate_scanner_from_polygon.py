#!/usr/bin/env python3
"""
Script para poblar las tablas del scanner usando Polygon Full Market Snapshot

Este script imita el proceso del scanner pero usando snapshots de Polygon
directamente, útil para poblar datos durante el fin de semana cuando el scanner
no está ejecutándose pero Polygon tiene snapshots disponibles hasta el domingo.

Uso:
    python scripts/populate_scanner_from_polygon.py
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import httpx
import json

# Agregar path para imports
sys.path.append('/opt/tradeul')
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.polygon import PolygonSnapshot, PolygonSnapshotResponse
from shared.models.scanner import ScannerTicker, FilterConfig, TickerMetadata
from shared.enums.market_session import MarketSession
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

# Import ScannerEngine desde el servicio
# El scanner está en services/scanner/scanner_engine.py
# Intentar diferentes paths según si estamos en contenedor o host
import importlib.util
scanner_engine_paths = [
    '/app/scanner_engine.py',  # Contenedor: archivo directo
    '/opt/tradeul/services/scanner/scanner_engine.py',  # Host
    '/app/services/scanner/scanner_engine.py',  # Contenedor: path completo
]

ScannerEngine = None
for path in scanner_engine_paths:
    try:
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("scanner_engine", path)
            scanner_engine_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(scanner_engine_module)
            ScannerEngine = scanner_engine_module.ScannerEngine
            break
    except Exception as e:
        continue

if ScannerEngine is None:
    # Fallback: import directo si está en el path
    try:
        from scanner_engine import ScannerEngine
    except ImportError:
        raise ImportError("Could not import ScannerEngine. Make sure scanner_engine.py is accessible.")

logger = get_logger(__name__)


class PolygonSnapshotPopulator:
    """
    Poblador de datos del scanner usando Polygon Full Market Snapshot
    """
    
    def __init__(self):
        self.redis_client: Optional[RedisClient] = None
        self.timescale_client: Optional[TimescaleClient] = None
        self.scanner_engine: Optional[ScannerEngine] = None
        self.polygon_api_key = settings.POLYGON_API_KEY
        self.polygon_base_url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
    
    async def initialize(self):
        """Inicializar clientes y scanner engine"""
        logger.info("Initializing Polygon Snapshot Populator...")
        
        # Inicializar Redis
        self.redis_client = RedisClient()
        await self.redis_client.connect()
        logger.info("✅ Redis connected")
        
        # Inicializar TimescaleDB
        self.timescale_client = TimescaleClient()
        await self.timescale_client.connect()
        logger.info("✅ TimescaleDB connected")
        
        # Inicializar ScannerEngine (para usar sus filtros y lógica)
        self.scanner_engine = ScannerEngine(
            redis_client=self.redis_client,
            timescale_client=self.timescale_client,
            snapshot_manager=None
        )
        
        # Cargar filtros
        await self.scanner_engine.reload_filters()
        logger.info(f"✅ Loaded {len(self.scanner_engine.filters)} filters")
        
        # Determinar sesión de mercado actual
        await self.scanner_engine._update_market_session()
        logger.info(f"✅ Market session: {self.scanner_engine.current_session.value}")
    
    async def fetch_polygon_snapshot(self) -> List[PolygonSnapshot]:
        """
        Obtener Full Market Snapshot de Polygon
        """
        try:
            logger.info("Fetching Full Market Snapshot from Polygon...")
            
            params = {
                "apiKey": self.polygon_api_key,
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(self.polygon_base_url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Parsear respuesta
                    tickers_raw = data.get("tickers", [])
                    if not isinstance(tickers_raw, list):
                        logger.warning("Unexpected response format from Polygon")
                        return []
                    
                    parsed: List[PolygonSnapshot] = []
                    failed_parse_count = 0
                    
                    for t in tickers_raw:
                        try:
                            parsed.append(PolygonSnapshot(**t))
                        except Exception as e:
                            failed_parse_count += 1
                            if failed_parse_count <= 5:  # Log primeros errores
                                logger.debug(f"Failed to parse ticker: {e}")
                    
                    logger.info(
                        "polygon_snapshot_fetched",
                        total=len(tickers_raw),
                        parsed=len(parsed),
                        failed=failed_parse_count
                    )
                    
                    return parsed
                
                elif response.status_code == 429:
                    logger.error("Rate limited by Polygon API")
                    return []
                
                else:
                    logger.error(
                        "Error fetching from Polygon",
                        status_code=response.status_code,
                        response=response.text[:500]
                    )
                    return []
        
        except httpx.TimeoutException:
            logger.error("Timeout fetching from Polygon")
            return []
        
        except Exception as e:
            logger.error("Exception fetching from Polygon", error=str(e))
            return []
    
    async def enrich_snapshot_with_rvol_atr(
        self,
        snapshot: PolygonSnapshot
    ) -> Dict[str, Any]:
        """
        Enriquecer snapshot con RVOL y ATR desde Redis
        """
        symbol = snapshot.ticker
        enriched = {
            'snapshot': snapshot,
            'rvol': None,
            'atr': None,
            'atr_percent': None,
            'intraday_high': None,
            'intraday_low': None
        }
        
        # 1. Intentar obtener RVOL desde Redis (si Analytics ya lo calculó)
        try:
            rvol_hash = await self.redis_client.client.hget("rvol:current_slot", symbol)
            if rvol_hash:
                enriched['rvol'] = float(rvol_hash)
        except Exception as e:
            logger.debug(f"Could not get RVOL for {symbol}: {e}")
        
        # 2. Si no hay RVOL en Redis, calcular uno simplificado
        if enriched['rvol'] is None:
            # Calcular RVOL simplificado: volume_today / avg_volume_30d
            volume_today = snapshot.current_volume
            if volume_today and volume_today > 0:
                # Intentar obtener avg_volume_30d desde metadata
                metadata = await self._get_metadata(symbol)
                if metadata and metadata.avg_volume_30d and metadata.avg_volume_30d > 0:
                    enriched['rvol'] = round(volume_today / metadata.avg_volume_30d, 2)
        
        # 3. Obtener ATR desde Redis (si Analytics lo calculó)
        try:
            atr_key = f"atr:{symbol}"
            atr_data = await self.redis_client.get(atr_key, deserialize=True)
            if atr_data and isinstance(atr_data, dict):
                enriched['atr'] = atr_data.get('atr')
                enriched['atr_percent'] = atr_data.get('atr_percent')
        except Exception as e:
            logger.debug(f"Could not get ATR for {symbol}: {e}")
        
        # 4. Obtener intraday high/low desde snapshot o day data
        if snapshot.day:
            enriched['intraday_high'] = snapshot.day.h
            enriched['intraday_low'] = snapshot.day.l
        
        return enriched
    
    async def _get_metadata(self, symbol: str) -> Optional[TickerMetadata]:
        """Obtener metadata desde Redis o BD"""
        try:
            # Intentar Redis primero
            key = f"{settings.key_prefix_metadata}:ticker:{symbol}"
            data = await self.redis_client.get(key, deserialize=True)
            
            if data:
                # Parsear address si viene como string JSON
                if 'address' in data and isinstance(data['address'], str):
                    try:
                        data['address'] = json.loads(data['address'])
                    except (json.JSONDecodeError, TypeError):
                        data['address'] = None
                
                return TickerMetadata(**data)
            
            # Fallback a BD
            row = await self.timescale_client.get_ticker_metadata(symbol)
            if row:
                row_dict = dict(row)
                # Parsear address si viene como string JSON desde BD
                if 'address' in row_dict and isinstance(row_dict['address'], str):
                    try:
                        row_dict['address'] = json.loads(row_dict['address'])
                    except (json.JSONDecodeError, TypeError):
                        row_dict['address'] = None
                
                metadata = TickerMetadata(**row_dict)
                
                # Guardar en cache
                await self.redis_client.set(
                    key,
                    metadata.model_dump(mode='json'),
                    ttl=3600
                )
                
                return metadata
            
            return None
        
        except Exception as e:
            logger.debug(f"Error getting metadata for {symbol}: {e}")
            return None
    
    async def process_snapshots(
        self,
        snapshots: List[PolygonSnapshot]
    ) -> List[ScannerTicker]:
        """
        Procesar snapshots igual que el scanner
        """
        logger.info(f"Processing {len(snapshots)} snapshots...")
        
        # 1. Enriquecer snapshots con RVOL y ATR
        enriched_snapshots = []
        for snapshot in snapshots:
            enriched = await self.enrich_snapshot_with_rvol_atr(snapshot)
            enriched_snapshots.append((
                enriched['snapshot'],
                enriched['rvol'],
                {
                    'atr': enriched['atr'],
                    'atr_percent': enriched['atr_percent'],
                    'intraday_high': enriched['intraday_high'],
                    'intraday_low': enriched['intraday_low']
                }
            ))
        
        logger.info(f"Enriched {len(enriched_snapshots)} snapshots")
        
        # 2. Usar el método optimizado del scanner para procesar
        filtered_tickers = await self.scanner_engine._process_snapshots_optimized(
            enriched_snapshots
        )
        
        logger.info(f"Filtered {len(filtered_tickers)} tickers")
        
        return filtered_tickers
    
    async def save_to_redis(self, tickers: List[ScannerTicker]):
        """
        Guardar tickers filtrados en Redis igual que el scanner
        """
        if not tickers:
            logger.warning("No tickers to save")
            return
        
        # Usar el método del scanner para guardar
        await self.scanner_engine._save_filtered_tickers_to_cache(tickers)
        
        # También categorizar (opcional, pero útil)
        await self.scanner_engine.categorize_filtered_tickers(tickers)
        
        logger.info(f"✅ Saved {len(tickers)} tickers to Redis cache")
    
    async def run(self):
        """
        Ejecutar el proceso completo
        """
        try:
            # 1. Inicializar
            await self.initialize()
            
            # 2. Obtener snapshot de Polygon
            snapshots = await self.fetch_polygon_snapshot()
            
            if not snapshots:
                logger.error("No snapshots fetched from Polygon")
                return
            
            # 3. Procesar snapshots (filtrar, enriquecer, score)
            filtered_tickers = await self.process_snapshots(snapshots)
            
            if not filtered_tickers:
                logger.warning("No tickers passed filters")
                return
            
            # 4. Guardar en Redis
            await self.save_to_redis(filtered_tickers)
            
            logger.info(
                "✅ Scanner data populated successfully",
                total_snapshots=len(snapshots),
                filtered_tickers=len(filtered_tickers),
                session=self.scanner_engine.current_session.value
            )
        
        except Exception as e:
            logger.error("Error running populator", error=str(e), exc_info=True)
            raise
    
    async def cleanup(self):
        """Cerrar conexiones"""
        if self.redis_client:
            await self.redis_client.disconnect()
        if self.timescale_client:
            await self.timescale_client.disconnect()


async def main():
    """Punto de entrada principal"""
    populator = PolygonSnapshotPopulator()
    
    try:
        await populator.run()
    finally:
        await populator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

