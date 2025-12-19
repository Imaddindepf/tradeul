"""
SEC EDGAR Shares Outstanding Service
=====================================
Obtiene historical shares outstanding desde SEC EDGAR Company Facts API (XBRL)
Fuente gratuita y oficial - no requiere API key
"""

import httpx
from typing import Optional, List, Dict
from datetime import date
from decimal import Decimal

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SECEdgarSharesService:
    """
    Servicio para obtener historical shares outstanding desde SEC EDGAR.
    Usa la API de Company Facts que expone datos XBRL de los filings.
    """
    
    BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
    USER_AGENT = "TradeulApp/1.0 (support@tradeul.com)"
    
    def __init__(self):
        self.timeout = 30.0
    
    async def get_historical_shares(
        self,
        cik: str,
        limit: int = 40
    ) -> Optional[List[Dict]]:
        """
        Obtener historical shares outstanding desde SEC EDGAR.
        
        Args:
            cik: CIK de la compañía (con o sin padding de ceros)
            limit: Número máximo de registros a devolver
            
        Returns:
            Lista de dicts con {date, shares, form, filed} ordenados por fecha
        """
        try:
            # Asegurar que CIK tiene 10 dígitos con padding
            cik_padded = cik.lstrip('0').zfill(10)
            url = f"{self.BASE_URL}/CIK{cik_padded}.json"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": self.USER_AGENT}
                )
                
                if response.status_code == 404:
                    logger.warning("sec_edgar_cik_not_found", cik=cik)
                    return None
                    
                if response.status_code != 200:
                    logger.error("sec_edgar_error", cik=cik, status=response.status_code)
                    return None
                
                data = response.json()
                
                # Extraer shares outstanding
                shares_data = self._extract_shares_outstanding(data)
                
                if not shares_data:
                    logger.warning("no_shares_data_found", cik=cik)
                    return None
                
                # Ordenar por fecha y limitar
                shares_data.sort(key=lambda x: x['date'])
                
                # Deduplicar por fecha (quedarse con el más reciente filed)
                seen_dates = {}
                for item in shares_data:
                    date_str = item['date']
                    if date_str not in seen_dates or item['filed'] > seen_dates[date_str]['filed']:
                        seen_dates[date_str] = item
                
                result = sorted(seen_dates.values(), key=lambda x: x['date'])[-limit:]
                
                logger.info(
                    "historical_shares_fetched",
                    cik=cik,
                    records=len(result)
                )
                
                return result
                
        except Exception as e:
            logger.error("sec_edgar_exception", cik=cik, error=str(e))
            return None
    
    def _extract_shares_outstanding(self, data: Dict) -> List[Dict]:
        """
        Extraer shares outstanding de los datos XBRL.
        Busca en múltiples campos posibles.
        """
        result = []
        
        facts = data.get('facts', {}).get('us-gaap', {})
        
        # Campos posibles para shares outstanding (en orden de preferencia)
        share_fields = [
            'CommonStockSharesOutstanding',
            'CommonStockSharesIssued',
            'WeightedAverageNumberOfSharesOutstandingBasic',
            'WeightedAverageNumberOfDilutedSharesOutstanding',
        ]
        
        for field in share_fields:
            field_data = facts.get(field, {})
            units = field_data.get('units', {})
            
            # Buscar en 'shares' o 'pure'
            shares_list = units.get('shares', []) or units.get('pure', [])
            
            if shares_list:
                for item in shares_list:
                    # Solo incluir datos de 10-K y 10-Q (no 8-K ni otros)
                    form = item.get('form', '')
                    if form not in ['10-K', '10-Q', '10-K/A', '10-Q/A']:
                        continue
                    
                    end_date = item.get('end')
                    value = item.get('val')
                    filed = item.get('filed')
                    
                    if end_date and value:
                        result.append({
                            'date': end_date,
                            'shares': int(value),
                            'form': form,
                            'filed': filed,
                            'source': field
                        })
                
                # Si encontramos datos, no buscar en otros campos
                if result:
                    break
        
        return result
    
    async def get_current_shares(self, cik: str) -> Optional[int]:
        """
        Obtener el número más reciente de shares outstanding.
        """
        historical = await self.get_historical_shares(cik, limit=5)
        if historical:
            return historical[-1]['shares']
        return None


async def get_cik_from_ticker(ticker: str) -> Optional[str]:
    """
    Obtener CIK desde ticker usando SEC EDGAR company search.
    """
    try:
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-K&dateb=&owner=include&count=1&search_text=&output=atom"
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "TradeulApp/1.0 (support@tradeul.com)"}
            )
            
            if response.status_code == 200:
                # Parsear XML para obtener CIK
                text = response.text
                # Buscar CIK en el contenido
                import re
                match = re.search(r'CIK=(\d+)', text)
                if match:
                    return match.group(1)
                    
        return None
        
    except Exception as e:
        logger.error("get_cik_failed", ticker=ticker, error=str(e))
        return None

