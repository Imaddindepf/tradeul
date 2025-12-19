"""
SPAC Detector Service
Detecta si una empresa es un SPAC (Special Purpose Acquisition Company)

Métodos de detección:
1. SIC Code 6770 (Blank Checks) - 100% certeza
2. Nombre contiene "Acquisition Corp/Company" - 80% certeza
3. Tiene S-1 + S-4 filings típicos de SPAC - 70% certeza
4. Sin revenue operativo - 60% certeza
5. Trust account en balance - 50% certeza
"""

import sys
sys.path.append('/app')

from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import httpx

from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)


@dataclass
class SPACDetectionResult:
    """Resultado de detección de SPAC"""
    is_spac: bool
    confidence: float  # 0.0 - 1.0
    reason: str
    indicators: Dict[str, bool]
    company_info: Dict[str, Any]


class SPACDetector:
    """
    Servicio para detectar si una empresa es un SPAC.
    
    Un SPAC (Special Purpose Acquisition Company) es una empresa
    creada únicamente para recaudar capital mediante IPO para
    adquirir otra empresa existente.
    
    Características de SPACs:
    - SIC Code 6770 (Blank Checks)
    - Nombre típicamente incluye "Acquisition Corp/Company"
    - Sin operaciones comerciales (solo trust fund)
    - Filings típicos: S-1 (IPO), S-4 (merger), DEFM14A (proxy)
    """
    
    # Palabras clave en nombres de SPACs
    SPAC_NAME_KEYWORDS = [
        'acquisition corp',
        'acquisition company',
        'acquisition co',
        'blank check',
        ' spac',
        'merger corp',
        'merger company',
    ]
    
    # SIC Code para SPACs
    SPAC_SIC_CODE = '6770'  # Blank Checks
    
    def __init__(self, sec_api_key: Optional[str] = None):
        self.sec_api_key = sec_api_key or settings.SEC_API_IO_KEY
        self.sec_api_url = "https://api.sec-api.io"
        self.edgar_url = "https://data.sec.gov/submissions"
    
    async def detect(self, ticker: str) -> SPACDetectionResult:
        """
        Detectar si un ticker es un SPAC.
        
        Args:
            ticker: Símbolo del ticker
            
        Returns:
            SPACDetectionResult con el resultado de la detección
        """
        ticker = ticker.upper()
        indicators = {}
        company_info = {'ticker': ticker}
        
        try:
            # 1. Obtener información de la empresa desde SEC
            cik, company_name, sic_code, sic_desc = await self._get_company_info(ticker)
            
            company_info.update({
                'cik': cik,
                'name': company_name,
                'sic_code': sic_code,
                'sic_description': sic_desc
            })
            
            # 2. Verificar SIC Code 6770 (100% certeza)
            indicators['sic_6770'] = sic_code == self.SPAC_SIC_CODE
            
            # 3. Verificar nombre (80% certeza)
            if company_name:
                name_lower = company_name.lower()
                indicators['name_match'] = any(
                    kw in name_lower for kw in self.SPAC_NAME_KEYWORDS
                )
            else:
                indicators['name_match'] = False
            
            # 4. Verificar filings típicos de SPAC
            indicators['has_spac_filings'] = await self._check_spac_filings(ticker, cik)
            
            # 5. Determinar resultado
            if indicators['sic_6770']:
                return SPACDetectionResult(
                    is_spac=True,
                    confidence=1.0,
                    reason=f"SIC Code 6770 (Blank Checks) - SPAC confirmado",
                    indicators=indicators,
                    company_info=company_info
                )
            
            if indicators['name_match'] and indicators['has_spac_filings']:
                return SPACDetectionResult(
                    is_spac=True,
                    confidence=0.95,
                    reason=f"Nombre '{company_name}' + filings típicos de SPAC",
                    indicators=indicators,
                    company_info=company_info
                )
            
            if indicators['name_match']:
                return SPACDetectionResult(
                    is_spac=True,
                    confidence=0.80,
                    reason=f"Nombre '{company_name}' típico de SPAC",
                    indicators=indicators,
                    company_info=company_info
                )
            
            if indicators['has_spac_filings']:
                return SPACDetectionResult(
                    is_spac=True,
                    confidence=0.70,
                    reason="Tiene filings típicos de SPAC (S-1, S-4, DEFM14A)",
                    indicators=indicators,
                    company_info=company_info
                )
            
            return SPACDetectionResult(
                is_spac=False,
                confidence=1.0,
                reason="No se detectaron indicadores de SPAC",
                indicators=indicators,
                company_info=company_info
            )
            
        except Exception as e:
            logger.error("spac_detection_failed", ticker=ticker, error=str(e))
            return SPACDetectionResult(
                is_spac=False,
                confidence=0.0,
                reason=f"Error en detección: {str(e)}",
                indicators=indicators,
                company_info=company_info
            )
    
    async def _get_company_info(
        self, 
        ticker: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Obtener información de la empresa desde SEC EDGAR.
        
        Returns:
            Tuple de (cik, company_name, sic_code, sic_description)
        """
        try:
            # Primero obtener CIK desde SEC-API.io
            cik = await self._get_cik_from_sec_api(ticker)
            
            if not cik:
                return None, None, None, None
            
            # Luego obtener datos completos desde SEC EDGAR
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.edgar_url}/CIK{str(cik).zfill(10)}.json"
                headers = {'User-Agent': 'TradeUL/1.0 (support@tradeul.com)'}
                
                resp = await client.get(url, headers=headers)
                
                if resp.status_code == 200:
                    data = resp.json()
                    return (
                        cik,
                        data.get('name'),
                        data.get('sic'),
                        data.get('sicDescription')
                    )
            
            return cik, None, None, None
            
        except Exception as e:
            logger.error("get_company_info_failed", ticker=ticker, error=str(e))
            return None, None, None, None
    
    async def _get_cik_from_sec_api(self, ticker: str) -> Optional[str]:
        """Obtener CIK desde SEC-API.io"""
        if not self.sec_api_key:
            return None
        
        try:
            query = {
                "query": {"query_string": {"query": f'ticker:{ticker}'}},
                "from": "0",
                "size": "1"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.sec_api_url}?token={self.sec_api_key}",
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
    
    async def _check_spac_filings(
        self, 
        ticker: str, 
        cik: Optional[str]
    ) -> bool:
        """
        Verificar si tiene filings típicos de SPAC.
        
        Filings típicos:
        - S-1: Registration statement (IPO)
        - S-4: Business combination (merger)
        - DEFM14A: Definitive proxy statement (merger vote)
        """
        if not self.sec_api_key:
            return False
        
        try:
            # Buscar filings de merger/IPO
            search_key = f'cik:{cik}' if cik else f'ticker:{ticker}'
            query = {
                "query": {
                    "query_string": {
                        "query": f'{search_key} AND (formType:"S-1" OR formType:"S-4" OR formType:"DEFM14A")'
                    }
                },
                "from": "0",
                "size": "5"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.sec_api_url}?token={self.sec_api_key}",
                    json=query
                )
                resp.raise_for_status()
                data = resp.json()
                
                filings = data.get('filings', [])
                
                # Si tiene S-1 + S-4, es muy probable que sea SPAC
                form_types = [f.get('formType', '') for f in filings]
                has_s1 = any('S-1' in ft for ft in form_types)
                has_s4 = any('S-4' in ft for ft in form_types)
                has_defm = any('DEFM14A' in ft for ft in form_types)
                
                return (has_s1 and has_s4) or (has_s1 and has_defm)
            
        except Exception as e:
            logger.error("check_spac_filings_failed", ticker=ticker, error=str(e))
            return False
    
    async def is_de_spac(self, ticker: str) -> Tuple[bool, Optional[str]]:
        """
        Verificar si una empresa es un de-SPAC (SPAC que ya completó merger).
        
        Returns:
            Tuple de (is_de_spac, original_spac_name)
        """
        try:
            result = await self.detect(ticker)
            
            # Si el SIC ya no es 6770 pero tiene nombre de Acquisition Corp,
            # probablemente es un de-SPAC
            if result.company_info.get('sic_code') != self.SPAC_SIC_CODE:
                if result.indicators.get('has_spac_filings'):
                    # Buscar el nombre original del SPAC en filings antiguos
                    return True, None
            
            return False, None
            
        except Exception as e:
            logger.error("is_de_spac_failed", ticker=ticker, error=str(e))
            return False, None

