"""
SEC Full-Text Search Service
============================
Usa SEC-API.io Full-Text Search para encontrar filings con contenido dilutivo.

VENTAJAS:
- Búsqueda directa en el texto completo de filings
- No necesita descargar todos los filings
- Encuentra instrumentos dilutivos de forma precisa
- Soporta búsquedas booleanas y wildcards
"""

import httpx
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


# Keywords de instrumentos dilutivos para búsqueda full-text
DILUTION_SEARCH_QUERIES = {
    # Warrants
    "warrants": '"warrant" OR "pre-funded warrant" OR "prefunded warrant" OR "exercise price" OR "warrants to purchase"',
    
    # ATM / At-The-Market
    "atm": '"at-the-market" OR "ATM offering" OR "ATM program" OR "sales agreement" OR "equity distribution"',
    
    # Convertibles
    "convertibles": '"convertible note" OR "convertible debenture" OR "conversion price" OR "convertible preferred"',
    
    # Shelf / Registrations
    "shelf": '"shelf registration" OR "prospectus supplement" OR "registration statement"',
    
    # Private Placements
    "private_placement": '"private placement" OR "PIPE" OR "securities purchase agreement" OR "subscription agreement"',
    
    # Equity Lines
    "equity_line": '"equity line" OR "ELOC" OR "committed equity" OR "purchase agreement"',
}

# Query combinada para buscar CUALQUIER instrumento dilutivo
COMBINED_DILUTION_QUERY = ' OR '.join([
    '"warrant"',
    '"pre-funded warrant"',
    '"at-the-market"',
    '"ATM offering"',
    '"convertible note"',
    '"shelf registration"',
    '"private placement"',
    '"PIPE"',
    '"equity line"',
    '"securities purchase agreement"',
])


class SECFullTextSearch:
    """
    Servicio para búsqueda full-text en SEC EDGAR usando SEC-API.io
    """
    
    API_ENDPOINT = "https://api.sec-api.io/full-text-search"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SEC_API_IO_KEY
        if not self.api_key:
            logger.warning("sec_api_io_key_not_configured")
    
    async def search_dilution_filings(
        self,
        cik: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        form_types: Optional[List[str]] = None,
        max_pages: int = 5
    ) -> List[Dict]:
        """
        Buscar filings que contengan términos de dilución para un CIK específico.
        
        Args:
            cik: CIK de la empresa (sin ceros iniciales)
            start_date: Fecha inicio (YYYY-MM-DD), default: 5 años atrás
            end_date: Fecha fin (YYYY-MM-DD), default: hoy
            form_types: Lista de form types a filtrar (opcional)
            max_pages: Máximo de páginas a obtener (100 resultados por página)
            
        Returns:
            Lista de filings con metadatos
        """
        if not self.api_key:
            logger.error("sec_api_io_key_missing")
            return []
        
        # Defaults
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*5)).strftime("%Y-%m-%d")
        
        # Normalizar CIK (sin ceros iniciales)
        cik_normalized = cik.lstrip('0')
        
        # Construir query con CIK + términos dilutivos
        # Formato: cik:XXXXXXX AND (términos dilutivos)
        query = f"({COMBINED_DILUTION_QUERY})"
        
        all_filings = []
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                for page in range(1, max_pages + 1):
                    payload = {
                        "query": query,
                        "ciks": [cik_normalized],
                        "startDate": start_date,
                        "endDate": end_date,
                        "page": str(page)
                    }
                    
                    # Filtrar por form types si se especifica
                    if form_types:
                        payload["formTypes"] = form_types
                    
                    logger.info("fulltext_search_request", 
                              cik=cik_normalized, 
                              page=page,
                              start_date=start_date,
                              end_date=end_date)
                    
                    response = await client.post(
                        f"{self.API_ENDPOINT}?token={self.api_key}",
                        json=payload
                    )
                    
                    if response.status_code != 200:
                        logger.error("fulltext_search_failed", 
                                   status=response.status_code,
                                   response=response.text[:500])
                        break
                    
                    data = response.json()
                    filings = data.get("filings", [])
                    total = data.get("total", {})
                    
                    logger.info("fulltext_search_page_result",
                              cik=cik_normalized,
                              page=page,
                              filings_count=len(filings),
                              total_value=total.get("value"),
                              total_relation=total.get("relation"))
                    
                    all_filings.extend(filings)
                    
                    # Si no hay más resultados, parar
                    if len(filings) < 100:
                        break
            
            # Deduplicar por accession number
            seen = set()
            unique_filings = []
            for f in all_filings:
                acc_no = f.get("accessionNo")
                if acc_no and acc_no not in seen:
                    seen.add(acc_no)
                    unique_filings.append(f)
            
            logger.info("fulltext_search_completed",
                       cik=cik_normalized,
                       total_filings=len(unique_filings),
                       pages_searched=min(page, max_pages))
            
            return unique_filings
            
        except Exception as e:
            logger.error("fulltext_search_exception", cik=cik, error=str(e))
            return []
    
    async def search_specific_instrument(
        self,
        cik: str,
        instrument_type: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Buscar filings para un tipo específico de instrumento dilutivo.
        
        Args:
            cik: CIK de la empresa
            instrument_type: Tipo de instrumento (warrants, atm, convertibles, shelf, etc.)
            start_date: Fecha inicio
            end_date: Fecha fin
            
        Returns:
            Lista de filings
        """
        if instrument_type not in DILUTION_SEARCH_QUERIES:
            logger.warning("unknown_instrument_type", instrument_type=instrument_type)
            return []
        
        query = DILUTION_SEARCH_QUERIES[instrument_type]
        cik_normalized = cik.lstrip('0')
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*5)).strftime("%Y-%m-%d")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "query": query,
                    "ciks": [cik_normalized],
                    "startDate": start_date,
                    "endDate": end_date,
                }
                
                response = await client.post(
                    f"{self.API_ENDPOINT}?token={self.api_key}",
                    json=payload
                )
                
                if response.status_code != 200:
                    logger.error("specific_instrument_search_failed", 
                               instrument=instrument_type,
                               status=response.status_code)
                    return []
                
                data = response.json()
                filings = data.get("filings", [])
                
                logger.info("specific_instrument_search_completed",
                           cik=cik_normalized,
                           instrument=instrument_type,
                           filings_count=len(filings))
                
                return filings
                
        except Exception as e:
            logger.error("specific_instrument_search_exception", error=str(e))
            return []
    
    async def get_prospectus_data(
        self,
        cik: str,
        start_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Obtener datos estructurados de prospectuses (S-1, 424B4) usando Form S-1/424B4 API.
        
        Esta API devuelve datos ya estructurados:
        - Offering amounts
        - Securities types
        - Underwriters
        - etc.
        """
        if not self.api_key:
            return []
        
        cik_normalized = cik.lstrip('0')
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*5)).strftime("%Y-%m-%d")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Query para S-1 y 424B4 por CIK
                payload = {
                    "query": f"cik:{cik_normalized} AND filedAt:[{start_date} TO *]",
                    "from": "0",
                    "size": "50",
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
                
                response = await client.post(
                    f"https://api.sec-api.io/form-s1-424b4?token={self.api_key}",
                    json=payload
                )
                
                if response.status_code != 200:
                    logger.warning("prospectus_api_failed", status=response.status_code)
                    return []
                
                data = response.json()
                prospectuses = data.get("data", [])
                
                logger.info("prospectus_data_fetched",
                           cik=cik_normalized,
                           count=len(prospectuses))
                
                return prospectuses
                
        except Exception as e:
            logger.error("prospectus_data_exception", error=str(e))
            return []
    
    async def get_form_d_offerings(
        self,
        cik: str,
        start_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Obtener Form D offerings (private placements) usando Form D API.
        
        Returns:
            Lista de offerings con datos estructurados
        """
        if not self.api_key:
            return []
        
        cik_normalized = cik.lstrip('0').zfill(10)  # Form D necesita CIK con ceros
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*5)).strftime("%Y-%m-%d")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "query": f"primaryIssuer.cik:{cik_normalized}",
                    "from": "0",
                    "size": "50",
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
                
                response = await client.post(
                    f"https://api.sec-api.io/form-d?token={self.api_key}",
                    json=payload
                )
                
                if response.status_code != 200:
                    logger.warning("form_d_api_failed", status=response.status_code)
                    return []
                
                data = response.json()
                offerings = data.get("offerings", [])
                
                logger.info("form_d_offerings_fetched",
                           cik=cik_normalized,
                           count=len(offerings))
                
                return offerings
                
        except Exception as e:
            logger.error("form_d_exception", error=str(e))
            return []


# Singleton
_fulltext_search: Optional[SECFullTextSearch] = None


def get_fulltext_search() -> SECFullTextSearch:
    """Get or create fulltext search instance"""
    global _fulltext_search
    if _fulltext_search is None:
        _fulltext_search = SECFullTextSearch()
    return _fulltext_search

