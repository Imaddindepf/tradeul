"""
SEC XBRL Splits - Ajuste de datos por stock splits usando Polygon API.
"""

import httpx
from typing import List, Dict, Any, Optional

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SplitAdjuster:
    """
    Ajusta datos financieros por splits históricos.
    
    Usa Polygon API para obtener historial de splits y ajustar:
    - EPS (Earnings Per Share)
    - Shares Outstanding
    """
    
    POLYGON_URL = "https://api.polygon.io"
    
    def __init__(self, polygon_api_key: Optional[str] = None):
        self.polygon_api_key = polygon_api_key
        self._cache: Dict[str, List[Dict]] = {}
    
    async def get_splits(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Obtener historial de splits de Polygon.
        Cachea los resultados para evitar llamadas repetidas.
        """
        if not self.polygon_api_key:
            return []
        
        if ticker in self._cache:
            return self._cache[ticker]
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.POLYGON_URL}/v3/reference/splits",
                    params={
                        "ticker": ticker,
                        "limit": 100,
                        "apiKey": self.polygon_api_key
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            splits = data.get("results", [])
            splits.sort(key=lambda x: x.get("execution_date", ""), reverse=True)
            
            self._cache[ticker] = splits
            logger.info(f"[{ticker}] Found {len(splits)} splits")
            return splits
            
        except Exception as e:
            logger.warning(f"[{ticker}] Error getting splits: {e}")
            return []
    
    def get_adjustment_factor(
        self, 
        splits: List[Dict], 
        period_end_date: str
    ) -> float:
        """
        Calcular el factor de ajuste acumulativo para una fecha.
        
        Para ajustar datos históricos al valor actual:
        - Multiplicar EPS por este factor
        - Dividir Shares por este factor
        
        Ejemplo: GOOGL split 20:1 en 2022-07-18
        - Datos de 2021 (antes del split): factor = 1/20 = 0.05
        - EPS 2021 original: $58.61 → Ajustado: $58.61 * 0.05 = $2.93
        """
        if not splits or not period_end_date:
            return 1.0
        
        factor = 1.0
        
        for split in splits:
            execution_date = split.get("execution_date", "")
            split_from = split.get("split_from", 1)
            split_to = split.get("split_to", 1)
            
            if not execution_date or split_from == 0:
                continue
            
            # Si el período es ANTES del split, aplicar el factor
            if period_end_date < execution_date:
                split_factor = split_to / split_from
                factor *= (1.0 / split_factor)
        
        return factor
    
    def adjust_fields(
        self,
        fields: List[Dict[str, Any]],
        splits: List[Dict[str, Any]],
        period_dates: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Ajustar campos de Shares y EPS por splits históricos.
        
        IMPORTANTE: Los filings SEC recientes "restatan" datos históricos post-split,
        pero los datos MUY antiguos pueden venir de filings pre-split y necesitar ajuste.
        
        Estrategia: Detectar valores que parecen pre-split comparando magnitudes.
        - Shares: Si un valor es ~20x menor → multiplicar por factor
        - EPS: Si un valor es ~20x mayor → dividir por factor
        """
        if not splits:
            return fields
        
        shares_keys = {'shares_basic', 'shares_diluted'}
        eps_keys = {'eps_basic', 'eps_diluted'}
        
        # Encontrar el split más grande
        max_split_factor = 1.0
        max_split_date = ""
        for split in splits:
            split_from = split.get("split_from", 1)
            split_to = split.get("split_to", 1)
            if split_from > 0:
                factor = split_to / split_from
                if factor > max_split_factor:
                    max_split_factor = factor
                    max_split_date = split.get("execution_date", "")
        
        if max_split_factor <= 1.5:  # No hay split significativo
            return fields
        
        adjusted_fields = []
        
        for field in fields:
            key = field['key']
            
            if key in shares_keys:
                adjusted = self._adjust_shares(
                    field, period_dates, max_split_factor, max_split_date
                )
                adjusted_fields.append(adjusted)
            
            elif key in eps_keys:
                adjusted = self._adjust_eps(
                    field, period_dates, max_split_factor, max_split_date
                )
                adjusted_fields.append(adjusted)
            
            else:
                adjusted_fields.append(field)
        
        return adjusted_fields
    
    def _adjust_shares(
        self,
        field: Dict,
        period_dates: List[str],
        max_split_factor: float,
        max_split_date: str
    ) -> Dict:
        """Ajustar campo de shares."""
        values = field['values']
        
        # Obtener mediana de valores post-split
        post_split_values = []
        for i, v in enumerate(values):
            if v is not None and i < len(period_dates):
                date = period_dates[i]
                if date and date > max_split_date:
                    post_split_values.append(v)
        
        if not post_split_values:
            return field
        
        median_post_split = sorted(post_split_values)[len(post_split_values)//2]
        
        # Ajustar valores que parecen pre-split
        adjusted_values = []
        for i, v in enumerate(values):
            if v is None:
                adjusted_values.append(None)
            elif v > 0 and median_post_split / v > max_split_factor * 0.5:
                adjusted_values.append(v * max_split_factor)
            else:
                adjusted_values.append(v)
        
        if adjusted_values != values:
            logger.info(f"Split-adjusted {field['key']}: detected pre-split values")
        
        return {
            **field,
            'values': adjusted_values,
            'split_adjusted': adjusted_values != values
        }
    
    def _adjust_eps(
        self,
        field: Dict,
        period_dates: List[str],
        max_split_factor: float,
        max_split_date: str
    ) -> Dict:
        """Ajustar campo de EPS."""
        values = field['values']
        
        # Obtener valores post-split para referencia
        post_split_values = []
        for i, v in enumerate(values):
            if v is not None and i < len(period_dates):
                date = period_dates[i]
                if date and date > max_split_date:
                    post_split_values.append(v)
        
        if not post_split_values:
            return field
        
        median_post_split = sorted(post_split_values)[len(post_split_values)//2]
        
        # Ajustar períodos pre-split con valores anómalos
        adjusted_values = []
        for i, v in enumerate(values):
            if v is None:
                adjusted_values.append(None)
            elif i < len(period_dates):
                date = period_dates[i]
                if date and date < max_split_date and v > median_post_split * 1.5:
                    adjusted_values.append(v / max_split_factor)
                else:
                    adjusted_values.append(v)
            else:
                adjusted_values.append(v)
        
        if adjusted_values != values:
            logger.info(f"Split-adjusted {field['key']}: detected pre-split values")
        
        return {
            **field,
            'values': adjusted_values,
            'split_adjusted': adjusted_values != values
        }

