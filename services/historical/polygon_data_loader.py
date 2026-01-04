"""
Polygon Data Loader
Carga todos los datos históricos desde Polygon (sin depender de FMP batch)

NOTA: Usa http_clients.polygon con connection pooling.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from statistics import mean

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.polygon import PolygonTickerDetails
from shared.models.scanner import TickerMetadata
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.utils.polygon_helpers import normalize_ticker_for_reference_api
from http_clients import http_clients

logger = get_logger(__name__)


class PolygonDataLoader:
    """
    Carga datos históricos desde Polygon únicamente
    
    Datos obtenidos:
    - Market Cap (de ticker details)
    - Average Volume (calculado de aggregates históricos)
    - Sector (de SIC code)
    - Float (de ticker details weighted_shares_outstanding)
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        timescale_client: TimescaleClient,
        polygon_api_key: str
    ):
        self.redis = redis_client
        self.db = timescale_client
        self.api_key = polygon_api_key
        self.base_url = "https://api.polygon.io"
        
        # Statistics
        self.tickers_loaded = 0
        self.api_calls = 0
        self.errors = 0
        self.cache_hits = 0
        self.start_time = time.time()
    
    async def load_all_ticker_data(
        self,
        symbols: List[str],
        calculate_avg_volume: bool = True,
        max_concurrent: int = 80  # NUEVO: Paralelización agresiva
    ) -> int:
        """
        Carga TODOS los datos de Polygon con PARALELIZACIÓN MASIVA
        
        Plan Advanced de Polygon permite hasta 100 requests/segundo.
        Usamos 80 para estar seguros.
        
        Args:
            symbols: Lista de símbolos (del universo de Polygon)
            calculate_avg_volume: Si calcular average volume
            max_concurrent: Requests concurrentes (default: 80)
        
        Returns:
            Cantidad de tickers cargados exitosamente
        """
        logger.info(
            "loading_polygon_data_parallel",
            symbols_count=len(symbols),
            calculate_avg_volume=calculate_avg_volume,
            max_concurrent=max_concurrent
        )
        
        loaded = 0
        
        # Procesar en chunks para control de rate limiting
        # Con avg_volume: 2 calls por ticker (details + aggregates)
        # Rate: 80 requests/seg = podemos procesar 40 tickers/seg (con avg_volume)
        #                       = 80 tickers/seg (sin avg_volume)
        
        calls_per_ticker = 2 if calculate_avg_volume else 1
        tickers_per_second = max_concurrent // calls_per_ticker
        chunk_size = tickers_per_second  # Procesar N tickers por segundo
        
        logger.info(
            f"Paralelización: {chunk_size} tickers/segundo, {max_concurrent} requests/segundo"
        )
        
        for i in range(0, len(symbols), chunk_size):
            batch = symbols[i:i + chunk_size]
            
            # Procesar batch completo en paralelo
            tasks = [
                self._load_ticker_data(symbol, calculate_avg_volume)
                for symbol in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if result and not isinstance(result, Exception):
                    loaded += 1
            
            # Progress logging
            if (i + chunk_size) % 500 == 0 or i == 0:
                logger.info(f"Progress: {min(i + chunk_size, len(symbols))}/{len(symbols)} tickers")
            
            # Rate limiting: Esperar 1 segundo entre batches
            # Esto asegura que no superamos max_concurrent requests/segundo
            await asyncio.sleep(1.0)
        
        logger.info(
            "polygon_data_load_completed",
            loaded=loaded,
            total=len(symbols),
            api_calls=self.api_calls,
            duration_seconds=int(time.time() - self.start_time)
        )
        
        return loaded
    
    async def _load_ticker_data(
        self,
        symbol: str,
        calculate_avg_volume: bool = True
    ) -> Optional[TickerMetadata]:
        """
        Carga datos de un ticker individual desde Polygon
        
        Pasos:
        1. Obtener ticker details (market_cap, sic_description)
        2. Si calculate_avg_volume=True: Obtener aggregates últimos 30 días
        3. Construir TickerMetadata
        4. Guardar en Redis + TimescaleDB
        """
        try:
            # 1. Ticker Details
            details = await self._fetch_ticker_details(symbol)
            
            if not details:
                return None
            
            # 2. Average Volume (opcional, más lento)
            avg_volume_30d = None
            if calculate_avg_volume:
                avg_volume_30d = await self._calculate_avg_volume(symbol, days=30)
            
            # 3. Construir metadata
            metadata = TickerMetadata(
                symbol=symbol,
                company_name=details.name,
                exchange=details.primary_exchange,
                sector=self._map_sic_to_sector(details.sic_description) if details.sic_description else None,
                industry=details.sic_description,
                market_cap=details.market_cap,
                free_float=details.weighted_shares_outstanding,
                # FIX: Usar weighted_shares_outstanding como fallback cuando share_class_shares_outstanding es None
                # Esto es común en foreign issuers (ej: AZI) donde Polygon solo tiene weighted
                shares_outstanding=details.share_class_shares_outstanding or details.weighted_shares_outstanding,
                avg_volume_30d=avg_volume_30d,
                avg_volume_10d=None,
                avg_price_30d=None,
                beta=None,  # No disponible fácilmente en Polygon
                is_etf=details.type == "ETF" if details.type else False,
                is_actively_trading=details.active,
                updated_at=datetime.now()
            )
            
            # 4. Guardar
            await self._save_to_cache(metadata)
            await self._save_to_database(metadata)
            
            self.tickers_loaded += 1
            
            return metadata
        
        except Exception as e:
            self.errors += 1
            logger.error(f"Error loading data for {symbol}", error=str(e))
            return None
    
    async def _fetch_ticker_details(self, symbol: str) -> Optional[PolygonTickerDetails]:
        """
        Obtiene detalles completos de un ticker desde Polygon
        
        Endpoint: GET /v3/reference/tickers/{ticker}
        
        Nota: Polygon usa formatos diferentes para preferred stocks:
        - Market Data API: P mayúscula (BACPM)
        - Reference API: p minúscula (BACpM)
        Esta función normaliza automáticamente el formato.
        """
        try:
            # Normalizar formato para preferred stocks (P mayúscula → p minúscula)
            normalized_symbol = normalize_ticker_for_reference_api(symbol)
            
            if normalized_symbol != symbol:
                logger.debug(f"Normalized preferred stock: {symbol} → {normalized_symbol}")
            
            # Usar cliente Polygon con connection pooling
            results = await http_clients.polygon.get_ticker_details(normalized_symbol)
            self.api_calls += 1
            
            if results:
                return PolygonTickerDetails(**results)
                    
            return None
        
        except Exception as e:
            logger.error(f"Error fetching ticker details for {symbol}", error=str(e))
            return None
    
    async def _calculate_avg_volume(self, symbol: str, days: int = 30) -> Optional[int]:
        """
        Calcula volumen promedio de los últimos N días
        
        Endpoint: GET /v2/aggs/ticker/{symbol}/range/1/day/{from}/{to}
        """
        try:
            # Calcular fechas
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            # Usar cliente Polygon con connection pooling
            data = await http_clients.polygon.get_aggregates(
                symbol=symbol,
                multiplier=1,
                timespan="day",
                from_date=from_date,
                to_date=to_date
            )
            self.api_calls += 1
            
            if data and "results" in data and data["results"]:
                volumes = [bar["v"] for bar in data["results"] if "v" in bar]
                
                if volumes:
                    return int(mean(volumes))
            
            return None
        
        except Exception as e:
            logger.debug(f"Error calculating avg volume for {symbol}", error=str(e))
            return None
    
    def _map_sic_to_sector(self, sic_description: Optional[str]) -> Optional[str]:
        """
        Mapea SIC description a sector general
        
        Polygon usa SIC (Standard Industrial Classification)
        Mapeamos a sectores comunes de trading
        """
        if not sic_description:
            return None
        
        sic_lower = sic_description.lower()
        
        # Technology
        if any(word in sic_lower for word in ["computer", "software", "electronic", "semiconductor", "technology"]):
            return "Technology"
        
        # Healthcare
        if any(word in sic_lower for word in ["pharmaceutical", "medical", "health", "biotechnology"]):
            return "Healthcare"
        
        # Financial
        if any(word in sic_lower for word in ["bank", "insurance", "financial", "investment", "securities"]):
            return "Financial Services"
        
        # Energy
        if any(word in sic_lower for word in ["oil", "gas", "energy", "petroleum", "coal"]):
            return "Energy"
        
        # Consumer
        if any(word in sic_lower for word in ["retail", "consumer", "restaurant", "food", "beverage"]):
            return "Consumer Cyclical"
        
        # Industrial
        if any(word in sic_lower for word in ["manufacturing", "industrial", "machinery", "equipment"]):
            return "Industrials"
        
        # Real Estate
        if any(word in sic_lower for word in ["real estate", "reit", "property"]):
            return "Real Estate"
        
        # Communication
        if any(word in sic_lower for word in ["communication", "telecom", "media", "broadcasting"]):
            return "Communication Services"
        
        # Utilities
        if any(word in sic_lower for word in ["utility", "electric", "water", "gas distribution"]):
            return "Utilities"
        
        # Materials
        if any(word in sic_lower for word in ["mining", "metal", "chemical", "paper", "construction"]):
            return "Basic Materials"
        
        return "Other"
    
    async def _save_to_cache(self, metadata: TickerMetadata) -> None:
        """Guarda metadata en Redis cache"""
        try:
            key = f"metadata:ticker:{metadata.symbol}"
            await self.redis.set(
                key,
                metadata.model_dump(mode='json'),
                ttl=86400  # 24 horas (aumentado desde 1 hora)
            )
        except Exception as e:
            logger.error(f"Error saving to cache {metadata.symbol}", error=str(e))
    
    async def _save_to_database(self, metadata: TickerMetadata) -> None:
        """Guarda metadata en TimescaleDB"""
        try:
            data = metadata.model_dump(mode='json')
            await self.db.upsert_ticker_metadata(metadata.symbol, data)
        except Exception as e:
            logger.error(f"Error saving to database {metadata.symbol}", error=str(e))
    
    async def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del loader"""
        return {
            "tickers_loaded": self.tickers_loaded,
            "api_calls": self.api_calls,
            "errors": self.errors,
            "cache_hits": self.cache_hits,
            "uptime_seconds": int(time.time() - self.start_time)
        }

