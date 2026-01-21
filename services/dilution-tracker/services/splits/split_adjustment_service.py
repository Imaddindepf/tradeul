"""
Split Adjustment Service v2.0

CAPA CENTRALIZADA Y DETERMINÍSTICA para ajuste de stock splits.

Principios de diseño:
1. ÚNICA FUENTE DE VERDAD: Solo este servicio ajusta por splits
2. DETERMINÍSTICO: Mismos inputs → mismos outputs
3. IDEMPOTENTE: No doble-ajusta (verifica split_adjusted flag)
4. VERIFICABLE: Detecta valores sospechosos
5. TRAZABLE: Guarda original_* para auditoría

Uso:
    service = SplitAdjustmentService(redis)
    adjusted_warrants = await service.adjust_warrants(ticker, warrants)
"""

import sys
sys.path.append('/app')

from typing import List, Dict, Optional, Tuple
from datetime import date
from decimal import Decimal
import httpx
import re

from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

# Mapeo de meses en inglés a número
MONTH_MAP = {
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12
}

def infer_issue_date_from_series_name(series_name: str) -> Optional[date]:
    """
    FIX: Intenta inferir issue_date del series_name cuando Gemini no la extrae.
    
    Ejemplos:
        "December 2020 Warrants" → 2020-12-15
        "March 2020 Convertible Notes" → 2020-03-15
        "Series A-1 Feb 2023" → 2023-02-15
        "Q3 2021 Offering" → 2021-07-15
    
    Returns:
        Fecha inferida o None si no puede determinarla
    """
    if not series_name:
        return None
    
    name = series_name.lower().strip()
    
    # Patrón 1: "Month YYYY" (más común)
    # Ejemplo: "December 2020", "March 2020"
    for month_name, month_num in MONTH_MAP.items():
        pattern = rf'\b{month_name}\s+(\d{{4}})\b'
        match = re.search(pattern, name)
        if match:
            year = int(match.group(1))
            if 2000 <= year <= 2030:  # Sanity check
                # Usamos día 15 como aproximación del medio del mes
                return date(year, month_num, 15)
    
    # Patrón 2: "YYYY-MM" o "MM/YYYY"
    match = re.search(r'\b(20\d{2})[-/](\d{1,2})\b', name)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            return date(year, month, 15)
    
    match = re.search(r'\b(\d{1,2})[-/](20\d{2})\b', name)
    if match:
        month = int(match.group(1))
        year = int(match.group(2))
        if 1 <= month <= 12:
            return date(year, month, 15)
    
    # Patrón 3: Solo año "2020 Warrants" → usar enero de ese año
    match = re.search(r'\b(20\d{2})\s+(warrant|note|preferred|offering)', name)
    if match:
        year = int(match.group(1))
        if 2000 <= year <= 2030:
            return date(year, 1, 1)  # Enero del año mencionado
    
    # Patrón 4: Trimestre "Q1 2021"
    match = re.search(r'\bq([1-4])\s+(20\d{2})\b', name)
    if match:
        quarter = int(match.group(1))
        year = int(match.group(2))
        month = (quarter - 1) * 3 + 1  # Q1=1, Q2=4, Q3=7, Q4=10
        return date(year, month, 15)
    
    return None


class SplitAdjustmentService:
    """
    Servicio centralizado para ajuste de splits.
    
    Regla de ajuste:
    - Si issue_date < split_date → AJUSTAR
    - Si issue_date >= split_date → NO AJUSTAR (ya es post-split)
    - Si issue_date es None → NO AJUSTAR, marcar needs_review=True
    
    Factores:
    - Precios: MULTIPLICAR por factor (reverse split sube precios)
    - Cantidades: DIVIDIR por factor (reverse split reduce cantidades)
    """
    
    CACHE_KEY_PREFIX = "sec_dilution:splits_v2"
    CACHE_TTL = 86400 * 7  # 7 días (splits no cambian frecuentemente)
    
    # Rangos típicos para validación
    TYPICAL_WARRANT_PRICE_RANGE = (0.001, 1000.0)  # $0.001 - $1000
    TYPICAL_OUTSTANDING_RANGE = (1, 100_000_000)   # 1 - 100M
    
    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.polygon_api_key = settings.POLYGON_API_KEY
    
    async def get_splits(self, ticker: str) -> List[Dict]:
        """
        Obtiene historial de splits para un ticker.
        
        Returns:
            Lista de splits ordenados por fecha (más reciente primero):
            [
                {
                    "execution_date": "2025-03-04",
                    "split_from": 11,
                    "split_to": 1,
                    "factor": 11.0,  # Multiplicador para precios
                    "type": "reverse"  # o "forward"
                },
                ...
            ]
        """
        ticker = ticker.upper()
        cache_key = f"{self.CACHE_KEY_PREFIX}:{ticker}"
        
        # Check cache
        cached = await self.redis.get(cache_key, deserialize=True)
        if cached is not None:
            logger.debug("splits_from_cache", ticker=ticker, count=len(cached))
            return cached
        
        # Fetch from Polygon
        splits = await self._fetch_splits_from_polygon(ticker)
        
        # Cache result
        await self.redis.set(cache_key, splits, ttl=self.CACHE_TTL, serialize=True)
        
        logger.info("splits_fetched_and_cached", 
                   ticker=ticker, 
                   count=len(splits),
                   splits=[f"{s['execution_date']}:{s['factor']}x" for s in splits])
        
        return splits
    
    async def _fetch_splits_from_polygon(self, ticker: str) -> List[Dict]:
        """Obtiene splits de Polygon API con formato normalizado."""
        if not self.polygon_api_key:
            logger.warning("polygon_api_key_missing")
            return []
        
        try:
            url = f"https://api.polygon.io/v3/reference/splits"
            params = {
                "ticker": ticker,
                "limit": 50,
                "apiKey": self.polygon_api_key
            }
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.warning("polygon_splits_api_error", 
                                  ticker=ticker, 
                                  status=response.status_code)
                    return []
                
                data = response.json()
            
            results = data.get('results', [])
            
            # Normalizar formato
            splits = []
            for r in results:
                exec_date = r.get('execution_date')
                split_from = r.get('split_from')  # Acciones antes
                split_to = r.get('split_to')      # Acciones después
                
                if not exec_date or not split_from or not split_to:
                    continue
                
                # Factor = split_from / split_to
                # Para reverse 11:1 → factor = 11 (precios suben 11x)
                # Para forward 1:2 → factor = 0.5 (precios bajan a la mitad)
                factor = split_from / split_to
                
                split_type = "reverse" if factor > 1 else "forward"
                
                splits.append({
                    "execution_date": exec_date,
                    "split_from": split_from,
                    "split_to": split_to,
                    "factor": factor,
                    "type": split_type
                })
            
            # Ordenar por fecha (más reciente primero)
            splits.sort(key=lambda x: x['execution_date'], reverse=True)
            
            return splits
            
        except Exception as e:
            logger.error("fetch_splits_failed", ticker=ticker, error=str(e))
            return []
    
    def calculate_cumulative_factor(
        self, 
        splits: List[Dict], 
        issue_date: date
    ) -> Tuple[float, List[str]]:
        """
        Calcula el factor acumulativo de splits aplicables a un instrumento.
        
        Args:
            splits: Lista de splits del ticker
            issue_date: Fecha de emisión del instrumento
            
        Returns:
            (factor, reasons): Factor acumulativo y lista de razones
        """
        cumulative_factor = 1.0
        reasons = []
        
        for split in splits:
            try:
                split_date = date.fromisoformat(split['execution_date'])
                
                # Si el instrumento se emitió ANTES del split, aplicar ajuste
                if issue_date < split_date:
                    cumulative_factor *= split['factor']
                    reasons.append(
                        f"{split['type']} {split['split_from']}:{split['split_to']} "
                        f"({split['execution_date']}): ×{split['factor']}"
                    )
                    
            except (ValueError, TypeError) as e:
                logger.warning("split_date_parse_error", 
                             split=split, 
                             error=str(e))
                continue
        
        return cumulative_factor, reasons
    
    async def adjust_warrants(
        self, 
        ticker: str, 
        warrants: List[Dict],
        force_readjust: bool = False
    ) -> List[Dict]:
        """
        Ajusta warrants por splits de forma determinística.
        
        Args:
            ticker: Ticker symbol
            warrants: Lista de warrants a ajustar
            force_readjust: Si True, re-ajusta incluso si ya está marcado
            
        Returns:
            Lista de warrants ajustados
        """
        if not warrants:
            return []
        
        ticker = ticker.upper()
        splits = await self.get_splits(ticker)
        
        if not splits:
            logger.info("no_splits_found", ticker=ticker)
            return warrants
        
        adjusted_warrants = []
        stats = {"adjusted": 0, "skipped": 0, "no_date": 0, "suspicious": 0}
        
        for warrant in warrants:
            adjusted = await self._adjust_single_warrant(
                warrant, 
                splits, 
                ticker,
                force_readjust
            )
            
            # Actualizar stats
            if adjusted.get('_adjustment_applied'):
                stats["adjusted"] += 1
            elif adjusted.get('_no_issue_date'):
                stats["no_date"] += 1
            else:
                stats["skipped"] += 1
            
            if adjusted.get('_suspicious_value'):
                stats["suspicious"] += 1
            
            adjusted_warrants.append(adjusted)
        
        logger.info("warrants_split_adjustment_complete",
                   ticker=ticker,
                   total=len(warrants),
                   **stats)
        
        return adjusted_warrants
    
    async def _adjust_single_warrant(
        self,
        warrant: Dict,
        splits: List[Dict],
        ticker: str,
        force_readjust: bool
    ) -> Dict:
        """Ajusta un warrant individual."""
        # Crear copia para no mutar original
        w = dict(warrant)
        
        # Si ya está ajustado y no forzamos, skip
        if w.get('split_adjusted') and not force_readjust:
            logger.debug("warrant_already_adjusted",
                        ticker=ticker,
                        series=w.get('series_name'),
                        factor=w.get('split_factor'))
            return w
        
        # Necesitamos issue_date para decidir
        issue_date_str = w.get('issue_date')
        issue_date = None
        inferred_from_name = False
        
        # Parsear fecha si existe
        if issue_date_str:
            try:
                if isinstance(issue_date_str, date):
                    issue_date = issue_date_str
                else:
                    issue_date = date.fromisoformat(str(issue_date_str)[:10])
            except (ValueError, TypeError) as e:
                logger.warning("warrant_date_parse_error",
                              ticker=ticker,
                              series=w.get('series_name'),
                              date=issue_date_str,
                              error=str(e))
        
        # FIX: Si no hay issue_date, intentar inferirla del series_name
        if issue_date is None:
            series_name = w.get('series_name', '')
            inferred_date = infer_issue_date_from_series_name(series_name)
            
            if inferred_date:
                issue_date = inferred_date
                inferred_from_name = True
                logger.info("warrant_date_inferred_from_name",
                           ticker=ticker,
                           series=series_name,
                           inferred_date=str(inferred_date))
            else:
                w['_no_issue_date'] = True
                w['_needs_review'] = True
                logger.warning("warrant_no_issue_date",
                              ticker=ticker,
                              series=w.get('series_name'))
                return w
        
        # Calcular factor
        factor, reasons = self.calculate_cumulative_factor(splits, issue_date)
        
        if factor == 1.0:
            # No hay ajuste necesario
            w['split_adjusted'] = False
            w['split_factor'] = None
            return w
        
        # ================================================================
        # APLICAR AJUSTE BASADO EN FECHAS (lógica determinística)
        # ================================================================
        # Regla simple y correcta:
        # - Si issue_date < split_date → APLICAR ese split (precio es pre-split)
        # - Si issue_date >= split_date → NO aplicar (precio ya es post-split)
        # 
        # El factor ya fue calculado por calculate_cumulative_factor()
        # usando exactamente esta lógica de fechas.
        # ================================================================
        if w.get('original_exercise_price'):
            original_price = self._parse_decimal(w.get('original_exercise_price'))
            price_source = "original_exercise_price"
        else:
            original_price = self._parse_decimal(w.get('exercise_price'))
            price_source = "exercise_price"
            
        if w.get('original_outstanding'):
            original_outstanding = self._parse_int(w.get('original_outstanding'))
        else:
            original_outstanding = self._parse_int(w.get('outstanding'))
            
        if w.get('original_total_issued'):
            original_total_issued = self._parse_int(w.get('original_total_issued'))
        else:
            original_total_issued = self._parse_int(w.get('total_issued'))
        
        # DEBUG: Log detallado de ajuste
        logger.info("split_adjustment_detail",
                   ticker=ticker,
                   series=w.get('series_name'),
                   issue_date=str(issue_date),
                   inferred_from_name=inferred_from_name,
                   price_source=price_source,
                   original_price=original_price,
                   factor=factor,
                   new_price=round(original_price * factor, 4) if original_price else None,
                   reasons=reasons)
        
        # Guardar originales si no existen
        if original_price and original_price > 0:
            if not w.get('original_exercise_price'):
                w['original_exercise_price'] = original_price
            w['exercise_price'] = round(original_price * factor, 4)
        
        if original_outstanding and original_outstanding > 0:
            if not w.get('original_outstanding'):
                w['original_outstanding'] = original_outstanding
            w['outstanding'] = int(original_outstanding / factor)
        
        if original_total_issued and original_total_issued > 0:
            if not w.get('original_total_issued'):
                w["original_total_issued"] = original_total_issued
            w['total_issued'] = int(original_total_issued / factor)
        
        # Marcar como ajustado
        w['split_adjusted'] = True
        w['split_factor'] = factor
        w['_adjustment_applied'] = True
        w['_adjustment_reasons'] = reasons
        
        # FIX: Indicar si la fecha fue inferida (para auditoría)
        if inferred_from_name:
            w['_issue_date_inferred'] = True
            w['_inferred_issue_date'] = str(issue_date)
        
        # Validar resultado
        new_price = w.get('exercise_price', 0)
        if new_price and (new_price < self.TYPICAL_WARRANT_PRICE_RANGE[0] or 
                         new_price > self.TYPICAL_WARRANT_PRICE_RANGE[1]):
            w['_suspicious_value'] = True
            logger.warning("suspicious_adjusted_price",
                          ticker=ticker,
                          series=w.get('series_name'),
                          original=original_price,
                          adjusted=new_price,
                          factor=factor)
        
        logger.debug("warrant_adjusted",
                    ticker=ticker,
                    series=w.get('series_name'),
                    factor=factor,
                    original_price=original_price,
                    new_price=w.get('exercise_price'))
        
        return w
    
    async def adjust_convertible_preferred(
        self,
        ticker: str,
        preferred: List[Dict],
        force_readjust: bool = False
    ) -> List[Dict]:
        """
        Ajusta convertible preferred por splits.
        
        Similar a warrants, pero ajusta conversion_price.
        """
        if not preferred:
            return []
        
        ticker = ticker.upper()
        splits = await self.get_splits(ticker)
        
        if not splits:
            return preferred
        
        adjusted_list = []
        
        for pref in preferred:
            p = dict(pref)
            
            if p.get('split_adjusted') and not force_readjust:
                adjusted_list.append(p)
                continue
            
            issue_date_str = p.get('issue_date')
            issue_date = None
            inferred_from_name = False
            
            # Parsear fecha si existe
            if issue_date_str:
                try:
                    if isinstance(issue_date_str, date):
                        issue_date = issue_date_str
                    else:
                        issue_date = date.fromisoformat(str(issue_date_str)[:10])
                except:
                    pass
            
            # FIX: Intentar inferir del series_name si no hay issue_date
            if issue_date is None:
                series_name = p.get('series_name', '')
                inferred_date = infer_issue_date_from_series_name(series_name)
                
                if inferred_date:
                    issue_date = inferred_date
                    inferred_from_name = True
                    logger.info("preferred_date_inferred_from_name",
                               ticker=ticker,
                               series=series_name,
                               inferred_date=str(inferred_date))
                else:
                    p['_needs_review'] = True
                    adjusted_list.append(p)
                    continue
            
            factor, reasons = self.calculate_cumulative_factor(splits, issue_date)
            
            if factor == 1.0:
                p['split_adjusted'] = False
                adjusted_list.append(p)
                continue
            
            # Ajustar conversion_price
            original_cp = self._parse_decimal(p.get('conversion_price'))
            if original_cp and original_cp > 0:
                p['original_conversion_price'] = original_cp
                p['conversion_price'] = round(original_cp * factor, 4)
            
            p['split_adjusted'] = True
            p['split_factor'] = factor
            
            # FIX: Indicar si la fecha fue inferida (para auditoría)
            if inferred_from_name:
                p['_issue_date_inferred'] = True
                p['_inferred_issue_date'] = str(issue_date)
            
            logger.debug("preferred_adjusted",
                        ticker=ticker,
                        series=p.get('series_name'),
                        factor=factor)
            
            adjusted_list.append(p)
        
        return adjusted_list
    
    @staticmethod
    def _parse_decimal(value) -> Optional[float]:
        """Parse valor a float."""
        if value is None:
            return None
        try:
            if isinstance(value, (int, float, Decimal)):
                return float(value)
            return float(str(value).replace(',', '').strip())
        except:
            return None
    
    @staticmethod
    def _parse_int(value) -> Optional[int]:
        """Parse valor a int."""
        if value is None:
            return None
        try:
            if isinstance(value, int):
                return value
            return int(float(str(value).replace(',', '').strip()))
        except:
            return None


# Singleton
_split_service_instance = None

def get_split_adjustment_service(redis: RedisClient) -> SplitAdjustmentService:
    """Obtiene instancia singleton del servicio."""
    global _split_service_instance
    if _split_service_instance is None:
        _split_service_instance = SplitAdjustmentService(redis)
    return _split_service_instance
