"""
EdgarTools Service - Datos detallados de XBRL via edgartools

ARQUITECTURA HÍBRIDA:
- SEC-API: Datos rápidos, pre-procesados (fuente principal)
- edgartools: Datos detallados, segmentos, geografía (enriquecimiento)

Este servicio proporciona:
1. Desgloses por segmento de negocio (Google Services, Cloud, etc.)
2. Desgloses por geografía (US, EMEA, APAC, etc.)
3. Estructura jerárquica completa (parent/child)
4. Labels FASB oficiales
5. Dimensiones XBRL completas
"""

import os
import asyncio
import functools
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import json

from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Lazy import para evitar errores si edgartools no está instalado
_edgar_available = None
_edgar_module = None


def _check_edgar_available():
    """Verificar si edgartools está disponible."""
    global _edgar_available, _edgar_module
    if _edgar_available is None:
        try:
            import edgar
            _edgar_module = edgar
            _edgar_available = True
            logger.info("edgartools_available", version=getattr(edgar, '__version__', 'unknown'))
        except ImportError:
            _edgar_available = False
            logger.warning("edgartools_not_installed", msg="pip install edgartools")
    return _edgar_available


class EdgarToolsService:
    """
    Servicio para extraer datos detallados via edgartools.
    
    Características:
    - Cache local de filings XBRL
    - Extracción de segmentos y dimensiones
    - Procesamiento en background (no bloquea API)
    - Compatible con el flujo híbrido
    """
    
    # Configuración de local storage
    DEFAULT_STORAGE_PATH = "/opt/tradeul/edgar_cache"
    
    # Cache en memoria para datos ya procesados
    _cache: Dict[str, Dict] = {}
    _cache_ttl = timedelta(hours=24)
    _cache_timestamps: Dict[str, datetime] = {}
    
    # Executor para operaciones síncronas de edgartools
    _executor = ThreadPoolExecutor(max_workers=4)
    
    def __init__(self, storage_path: str = None):
        """
        Inicializar servicio.
        
        Args:
            storage_path: Ruta para local storage de edgartools
        """
        self.storage_path = storage_path or self.DEFAULT_STORAGE_PATH
        self._initialized = False
        self._identity_set = False
        
    async def initialize(self) -> bool:
        """
        Inicializar edgartools con local storage.
        
        Returns:
            True si la inicialización fue exitosa
        """
        if self._initialized:
            return True
            
        if not _check_edgar_available():
            logger.error("edgartools_init_failed", reason="not_installed")
            return False
            
        try:
            # Ejecutar inicialización en thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                self._sync_initialize
            )
            self._initialized = True
            logger.info("edgartools_initialized", storage_path=self.storage_path)
            return True
            
        except Exception as e:
            logger.error("edgartools_init_error", error=str(e))
            return False
    
    def _sync_initialize(self):
        """Inicialización síncrona (ejecutada en thread pool)."""
        import edgar
        
        # Configurar identidad (requerido por SEC)
        if not self._identity_set:
            edgar.set_identity("Tradeul API api@tradeul.com")
            self._identity_set = True
        
        # Configurar local storage si existe el directorio
        if os.path.exists(self.storage_path):
            try:
                edgar.use_local_storage(self.storage_path)
                logger.info("edgartools_local_storage_enabled", path=self.storage_path)
            except Exception as e:
                logger.warning("edgartools_local_storage_failed", error=str(e))
        else:
            # Crear directorio
            os.makedirs(self.storage_path, exist_ok=True)
            logger.info("edgartools_storage_created", path=self.storage_path)
    
    async def get_segment_data(
        self,
        symbol: str,
        years: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Obtener datos desglosados por segmento de negocio.
        
        Args:
            symbol: Ticker de la empresa
            years: Número de años a obtener
            
        Returns:
            Dict con desgloses por segmento o None si falla
        """
        cache_key = f"segments:{symbol}:{years}"
        
        # Verificar cache
        if cache_key in self._cache:
            if datetime.now() - self._cache_timestamps.get(cache_key, datetime.min) < self._cache_ttl:
                logger.debug("edgartools_cache_hit", key=cache_key)
                return self._cache[cache_key]
        
        if not await self.initialize():
            return None
            
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._sync_get_segment_data,
                symbol,
                years
            )
            
            # Guardar en cache
            if result:
                self._cache[cache_key] = result
                self._cache_timestamps[cache_key] = datetime.now()
                
            return result
            
        except Exception as e:
            logger.error("edgartools_segment_error", symbol=symbol, error=str(e))
            return None
    
    def _sync_get_segment_data(self, symbol: str, years: int) -> Dict[str, Any]:
        """Obtener datos de segmentos (síncrono)."""
        import edgar
        
        company = edgar.Company(symbol)
        filings = company.get_filings(form="10-K")
        
        if not filings or len(filings) == 0:
            return None
            
        # Obtener el filing más reciente
        latest = filings[0]
        xbrl = latest.xbrl()
        
        if not xbrl:
            return None
        
        result = {
            "symbol": symbol,
            "filing_date": str(latest.filing_date),
            "segments": {"revenue": {}, "operating_income": {}, "costs": {}},
            "geography": {"revenue": {}},
            "products": {"revenue": {}},
            "raw_data": []
        }
        
        # Buscar statements de segmentos directamente
        # Diferentes empresas usan diferentes nombres
        segment_statement_names = [
            # GOOGL style
            'InformationaboutSegmentsandGeographicAreasRevenueandOperatingIncomeLossbySegmentDetails',
            'RevenuesRevenuebySegmentDetails',
            'RevenuesRevenuebyGeographicLocationDetails',
            'InformationaboutSegmentsandGeographicAreasLongLivedAssetsbyGeographicAreaDetails',
            # AMZN style
            'SegmentInformationReportableSegmentsandReconciliationtoConsolidatedNetIncomeDetails',
            'SegmentInformationDisaggregationofRevenueDetails',
            'SegmentInformationNetSalesAttributedtoCountriesRepresentingPortionofConsolidatedNetSalesDetails',
            # AAPL style
            'SegmentInformationandGeographicDataInformationbyReportableSegmentDetails',
            'SegmentInformationandGeographicDataNetSalesforCountriesthatIndividuallyAccountedforMorethan10oftheTotalDetails',
            'RevenueDisaggregatedNetSalesandPortionofNetSalesThatWasPreviouslyDeferredDetails',
            # Generic patterns
            'SegmentReportingDetails',
            'RevenueFromExternalCustomersByGeographicAreasDetails',
        ]
        
        for stmt_name in segment_statement_names:
            try:
                stmt = xbrl.get_statement(stmt_name)
                if stmt:
                    # El statement puede ser una lista directa
                    data = stmt if isinstance(stmt, list) else getattr(stmt, 'data', None)
                    if data:
                        self._process_segment_statement(data, result)
            except Exception as e:
                logger.debug("edgartools_stmt_not_found", statement=stmt_name, error=str(e))
        
        return result
    
    def _process_segment_statement(self, data: List[Dict], result: Dict) -> None:
        """Procesar un statement con datos de segmentos."""
        for item in data:
            if not isinstance(item, dict):
                continue
            
            # Solo procesar items con valores y dimensiones
            if not item.get('has_values') or not item.get('is_dimension'):
                continue
            
            values = item.get('values', {})
            if not values:
                continue
            
            # Convertir valores a formato año
            values_by_year = {}
            for period_key, value in values.items():
                year = self._extract_year_from_period(period_key)
                if year:
                    values_by_year[year] = value
            
            if not values_by_year:
                continue
            
            concept = item.get('concept', '').lower()
            label = item.get('label', '')
            dimension_label = item.get('full_dimension_label', '')
            
            # Determinar el tipo de métrica y dimensión
            is_revenue = 'revenue' in concept
            is_operating_income = 'operatingincomeloss' in concept.replace('_', '')
            is_costs = 'cost' in concept or 'expense' in concept
            
            # Determinar si es segmento o geografía
            is_segment = 'StatementBusinessSegmentsAxis' in dimension_label or 'ProductOrServiceAxis' in dimension_label
            is_geography = 'GeographicalAxis' in dimension_label
            
            # Extraer nombre limpio del segmento/geografía
            segment_name = label
            
            # Guardar en la estructura correcta
            if is_revenue:
                if is_geography:
                    if segment_name not in result["geography"]["revenue"]:
                        result["geography"]["revenue"][segment_name] = values_by_year
                elif is_segment:
                    # Separar productos de segmentos
                    if 'ProductOrServiceAxis' in dimension_label and 'StatementBusinessSegmentsAxis' not in dimension_label:
                        if segment_name not in result["products"]["revenue"]:
                            result["products"]["revenue"][segment_name] = values_by_year
                    else:
                        if segment_name not in result["segments"]["revenue"]:
                            result["segments"]["revenue"][segment_name] = values_by_year
                            
            elif is_operating_income and is_segment:
                if segment_name not in result["segments"]["operating_income"]:
                    result["segments"]["operating_income"][segment_name] = values_by_year
                    
            elif is_costs and is_segment:
                if segment_name not in result["segments"]["costs"]:
                    result["segments"]["costs"][segment_name] = values_by_year
    
    def _extract_dimensional_data(self, data: List[Dict]) -> List[Dict]:
        """
        Extraer datos con dimensiones de un statement.
        
        Incluye:
        - Datos consolidados (sin dimensiones)
        - Desgloses por segmento
        - Desgloses por geografía
        - Desgloses por producto
        """
        extracted = []
        
        for item in data:
            if not isinstance(item, dict):
                continue
                
            # Datos básicos
            record = {
                "concept": item.get("concept", ""),
                "label": item.get("label", ""),
                "level": item.get("level", 0),
                "is_abstract": item.get("is_abstract", False),
                "parent": item.get("parent"),
                "children": item.get("children", []),
                "has_values": item.get("has_values", False),
            }
            
            # Valores por período
            values = item.get("values", {})
            if values:
                record["values"] = {}
                for period_key, value in values.items():
                    # Convertir key de período a año
                    year = self._extract_year_from_period(period_key)
                    if year:
                        record["values"][year] = value
            
            # Información dimensional
            if item.get("is_dimension"):
                record["is_dimension"] = True
                record["full_dimension_label"] = item.get("full_dimension_label", "")
                
                # Procesar metadata de dimensiones
                dim_metadata = item.get("dimension_metadata", [])
                if dim_metadata:
                    dimensions = []
                    for dm in dim_metadata:
                        if isinstance(dm, dict):
                            dimensions.append({
                                "dimension": dm.get("dimension", ""),
                                "member": dm.get("member", ""),
                                "member_label": dm.get("member_label", "")
                            })
                    record["dimensions"] = dimensions
            
            extracted.append(record)
        
        return extracted
    
    def _extract_year_from_period(self, period_key: str) -> Optional[str]:
        """Extraer año de una key de período XBRL."""
        # Formato: "duration_2024-01-01_2024-12-31" o "instant_2024-12-31"
        import re
        match = re.search(r'(\d{4})-12-31', period_key)
        if match:
            return match.group(1)
        match = re.search(r'(\d{4})', period_key)
        if match:
            return match.group(1)
        return None
    
    def _process_segments(self, data: Dict) -> Dict[str, Any]:
        """
        Procesar y estructurar datos por segmento de negocio.
        
        Returns:
            Dict con estructura:
            {
                "revenue": {
                    "Google Services": {"2024": 304930000000, ...},
                    "Google Cloud": {"2024": 43229000000, ...},
                    ...
                },
                "operating_income": {...}
            }
        """
        segments = {
            "revenue": {},
            "operating_income": {},
            "costs": {}
        }
        
        for statement_name in ["income_statement", "balance_sheet"]:
            statement = data.get(statement_name, [])
            for item in statement:
                if not item.get("is_dimension") or not item.get("values"):
                    continue
                
                dimensions = item.get("dimensions", [])
                for dim in dimensions:
                    # Buscar segmentos de negocio
                    if "BusinessSegmentsAxis" in dim.get("dimension", ""):
                        segment_name = dim.get("member_label", "Unknown")
                        concept = item.get("concept", "").lower()
                        
                        # Clasificar por tipo de métrica
                        if "revenue" in concept:
                            if segment_name not in segments["revenue"]:
                                segments["revenue"][segment_name] = {}
                            segments["revenue"][segment_name].update(item.get("values", {}))
                            
                        elif "operating" in concept and "income" in concept:
                            if segment_name not in segments["operating_income"]:
                                segments["operating_income"][segment_name] = {}
                            segments["operating_income"][segment_name].update(item.get("values", {}))
                            
                        elif "cost" in concept or "expense" in concept:
                            if segment_name not in segments["costs"]:
                                segments["costs"][segment_name] = {}
                            segments["costs"][segment_name].update(item.get("values", {}))
        
        return segments
    
    def _process_geography(self, data: Dict) -> Dict[str, Any]:
        """
        Procesar y estructurar datos por geografía.
        
        Returns:
            Dict con estructura:
            {
                "revenue": {
                    "United States": {"2024": 170447000000, ...},
                    "EMEA": {"2024": 102127000000, ...},
                    ...
                }
            }
        """
        geography = {
            "revenue": {},
            "assets": {}
        }
        
        for statement_name in ["income_statement", "balance_sheet"]:
            statement = data.get(statement_name, [])
            for item in statement:
                if not item.get("is_dimension") or not item.get("values"):
                    continue
                
                dimensions = item.get("dimensions", [])
                for dim in dimensions:
                    # Buscar dimensiones geográficas
                    if "GeographicalAxis" in dim.get("dimension", ""):
                        geo_name = dim.get("member_label", "Unknown")
                        concept = item.get("concept", "").lower()
                        
                        if "revenue" in concept:
                            if geo_name not in geography["revenue"]:
                                geography["revenue"][geo_name] = {}
                            geography["revenue"][geo_name].update(item.get("values", {}))
                            
                        elif "asset" in concept:
                            if geo_name not in geography["assets"]:
                                geography["assets"][geo_name] = {}
                            geography["assets"][geo_name].update(item.get("values", {}))
        
        return geography
    
    async def get_full_statement_structure(
        self,
        symbol: str,
        statement_type: str = "income"
    ) -> Optional[List[Dict]]:
        """
        Obtener estructura jerárquica completa de un statement.
        
        Args:
            symbol: Ticker
            statement_type: "income", "balance", o "cash"
            
        Returns:
            Lista de items con jerarquía completa
        """
        if not await self.initialize():
            return None
            
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._sync_get_statement_structure,
                symbol,
                statement_type
            )
            return result
            
        except Exception as e:
            logger.error("edgartools_structure_error", symbol=symbol, error=str(e))
            return None
    
    def _sync_get_statement_structure(
        self,
        symbol: str,
        statement_type: str
    ) -> List[Dict]:
        """Obtener estructura de statement (síncrono)."""
        import edgar
        
        company = edgar.Company(symbol)
        filings = company.get_filings(form="10-K")
        
        if not filings or len(filings) == 0:
            return []
            
        latest = filings[0]
        xbrl = latest.xbrl()
        
        if not xbrl:
            return []
        
        statement = xbrl.get_statement(statement_type)
        if not statement or not hasattr(statement, 'data'):
            return []
        
        # Convertir a estructura limpia
        structure = []
        for item in statement.data:
            if not isinstance(item, dict):
                continue
                
            # Solo items no-dimensionales para la estructura base
            if item.get("is_dimension"):
                continue
                
            structure.append({
                "concept": item.get("concept", ""),
                "label": item.get("label", ""),
                "level": item.get("level", 0),
                "is_abstract": item.get("is_abstract", False),
                "is_subtotal": "total" in item.get("preferred_label", "").lower() if item.get("preferred_label") else False,
                "parent": item.get("parent"),
                "has_values": item.get("has_values", False),
                "balance": item.get("balance"),  # debit/credit
            })
        
        return structure
    
    async def download_edgar_data(self) -> bool:
        """
        Descargar datos esenciales de EDGAR para acelerar consultas futuras.
        
        Este método debe ejecutarse como job nocturno (cron).
        
        Returns:
            True si la descarga fue exitosa
        """
        if not await self.initialize():
            return False
            
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                self._sync_download_data
            )
            logger.info("edgartools_data_downloaded")
            return True
            
        except Exception as e:
            logger.error("edgartools_download_error", error=str(e))
            return False
    
    def _sync_download_data(self):
        """Descargar datos de EDGAR (síncrono)."""
        import edgar
        
        # Esto descarga índices y datos esenciales
        edgar.download_edgar_data()
    
    def clear_cache(self, symbol: str = None):
        """
        Limpiar cache.
        
        Args:
            symbol: Si se proporciona, solo limpia cache de ese símbolo
        """
        if symbol:
            keys_to_remove = [k for k in self._cache.keys() if symbol in k]
            for k in keys_to_remove:
                del self._cache[k]
                del self._cache_timestamps[k]
        else:
            self._cache.clear()
            self._cache_timestamps.clear()


# Singleton global
_edgartools_service: Optional[EdgarToolsService] = None


def get_edgartools_service() -> EdgarToolsService:
    """Obtener instancia singleton del servicio."""
    global _edgartools_service
    if _edgartools_service is None:
        _edgartools_service = EdgarToolsService()
    return _edgartools_service

