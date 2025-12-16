"""
SEC-API.io Filings Service
Obtiene SEC filings desde SEC-API.io (fuente principal)

Ventajas sobre FMP:
- Incluye Form 3/4 (insider transactions)
- Incluye Schedule 13G/13D (institutional holdings)
- Incluye S-4 (mergers)
- Incluye CORRESP (SEC correspondence)
- Búsqueda por CIK (más precisa)
"""

import sys
sys.path.append('/app')

from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx

from shared.utils.logger import get_logger
from shared.config.settings import settings
from models.filing_models import SECFilingCreate, FilingCategory

logger = get_logger(__name__)


class SECAPIFilingsService:
    """
    Servicio para obtener SEC filings desde SEC-API.io
    
    Reemplaza FMPFilingsService como fuente principal.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SEC_API_IO_KEY
        self.base_url = "https://api.sec-api.io"
    
    async def get_company_cik(self, ticker: str) -> Optional[str]:
        """Obtener CIK de una empresa por ticker"""
        if not self.api_key:
            return None
        
        try:
            query = {
                "query": {"query_string": {"query": f'ticker:{ticker}'}},
                "from": "0",
                "size": "1"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}?token={self.api_key}",
                    json=query
                )
                resp.raise_for_status()
                data = resp.json()
                
                filings = data.get('filings', [])
                if filings:
                    return filings[0].get('cik')
                return None
                
        except Exception as e:
            logger.error("get_cik_failed", ticker=ticker, error=str(e))
            return None
    
    async def get_sec_filings(
        self,
        ticker: str,
        filing_type: Optional[str] = None,
        limit: int = 100
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener SEC filings para un ticker desde SEC-API.io
        
        Args:
            ticker: Símbolo del ticker
            filing_type: Tipo de filing (opcional, ej: '10-K', '10-Q', '8-K')
            limit: Límite de resultados
        
        Returns:
            Lista de filings o None
        """
        if not self.api_key:
            logger.warning("sec_api_key_missing")
            return None
        
        try:
            ticker = ticker.upper()
            
            # Construir query
            query_str = f'ticker:{ticker}'
            if filing_type:
                query_str += f' AND formType:"{filing_type}"'
            
            query = {
                "query": {"query_string": {"query": query_str}},
                "from": "0",
                "size": str(limit),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}?token={self.api_key}",
                    json=query
                )
                resp.raise_for_status()
                data = resp.json()
            
            filings_data = data.get('filings', [])
            
            if not filings_data:
                logger.warning("no_sec_filings", ticker=ticker)
                return None
            
            # Convertir a modelos
            filings = []
            for f in filings_data:
                filing = self._build_filing(ticker, f)
                if filing:
                    filings.append(filing)
            
            logger.info(
                "sec_api_filings_fetched",
                ticker=ticker,
                count=len(filings),
                filing_type=filing_type
            )
            
            return filings
            
        except Exception as e:
            logger.error(
                "get_sec_filings_failed",
                ticker=ticker,
                error=str(e)
            )
            return None
    
    async def get_filings_by_cik(
        self,
        cik: str,
        filing_type: Optional[str] = None,
        limit: int = 100
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener SEC filings por CIK (más preciso que por ticker)
        """
        if not self.api_key:
            return None
        
        try:
            query_str = f'cik:{cik}'
            if filing_type:
                query_str += f' AND formType:"{filing_type}"'
            
            query = {
                "query": {"query_string": {"query": query_str}},
                "from": "0",
                "size": str(limit),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}?token={self.api_key}",
                    json=query
                )
                resp.raise_for_status()
                data = resp.json()
            
            filings_data = data.get('filings', [])
            
            filings = []
            for f in filings_data:
                ticker = f.get('ticker', '')
                filing = self._build_filing(ticker, f)
                if filing:
                    filings.append(filing)
            
            return filings
            
        except Exception as e:
            logger.error("get_filings_by_cik_failed", cik=cik, error=str(e))
            return None
    
    async def get_insider_filings(
        self,
        ticker: str,
        limit: int = 50
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener Form 3/4/5 (insider transactions)
        Solo disponible en SEC-API.io, no en FMP
        """
        filings = []
        
        for form_type in ['3', '4', '5']:
            form_filings = await self.get_sec_filings(ticker, form_type, limit // 3)
            if form_filings:
                filings.extend(form_filings)
        
        return filings if filings else None
    
    async def get_institutional_filings(
        self,
        ticker: str,
        limit: int = 50
    ) -> Optional[List[SECFilingCreate]]:
        """
        Obtener Schedule 13G/13D (institutional holdings changes)
        Solo disponible en SEC-API.io, no en FMP
        """
        filings = []
        
        for form_type in ['SC 13G', 'SC 13G/A', 'SC 13D', 'SC 13D/A']:
            form_filings = await self.get_sec_filings(ticker, form_type, limit // 4)
            if form_filings:
                filings.extend(form_filings)
        
        return filings if filings else None
    
    def _build_filing(self, ticker: str, filing_data: Dict) -> Optional[SECFilingCreate]:
        """Convertir datos de SEC-API.io a modelo SECFilingCreate"""
        try:
            form_type = filing_data.get('formType', '')
            
            # Normalizar fecha
            filed_at = filing_data.get('filedAt', '')
            if filed_at:
                # SEC-API.io usa formato ISO: "2025-01-15T16:30:00-05:00"
                filing_date = datetime.fromisoformat(filed_at.replace('Z', '+00:00')).date()
            else:
                return None
            
            # Determinar categoría del filing
            category = self._classify_filing_category(form_type)
            
            # Determinar si es relacionado con offering o dilutivo
            is_offering = category == FilingCategory.OFFERING
            is_dilutive = form_type.upper() in ('S-3', 'S-1', '424B5', '424B3', 'S-8')
            
            return SECFilingCreate(
                ticker=ticker.upper(),
                filing_type=form_type,
                filing_date=filing_date,
                accession_number=filing_data.get('accessionNo', ''),
                description=filing_data.get('description', ''),
                url=filing_data.get('linkToFilingDetails', ''),
                category=category,
                is_offering_related=is_offering,
                is_dilutive=is_dilutive,
            )
            
        except Exception as e:
            logger.debug("build_filing_failed", error=str(e))
            return None
    
    def _classify_filing_category(self, form_type: str) -> FilingCategory:
        """Clasificar categoría del filing"""
        form_upper = form_type.upper()
        
        if '10-K' in form_upper or '10-Q' in form_upper:
            return FilingCategory.FINANCIAL
        elif '8-K' in form_upper:
            return FilingCategory.DISCLOSURE
        elif 'S-3' in form_upper or '424B' in form_upper or 'S-1' in form_upper or 'S-4' in form_upper:
            return FilingCategory.OFFERING
        elif 'DEF 14' in form_upper or 'PRE 14' in form_upper:
            return FilingCategory.PROXY
        elif '13G' in form_upper or '13D' in form_upper or form_upper in ('3', '4', '5'):
            return FilingCategory.OWNERSHIP
        else:
            return FilingCategory.OTHER

