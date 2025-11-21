"""
Metadata Manager - Core business logic
"""

import asyncio
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Dict, Any, List
import httpx

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.models.scanner import TickerMetadata

from providers.polygon_provider import PolygonProvider
from providers.cache_provider import CacheProvider

logger = get_logger(__name__)

class MetadataManager:
    """Manager principal para metadatos de tickers"""
    
    def __init__(
        self,
        redis_client: RedisClient,
        timescale_client: TimescaleClient,
        polygon_api_key: str
    ):
        self.redis = redis_client
        self.db = timescale_client
        
        self.polygon = PolygonProvider(polygon_api_key)
        self.cache = CacheProvider(redis_client)
        
        self.cache_ttl = 3600
        self.metadata_stale_days = 7
        
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "db_hits": 0,
            "api_calls": 0,
            "errors": 0
        }
    
    async def get_metadata(
        self,
        symbol: str,
        force_refresh: bool = False
    ) -> Optional[TickerMetadata]:
        """Obtiene metadata de un ticker con estrategia cache-first"""
        symbol = symbol.upper()
        
        try:
            if not force_refresh:
                cached = await self.cache.get_metadata(symbol)
                if cached:
                    self.stats["cache_hits"] += 1
                    logger.debug("metadata_cache_hit", symbol=symbol)
                    return cached
                
                self.stats["cache_misses"] += 1
            
            db_metadata = await self._get_from_db(symbol)
            
            if db_metadata:
                self.stats["db_hits"] += 1
                
                updated_at = db_metadata.get("updated_at")
                is_stale = self._is_metadata_stale(updated_at)
                
                if not is_stale and not force_refresh:
                    metadata_obj = self._dict_to_metadata(db_metadata)
                    await self.cache.set_metadata(metadata_obj, ttl=self.cache_ttl)
                    logger.debug("metadata_db_hit", symbol=symbol)
                    return metadata_obj
                
                logger.info("metadata_stale", symbol=symbol)
            
            enriched = await self.enrich_metadata(symbol)
            
            if enriched:
                return enriched
            
            if db_metadata:
                logger.warning("api_failed_using_stale", symbol=symbol)
                metadata_obj = self._dict_to_metadata(db_metadata)
                await self.cache.set_metadata(metadata_obj, ttl=300)
                return metadata_obj
            
            logger.warning("metadata_not_found", symbol=symbol)
            return None
        
        except Exception as e:
            logger.error("get_metadata_failed", symbol=symbol, error=str(e))
            self.stats["errors"] += 1
            return None
    
    async def enrich_metadata(self, symbol: str) -> Optional[TickerMetadata]:
        """Enriquece metadata desde Polygon"""
        symbol = symbol.upper()
        
        try:
            logger.info("enriching_metadata", symbol=symbol)
            self.stats["api_calls"] += 1
            
            ticker_details = await self.polygon.get_ticker_details(symbol)
            
            if not ticker_details:
                logger.warning("polygon_no_data", symbol=symbol)
                return None
            
            # Extraer branding
            branding = ticker_details.get("branding", {})
            
            metadata = TickerMetadata(
                # Identificación básica
                symbol=symbol,
                company_name=ticker_details.get("name"),
                
                # Clasificación
                exchange=ticker_details.get("primary_exchange"),
                sector=self._map_sic_to_sector(ticker_details.get("sic_description")),
                industry=ticker_details.get("sic_description"),
                
                # Capitalización y shares
                market_cap=ticker_details.get("market_cap"),
                float_shares=ticker_details.get("weighted_shares_outstanding"),
                shares_outstanding=ticker_details.get("share_class_shares_outstanding"),
                
                # Métricas (se calculan por separado)
                avg_volume_30d=None,
                avg_volume_10d=None,
                avg_price_30d=None,
                beta=None,
                
                # Información de la compañía
                description=ticker_details.get("description"),
                homepage_url=ticker_details.get("homepage_url"),
                phone_number=ticker_details.get("phone_number"),
                address=ticker_details.get("address"),  # Ya viene como dict
                total_employees=ticker_details.get("total_employees"),
                list_date=ticker_details.get("list_date"),  # Mantener como string "YYYY-MM-DD"
                
                # Branding
                logo_url=branding.get("logo_url") if branding else None,
                icon_url=branding.get("icon_url") if branding else None,
                
                # Identificadores
                cik=ticker_details.get("cik"),
                composite_figi=ticker_details.get("composite_figi"),
                share_class_figi=ticker_details.get("share_class_figi"),
                ticker_root=ticker_details.get("ticker_root"),
                ticker_suffix=ticker_details.get("ticker_suffix"),
                
                # Detalles del activo
                type=ticker_details.get("type"),
                currency_name=ticker_details.get("currency_name"),
                locale=ticker_details.get("locale"),
                market=ticker_details.get("market"),
                round_lot=ticker_details.get("round_lot"),
                delisted_utc=ticker_details.get("delisted_utc"),
                
                # Estados
                is_etf=ticker_details.get("type") == "ETF",
                is_actively_trading=ticker_details.get("active", True),
                updated_at=datetime.now(timezone.utc)
            )
            
            await self._save_to_db(metadata)
            await self.cache.set_metadata(metadata, ttl=self.cache_ttl)
            
            logger.info("metadata_enriched", symbol=symbol)
            
            return metadata
        
        except Exception as e:
            logger.error("enrich_metadata_failed", symbol=symbol, error=str(e))
            self.stats["errors"] += 1
            return None
    
    async def bulk_enrich(
        self,
        symbols: List[str],
        max_concurrent: int = 5
    ) -> Dict[str, bool]:
        """Enriquece múltiples symbols en paralelo"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def enrich_with_sem(symbol: str) -> tuple[str, bool]:
            async with semaphore:
                result = await self.enrich_metadata(symbol)
                await asyncio.sleep(0.2)
                return (symbol, result is not None)
        
        tasks = [enrich_with_sem(sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return dict(results)
    
    async def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene perfil completo de la compañía"""
        metadata = await self.get_metadata(symbol)
        
        if not metadata:
            return None
        
        profile = {
            "symbol": metadata.symbol,
            "company_name": metadata.company_name,
            "exchange": metadata.exchange,
            "sector": metadata.sector,
            "industry": metadata.industry,
            "is_etf": metadata.is_etf,
            "is_actively_trading": metadata.is_actively_trading,
            "updated_at": metadata.updated_at.isoformat() if metadata.updated_at else None
        }
        
        return profile
    
    async def get_statistics(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene estadísticas de mercado del ticker"""
        metadata = await self.get_metadata(symbol)
        
        if not metadata:
            return None
        
        stats = {
            "symbol": metadata.symbol,
            "market_cap": metadata.market_cap,
            "float_shares": metadata.float_shares,
            "shares_outstanding": metadata.shares_outstanding,
            "avg_volume_30d": metadata.avg_volume_30d,
            "avg_volume_10d": metadata.avg_volume_10d,
            "avg_price_30d": metadata.avg_price_30d,
            "beta": metadata.beta,
            "updated_at": metadata.updated_at.isoformat() if metadata.updated_at else None
        }
        
        return stats
    
    async def _get_from_db(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene metadata de TimescaleDB con todos los campos"""
        query = """
            SELECT 
                symbol, company_name, exchange, sector, industry,
                market_cap, float_shares, shares_outstanding,
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
        
        result = await self.db.fetchrow(query, symbol)
        return dict(result) if result else None
    
    async def _save_to_db(self, metadata: TickerMetadata) -> None:
        """Guarda metadata en TimescaleDB con todos los campos expandidos"""
        import json
        from datetime import datetime, date as date_type
        
        query = """
            INSERT INTO ticker_metadata (
                symbol, company_name, exchange, sector, industry,
                market_cap, float_shares, shares_outstanding,
                avg_volume_30d, avg_volume_10d, avg_price_30d, beta,
                description, homepage_url, phone_number, address,
                total_employees, list_date,
                logo_url, icon_url,
                cik, composite_figi, share_class_figi, ticker_root, ticker_suffix,
                type, currency_name, locale, market, round_lot, delisted_utc,
                is_etf, is_actively_trading, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                $13, $14, $15, $16::jsonb, $17, $18,
                $19, $20,
                $21, $22, $23, $24, $25,
                $26, $27, $28, $29, $30, $31,
                $32, $33, NOW()
            )
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                exchange = EXCLUDED.exchange,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                market_cap = EXCLUDED.market_cap,
                float_shares = EXCLUDED.float_shares,
                shares_outstanding = EXCLUDED.shares_outstanding,
                avg_volume_30d = EXCLUDED.avg_volume_30d,
                avg_volume_10d = EXCLUDED.avg_volume_10d,
                avg_price_30d = EXCLUDED.avg_price_30d,
                beta = EXCLUDED.beta,
                description = EXCLUDED.description,
                homepage_url = EXCLUDED.homepage_url,
                phone_number = EXCLUDED.phone_number,
                address = EXCLUDED.address,
                total_employees = EXCLUDED.total_employees,
                list_date = EXCLUDED.list_date,
                logo_url = EXCLUDED.logo_url,
                icon_url = EXCLUDED.icon_url,
                cik = EXCLUDED.cik,
                composite_figi = EXCLUDED.composite_figi,
                share_class_figi = EXCLUDED.share_class_figi,
                ticker_root = EXCLUDED.ticker_root,
                ticker_suffix = EXCLUDED.ticker_suffix,
                type = EXCLUDED.type,
                currency_name = EXCLUDED.currency_name,
                locale = EXCLUDED.locale,
                market = EXCLUDED.market,
                round_lot = EXCLUDED.round_lot,
                delisted_utc = EXCLUDED.delisted_utc,
                is_etf = EXCLUDED.is_etf,
                is_actively_trading = EXCLUDED.is_actively_trading,
                updated_at = NOW()
        """
        
        # Convertir address dict a JSON string para PostgreSQL
        address_json = json.dumps(metadata.address) if metadata.address else None
        
        # Convertir list_date de string a date object si es necesario
        list_date_value = None
        if metadata.list_date:
            if isinstance(metadata.list_date, str):
                try:
                    list_date_value = datetime.strptime(metadata.list_date, '%Y-%m-%d').date()
                except:
                    list_date_value = None
            elif isinstance(metadata.list_date, date_type):
                list_date_value = metadata.list_date
        
        await self.db.execute(
            query,
            metadata.symbol,
            metadata.company_name,
            metadata.exchange,
            metadata.sector,
            metadata.industry,
            metadata.market_cap,
            metadata.float_shares,
            metadata.shares_outstanding,
            metadata.avg_volume_30d,
            metadata.avg_volume_10d,
            metadata.avg_price_30d,
            metadata.beta,
            metadata.description,
            metadata.homepage_url,
            metadata.phone_number,
            address_json,
            metadata.total_employees,
            list_date_value,
            metadata.logo_url,
            metadata.icon_url,
            metadata.cik,
            metadata.composite_figi,
            metadata.share_class_figi,
            metadata.ticker_root,
            metadata.ticker_suffix,
            metadata.type,
            metadata.currency_name,
            metadata.locale,
            metadata.market,
            metadata.round_lot,
            metadata.delisted_utc,
            metadata.is_etf,
            metadata.is_actively_trading
        )
    
    def _dict_to_metadata(self, data: Dict[str, Any]) -> TickerMetadata:
        """Convierte dict de DB a TickerMetadata con TODOS los campos"""
        import json
        
        # Parsear address si viene como string JSON
        address = data.get("address")
        if address and isinstance(address, str):
            try:
                address = json.loads(address)
            except (json.JSONDecodeError, TypeError):
                address = None
        
        return TickerMetadata(
            symbol=data["symbol"],
            company_name=data.get("company_name"),
            exchange=data.get("exchange"),
            sector=data.get("sector"),
            industry=data.get("industry"),
            market_cap=data.get("market_cap"),
            float_shares=data.get("float_shares"),
            shares_outstanding=data.get("shares_outstanding"),
            avg_volume_30d=data.get("avg_volume_30d"),
            avg_volume_10d=data.get("avg_volume_10d"),
            avg_price_30d=data.get("avg_price_30d"),
            beta=data.get("beta"),
            
            # Campos expandidos
            description=data.get("description"),
            homepage_url=data.get("homepage_url"),
            phone_number=data.get("phone_number"),
            address=address,  # Ya parseado
            total_employees=data.get("total_employees"),
            list_date=data.get("list_date"),
            logo_url=data.get("logo_url"),
            icon_url=data.get("icon_url"),
            cik=data.get("cik"),
            composite_figi=data.get("composite_figi"),
            share_class_figi=data.get("share_class_figi"),
            ticker_root=data.get("ticker_root"),
            ticker_suffix=data.get("ticker_suffix"),
            type=data.get("type"),
            currency_name=data.get("currency_name"),
            locale=data.get("locale"),
            market=data.get("market"),
            round_lot=data.get("round_lot"),
            delisted_utc=data.get("delisted_utc"),
            
            # Estados
            is_etf=data.get("is_etf", False),
            is_actively_trading=data.get("is_actively_trading", True),
            updated_at=data.get("updated_at", datetime.now(timezone.utc))
        )
    
    def _is_metadata_stale(self, updated_at: datetime) -> bool:
        """Verifica si metadata está obsoleto"""
        if not updated_at:
            return True
        
        age = datetime.now(timezone.utc) - updated_at
        return age.days > self.metadata_stale_days
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Convierte string YYYY-MM-DD a objeto date"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            return None
    
    def _map_sic_to_sector(self, sic_description: Optional[str]) -> Optional[str]:
        """Mapea SIC description a sector general"""
        if not sic_description:
            return None
        
        sic_lower = sic_description.lower()
        
        if any(k in sic_lower for k in ["technology", "software", "computer", "internet"]):
            return "Technology"
        elif any(k in sic_lower for k in ["financial", "bank", "insurance", "investment"]):
            return "Financial Services"
        elif any(k in sic_lower for k in ["healthcare", "pharmaceutical", "medical", "biotech"]):
            return "Healthcare"
        elif any(k in sic_lower for k in ["retail", "store", "consumer"]):
            return "Consumer Cyclical"
        elif any(k in sic_lower for k in ["energy", "oil", "gas", "petroleum"]):
            return "Energy"
        elif any(k in sic_lower for k in ["manufacturing", "industrial", "machinery"]):
            return "Industrials"
        elif any(k in sic_lower for k in ["real estate", "property", "reit"]):
            return "Real Estate"
        elif any(k in sic_lower for k in ["communication", "telecom", "media"]):
            return "Communication Services"
        elif any(k in sic_lower for k in ["utility", "utilities", "electric", "water"]):
            return "Utilities"
        elif any(k in sic_lower for k in ["material", "chemical", "mining", "metal"]):
            return "Basic Materials"
        else:
            return "Other"
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del manager"""
        total_requests = self.stats["cache_hits"] + self.stats["cache_misses"]
        cache_hit_rate = (self.stats["cache_hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["cache_misses"],
            "db_hits": self.stats["db_hits"],
            "api_calls": self.stats["api_calls"],
            "errors": self.stats["errors"]
        }

