"""
SEC 13F Holders Service
Obtiene holders institucionales desde SEC-API.io 13F filings (fuente oficial)
"""

import sys
sys.path.append('/app')

from typing import List, Optional, Dict, Any
from datetime import datetime, date
from collections import defaultdict

from shared.utils.logger import get_logger
from shared.config.settings import settings
from http_clients import http_clients

from models.holder_models import InstitutionalHolderCreate

logger = get_logger(__name__)


class SEC13FHoldersService:
    """
    Servicio para obtener holders institucionales desde 13F filings via SEC-API.io
    
    Los 13F filings son reportes trimestrales obligatorios para instituciones
    con más de $100M en AUM. Contienen todas las posiciones en acciones US.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, 'SEC_API_IO', None) or getattr(settings, 'SEC_API_IO_KEY', None)
        self.base_url = "https://api.sec-api.io"
    
    async def get_institutional_holders(
        self, 
        ticker: str,
        limit: int = 50
    ) -> List[InstitutionalHolderCreate]:
        """
        Obtener holders institucionales de un ticker desde 13F filings.
        
        Args:
            ticker: Símbolo del ticker (ej: KITT)
            limit: Número máximo de holders a retornar
            
        Returns:
            Lista de InstitutionalHolderCreate con los holders
        """
        if not self.api_key:
            logger.warning("sec_api_key_missing_for_13f")
            return []
        
        try:
            ticker = ticker.upper()
            logger.info("fetching_13f_holders", ticker=ticker)
            
            # Query para buscar 13F filings que contengan el ticker
            # Buscamos los más recientes (últimos 3 meses)
            query = {
                "query": {
                    "query_string": {
                        "query": f'formType:"13F-HR" AND holdings.ticker:"{ticker}"'
                    }
                },
                "from": "0",
                "size": "100",  # Obtener suficientes para agregar
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            # Usar el cliente HTTP existente o hacer request directo
            if http_clients.sec_api:
                data = await http_clients.sec_api.query_api(query)
            else:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.base_url}?token={self.api_key}",
                        json=query
                    )
                    response.raise_for_status()
                    data = response.json()
            
            if not data or 'filings' not in data:
                logger.warning("no_13f_filings_found", ticker=ticker)
                return []
            
            # Extraer y agregar holdings por institución
            holders_map = self._aggregate_holdings(data['filings'], ticker)
            
            # Convertir a modelo y ordenar por shares
            holders = []
            for holder_name, holder_data in holders_map.items():
                holders.append(InstitutionalHolderCreate(
                    ticker=ticker,
                    holder_name=holder_name,
                    holder_cik=holder_data.get('cik'),
                    shares_held=holder_data['shares'],
                    market_value=holder_data['value'],
                    ownership_percent=None,  # Se calcula después
                    report_date=holder_data['report_date'],
                    change_shares=holder_data.get('change'),
                    change_percent=None,
                    source='SEC-13F'
                ))
            
            # Ordenar por shares (mayor primero)
            holders.sort(key=lambda x: x.shares_held or 0, reverse=True)
            
            # Limitar resultados
            holders = holders[:limit]
            
            logger.info("13f_holders_fetched", 
                       ticker=ticker, 
                       count=len(holders),
                       total_filings=len(data['filings']))
            
            return holders
            
        except Exception as e:
            logger.error("fetch_13f_holders_failed", ticker=ticker, error=str(e))
            return []
    
    def _aggregate_holdings(
        self, 
        filings: List[Dict], 
        ticker: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Agregar holdings por institución.
        
        Una institución puede tener múltiples 13F filings (diferentes cuentas/fondos).
        Agregamos todas las posiciones del mismo ticker por nombre de institución,
        tomando solo el filing más reciente de cada una.
        """
        holders_map = {}
        seen_filers = set()  # Para evitar duplicados del mismo filer
        
        for filing in filings:
            filer_name = filing.get('companyName', '').strip()
            filer_cik = filing.get('cik', '')
            filed_at = filing.get('filedAt', '')
            
            # Normalizar nombre del filer (remover sufijos comunes)
            normalized_name = self._normalize_filer_name(filer_name)
            
            # Si ya procesamos este filer, saltar (ya tenemos su filing más reciente)
            if normalized_name in seen_filers:
                continue
            
            # Buscar el holding del ticker en este filing
            holdings = filing.get('holdings', [])
            ticker_holdings = [h for h in holdings if h.get('ticker') == ticker]
            
            if not ticker_holdings:
                continue
            
            # Agregar todas las posiciones del ticker en este filing
            total_shares = 0
            total_value = 0
            
            for holding in ticker_holdings:
                # shares puede estar en diferentes campos
                shares = (
                    holding.get('shrsOrPrnAmt', {}).get('sshPrnamt') or
                    holding.get('shares') or
                    0
                )
                value = holding.get('value') or 0
                
                if shares:
                    total_shares += int(shares)
                if value:
                    total_value += int(value)
            
            # Si no hay shares pero hay value, intentar calcular
            if total_shares == 0 and total_value > 0:
                # No podemos calcular sin precio, pero guardamos el value
                pass
            
            # Solo incluir si tiene shares o value
            if total_shares > 0 or total_value > 0:
                # Parsear fecha
                report_date = None
                if filed_at:
                    try:
                        report_date = datetime.fromisoformat(filed_at.replace('Z', '+00:00')).date()
                    except:
                        pass
                
                holders_map[normalized_name] = {
                    'shares': total_shares,
                    'value': total_value,
                    'cik': filer_cik,
                    'report_date': report_date,
                    'filed_at': filed_at
                }
                seen_filers.add(normalized_name)
        
        return holders_map
    
    def _normalize_filer_name(self, name: str) -> str:
        """
        Normalizar nombre del filer para agrupar variaciones.
        
        Ejemplos:
        - "VANGUARD GROUP INC" y "Vanguard Group Inc" → "VANGUARD GROUP"
        - "BlackRock, Inc." y "BLACKROCK INC." → "BLACKROCK"
        """
        if not name:
            return ""
        
        # Uppercase y limpiar
        normalized = name.upper().strip()
        
        # Remover sufijos comunes (orden importa - más largos primero)
        suffixes = [
            ', L.L.C.', ' L.L.C.', ', LLC', ' LLC',
            ', INC.', ' INC.', ', INC', ' INC',
            ', L.P.', ' L.P.', ', LP', ' LP',
            ', LTD.', ' LTD.', ', LTD', ' LTD',
            ' CORPORATION', ' CORP.', ' CORP',
            '/DE/', '/DE', ' /DE/',
            ', CO.', ' CO.',
            ' & CO.', ' & CO', ' AND CO',
            ' GROUP', ' ADVISORS', ' ADVISORY',  # Para mejor agrupación
        ]
        
        # Aplicar múltiples veces para capturar combinaciones
        for _ in range(3):
            for suffix in suffixes:
                if normalized.endswith(suffix.upper()):
                    normalized = normalized[:-len(suffix)]
        
        # Mapeo de nombres conocidos con variaciones
        name_mappings = {
            'BLACKROCK': 'BLACKROCK',
            'BLACK ROCK': 'BLACKROCK',
            'VANGUARD': 'VANGUARD',
            'THE VANGUARD': 'VANGUARD',
            'STATE STREET': 'STATE STREET',
            'FIDELITY': 'FIDELITY',
            'MORGAN STANLEY': 'MORGAN STANLEY',
            'GOLDMAN SACHS': 'GOLDMAN SACHS',
            'JP MORGAN': 'JPMORGAN',
            'JPMORGAN': 'JPMORGAN',
            'J.P. MORGAN': 'JPMORGAN',
            'WELLS FARGO': 'WELLS FARGO',
            'BANK OF AMERICA': 'BANK OF AMERICA',
            'CITADEL': 'CITADEL',
            'RENAISSANCE': 'RENAISSANCE',
            'TWO SIGMA': 'TWO SIGMA',
            'BRIDGEWATER': 'BRIDGEWATER',
            'AQR': 'AQR',
            'D.E. SHAW': 'DE SHAW',
            'DE SHAW': 'DE SHAW',
        }
        
        # Buscar si el nombre normalizado comienza con algún nombre conocido
        for key, canonical in name_mappings.items():
            if normalized.startswith(key):
                return canonical
        
        # Limpiar caracteres especiales al final
        normalized = normalized.rstrip(' .,/')
        
        return normalized
    
    async def enrich_holders_with_ownership_pct(
        self,
        holders: List[InstitutionalHolderCreate],
        shares_outstanding: int
    ) -> List[InstitutionalHolderCreate]:
        """
        Enriquecer holders con porcentaje de ownership.
        """
        if not shares_outstanding or shares_outstanding <= 0:
            return holders
        
        for holder in holders:
            if holder.shares_held and holder.shares_held > 0:
                holder.ownership_percent = round(
                    (holder.shares_held / shares_outstanding) * 100, 
                    4
                )
        
        return holders

