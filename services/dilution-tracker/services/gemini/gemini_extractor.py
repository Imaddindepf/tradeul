"""
Gemini Extractor - Extracción simplificada de datos SEC
========================================================
Usa Gemini Files API para analizar SEC filings y exhibits.

ARQUITECTURA SIMPLIFICADA:
1. Recibe lista de filings con exhibits
2. Prioriza exhibits para datos precisos (conversion_price, etc.)
3. Un único prompt extrae TODOS los instrumentos
4. Sin fallbacks complejos, sin multiple passes

VENTAJAS:
- Código simple (~400 líneas vs 1,200+)
- Exhibits tienen datos exactos (no resúmenes)
- Un solo modelo (Gemini 2.5 Flash)
- Sin chunking ni timeouts complejos
"""

import asyncio
import json
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from google import genai
from google.genai.types import GenerateContentConfig

from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# PROMPT UNIFICADO - Extrae TODO en una sola llamada
# =============================================================================

UNIFIED_EXTRACTION_PROMPT = """
Analyze this SEC filing/exhibit and extract ALL ISSUED financial instruments.

CRITICAL: Extract only ACTUALLY ISSUED instruments, NOT future capacity.
- If agreement has "$3M initial + $24M incremental capacity", extract ONLY the $3M issued
- "Incremental Notes" or "Future Capacity" should NOT be extracted

Return JSON with this EXACT structure:

{
  "convertible_notes": [{
    "series_name": "Full descriptive name",
    "total_principal_amount": <ISSUED principal in dollars>,
    "remaining_principal_amount": <outstanding or null>,
    "conversion_price": <price per share - CRITICAL>,
    "original_conversion_price": <initial price before resets>,
    "conversion_ratio": <shares per dollar if given>,
    "total_shares_when_converted": <max shares if fully converted>,
    "remaining_shares_when_converted": <shares from remaining principal>,
    "interest_rate": <percentage number>,
    "issue_date": "YYYY-MM-DD",
    "convertible_date": "YYYY-MM-DD",
    "maturity_date": "YYYY-MM-DD",
    "is_registered": <boolean>,
    "registration_type": "S-1|S-3|F-1|F-3|null",
    "known_owners": "investor names",
    "underwriter_agent": "placement agent",
    "price_protection": "Variable Rate|Full Ratchet|Reset|None",
    "price_protection_clause": "EXACT TEXT of reset provision - copy verbatim",
    "floor_price": <minimum conversion price>,
    "variable_rate_adjustment": <boolean>,
    "is_toxic": <boolean if death spiral>
  }],
  "convertible_preferred": [{
    "series_name": "Series A/B/etc",
    "shares_outstanding": <number>,
    "liquidation_preference": <dollar per share>,
    "conversion_price": <price per common>,
    "conversion_ratio": <common per preferred>,
    "dividend_rate": <percentage>,
    "issue_date": "YYYY-MM-DD",
    "is_cumulative": <boolean>,
    "is_participating": <boolean>,
    "anti_dilution_provision": "weighted average|full ratchet|none",
    "known_owners": "holders"
  }],
  "warrants": [{
    "series_name": "warrant series name",
    "exercise_price": <price per share>,
    "original_exercise_price": <initial price>,
    "outstanding": <number outstanding>,
    "total_issued": <total issued>,
    "exercised": <number exercised>,
    "expired": <number expired>,
    "issue_date": "YYYY-MM-DD",
    "expiration_date": "YYYY-MM-DD",
    "exercisable_date": "YYYY-MM-DD",
    "is_registered": <boolean>,
    "registration_type": "S-1|S-3|F-1|F-3|null",
    "is_prefunded": <boolean for $0.0001 exercise>,
    "has_cashless_exercise": <boolean>,
    "warrant_coverage_ratio": <warrants per share purchased>,
    "known_owners": "holders",
    "underwriter_agent": "agent",
    "warrant_type": "Common|Pre-Funded|Placement Agent|SPAC",
    "status": "active|expired|exercised",
    "price_protection": "description",
    "anti_dilution_provision": <boolean>
  }],
  "atm_offerings": [{
    "series_name": "ATM program name",
    "total_capacity": <max dollars>,
    "remaining_capacity": <unused>,
    "amount_raised_to_date": <raised so far>,
    "registered_shares": <shares registered>,
    "placement_agent": "agent",
    "commission_rate": <percentage>,
    "agreement_date": "YYYY-MM-DD",
    "termination_date": "YYYY-MM-DD",
    "is_baby_shelf_limited": <boolean>
  }],
  "shelf_registrations": [{
    "series_name": "shelf name",
    "total_capacity": <dollars>,
    "remaining_capacity": <unused>,
    "current_raisable_amount": <current available>,
    "amount_raised": <total raised>,
    "amount_raised_last_12_months": <recent usage>,
    "form_type": "S-3|F-3|S-1|F-1|S-3ASR",
    "effect_date": "YYYY-MM-DD",
    "expiration_date": "YYYY-MM-DD",
    "is_baby_shelf": <boolean if <$75M float>,
    "baby_shelf_restriction": <boolean>,
    "is_mixed_shelf": <boolean>,
    "is_wksi": <boolean>,
    "last_banker": "underwriter"
  }],
  "equity_lines": [{
    "series_name": "ELOC name",
    "total_capacity": <amount>,
    "remaining_capacity": <unused>,
    "amount_used": <drawn>,
    "pricing_discount": <discount to market>,
    "daily_purchase_limit": <max daily>,
    "counterparty": "investor",
    "agreement_date": "YYYY-MM-DD",
    "termination_date": "YYYY-MM-DD",
    "registration_type": "S-1|S-3|F-1|F-3"
  }],
  "completed_offerings": [{
    "series_name": "offering name",
    "offering_date": "YYYY-MM-DD",
    "shares_offered": <number>,
    "price_per_share": <price>,
    "gross_proceeds": <total raised>,
    "offering_type": "Public|Private|PIPE|Rights|Direct",
    "method": "S-1|S-3|Direct|Private|Shelf",
    "warrants_issued": <warrant count>,
    "warrant_exercise_price": <strike>,
    "investors": "buyer names"
  }]
}

EXTRACTION RULES:
1. conversion_price and exercise_price are MOST CRITICAL - search thoroughly
2. Look for: "$X.XX per share", "conversion price of $X.XX", "exercise price"
3. price_protection_clause: Copy the EXACT TEXT verbatim from the document
4. Dates must be YYYY-MM-DD format
5. Use null for missing fields, not empty strings
6. Extract ALL instruments, not just the first
7. ONLY extract ISSUED instruments with issue_date, NOT capacity/incremental
8. If multiple prices (initial/reset/current), use CURRENT for conversion_price, INITIAL for original_conversion_price
"""


# =============================================================================
# EXHIBIT PATTERNS - Qué archivos contienen datos importantes
# =============================================================================

EXHIBIT_PATTERNS = {
    # Convertible Notes - Alta prioridad
    "convertible_note": [
        r"ex4[-_]?\d*\.htm",      # ex4-1.htm, ex4.htm
        r"ex10[-_]?\d*\.htm",     # ex10-1.htm (Securities Purchase Agreement)
        r"ex99[-_]?\d*\.htm",     # ex99-1.htm (often has note details)
    ],
    # Warrants
    "warrant": [
        r"ex4[-_]?\d*\.htm",
        r"ex10[-_]?\d*\.htm",
    ],
    # General exhibits
    "general": [
        r"ex\d+[-_]?\d*\.htm",
    ]
}


class GeminiExtractor:
    """
    Extractor de datos SEC usando Google Gemini.
    
    Flujo:
    1. Recibe filings con exhibits
    2. Prioriza exhibits relevantes
    3. Sube a Gemini Files API
    4. Extrae con prompt unificado
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Google API key (usa GOOGL_API_KEY_V2 del .env si no se provee)
        """
        self.api_key = api_key or settings.GOOGL_API_KEY_V2 or os.getenv("GOOGL_API_KEY_V2")
        
        if not self.api_key:
            logger.warning("gemini_api_key_not_configured")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
            logger.info("gemini_client_initialized")
        
        self.model = "gemini-2.5-flash"
        self._stats = {
            "extractions": 0,
            "exhibits_processed": 0,
            "filings_processed": 0,
            "errors": 0,
        }
    
    # =========================================================================
    # MAIN EXTRACTION METHOD
    # =========================================================================
    
    async def extract_all(
        self,
        ticker: str,
        filings: List[Dict]
    ) -> Dict[str, List]:
        """
        Extrae TODOS los instrumentos de una lista de filings.
        
        Args:
            ticker: Stock ticker
            filings: Lista de filings con estructura:
                [{
                    "url": "...",
                    "form_type": "6-K",
                    "filing_date": "2025-09-19",
                    "content": "...",
                    "exhibits": [
                        {"name": "ex99-1.htm", "url": "...", "content": "..."}
                    ]
                }]
        
        Returns:
            {
                "convertible_notes": [...],
                "warrants": [...],
                "atm_offerings": [...],
                "shelf_registrations": [...],
                "equity_lines": [...]
            }
        """
        if not self.client:
            logger.error("gemini_client_not_available", ticker=ticker)
            return self._empty_result()
        
        all_data = self._empty_result()
        
        logger.info("gemini_extraction_start", 
                   ticker=ticker, 
                   filings_count=len(filings))
        
        # Procesar cada filing
        for filing in filings:
            try:
                # 1. Primero intentar exhibits (datos más precisos)
                exhibits = filing.get('exhibits', [])
                if exhibits:
                    for exhibit in exhibits:
                        if self._is_relevant_exhibit(exhibit.get('name', '')):
                            data = await self._extract_from_content(
                                ticker=ticker,
                                content=exhibit.get('content', ''),
                                source=f"exhibit:{exhibit.get('name')}"
                            )
                            self._merge_data(all_data, data)
                            self._stats["exhibits_processed"] += 1
                
                # 2. También procesar filing principal si tiene contenido útil
                form_type = filing.get('form_type', '')
                if form_type in ['6-K', '8-K', '10-Q', '10-K', '424B5', '424B4']:
                    data = await self._extract_from_content(
                        ticker=ticker,
                        content=filing.get('content', ''),
                        source=f"filing:{form_type}"
                    )
                    self._merge_data(all_data, data)
                    self._stats["filings_processed"] += 1
                
            except Exception as e:
                logger.warning("gemini_filing_extraction_error",
                             ticker=ticker,
                             filing_url=filing.get('url'),
                             error=str(e))
                self._stats["errors"] += 1
        
        logger.info("gemini_extraction_complete",
                   ticker=ticker,
                   convertible_notes=len(all_data['convertible_notes']),
                   warrants=len(all_data['warrants']),
                   atm=len(all_data['atm_offerings']),
                   stats=self._stats)
        
        return all_data
    
    # =========================================================================
    # CONTENT EXTRACTION
    # =========================================================================
    
    async def _extract_from_content(
        self,
        ticker: str,
        content: str,
        source: str
    ) -> Dict[str, List]:
        """
        Extrae datos de contenido HTML/texto.
        
        Args:
            ticker: Stock ticker
            content: HTML content
            source: Descripción del source (para logging)
        
        Returns:
            Dict con instrumentos extraídos
        """
        if not content or len(content) < 500:
            return self._empty_result()
        
        try:
            # Si es muy grande, extraer secciones relevantes
            if len(content) > 500_000:
                content = self._extract_relevant_sections(content)
                logger.debug("content_truncated", 
                           ticker=ticker, 
                           source=source,
                           new_size=len(content))
            
            # Subir a Gemini
            uploaded_file = await self._upload_content(content)
            
            if not uploaded_file:
                return self._empty_result()
            
            # Extraer con Gemini
            start_time = time.time()
            
            # Forzar respuesta JSON para consistencia
            config = GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1  # Baja temperatura para precisión
            )
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[uploaded_file, UNIFIED_EXTRACTION_PROMPT],
                config=config
            )
            
            extraction_time = time.time() - start_time
            
            logger.info("gemini_extraction_done",
                       ticker=ticker,
                       source=source,
                       time_seconds=round(extraction_time, 1))
            
            # Cleanup
            try:
                self.client.files.delete(name=uploaded_file.name)
            except:
                pass
            
            # Parse response
            result = self._parse_response(response.text)
            self._stats["extractions"] += 1
            
            return result
            
        except Exception as e:
            logger.error("gemini_content_extraction_error",
                        ticker=ticker,
                        source=source,
                        error=str(e))
            self._stats["errors"] += 1
            return self._empty_result()
    
    async def _upload_content(self, content: str) -> Optional[Any]:
        """Sube contenido a Gemini Files API."""
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.html', 
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(content)
                temp_path = f.name
            
            uploaded = self.client.files.upload(file=temp_path)
            
            # Esperar procesamiento si necesario
            max_wait = 30
            waited = 0
            while uploaded.state.name == "PROCESSING" and waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                uploaded = self.client.files.get(name=uploaded.name)
            
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except:
                pass
            
            if uploaded.state.name == "ACTIVE":
                return uploaded
            else:
                logger.warning("gemini_upload_not_active", state=uploaded.state.name)
                return None
                
        except Exception as e:
            logger.error("gemini_upload_error", error=str(e))
            return None
    
    # =========================================================================
    # SECTION EXTRACTION (para archivos grandes)
    # =========================================================================
    
    def _extract_relevant_sections(self, html: str) -> str:
        """
        Extrae solo las secciones relevantes de un HTML grande.
        Usado para F-1, 20-F, 10-K que exceden límites de tokens.
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
        except:
            text = html
        
        sections = []
        
        # Patrones para encontrar secciones relevantes
        patterns = [
            # Convertible Notes
            r'(?i)(DESCRIPTION OF SECURITIES.*?(?=DESCRIPTION OF [A-Z]|LEGAL MATTERS|EXPERTS|\Z))',
            r'(?i)(CONVERTIBLE NOTES.*?(?=\n[A-Z]{3,}[^a-z]|\Z))',
            r'(?i)(SECURITIES PURCHASE AGREEMENT.*?(?=\n[A-Z]{3,}[^a-z]|\Z))',
            r'(?i)(NOTE PURCHASE AGREEMENT.*?(?=\n[A-Z]{3,}[^a-z]|\Z))',
            # Specific terms with context
            r'(?i)(conversion price.{0,500})',
            r'(?i)(principal amount.{0,500})',
            r'(?i)(exercise price.{0,500})',
            # Warrants
            r'(?i)(WARRANT AGREEMENT.*?(?=\n[A-Z]{3,}|\Z))',
            r'(?i)(warrants to purchase.{0,500})',
            # ATM
            r'(?i)(AT-THE-MARKET.*?(?=\n[A-Z]{3,}|\Z))',
            r'(?i)(EQUITY DISTRIBUTION.*?(?=\n[A-Z]{3,}|\Z))',
        ]
        
        for pattern in patterns:
            try:
                matches = re.findall(pattern, text, re.DOTALL)
                for match in matches[:3]:  # Max 3 matches per pattern
                    if len(match) > 100:
                        sections.append(match[:15000])  # Max 15KB per section
            except:
                continue
        
        # También extraer tablas con info relevante
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for table in soup.find_all('table'):
                table_text = table.get_text()
                keywords = ['conversion', 'principal', 'convertible', 
                           'warrant', 'exercise', 'maturity']
                if any(kw in table_text.lower() for kw in keywords):
                    sections.append(table_text[:10000])
        except:
            pass
        
        combined = '\n\n---SECTION---\n\n'.join(sections)
        
        # Limitar a 400KB para estar seguro dentro de límites de tokens
        return combined[:400000]
    
    # =========================================================================
    # RESPONSE PARSING
    # =========================================================================
    
    def _parse_response(self, response_text: str) -> Dict[str, List]:
        """Parsea la respuesta JSON de Gemini."""
        try:
            # Limpiar markdown si existe
            text = response_text.strip()
            if text.startswith('```'):
                # Remove ```json and ```
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            
            # Intentar parsear JSON
            data = json.loads(text)
            
            # Validar estructura
            result = self._empty_result()
            
            for key in result.keys():
                if key in data and isinstance(data[key], list):
                    result[key] = data[key]
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning("gemini_json_parse_error", 
                         error=str(e),
                         response_preview=response_text[:200])
            
            # Intentar extraer JSON parcial
            try:
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    data = json.loads(json_match.group())
                    result = self._empty_result()
                    for key in result.keys():
                        if key in data and isinstance(data[key], list):
                            result[key] = data[key]
                    return result
            except:
                pass
            
            return self._empty_result()
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _is_relevant_exhibit(self, filename: str) -> bool:
        """Determina si un exhibit es relevante para extracción."""
        if not filename:
            return False
        
        name_lower = filename.lower()
        
        # Patrones de exhibits importantes
        relevant_patterns = [
            r'^ex4[-_]?\d*\.htm',    # Form of Note, Warrant
            r'^ex10[-_]?\d*\.htm',   # Securities Purchase Agreement
            r'^ex99[-_]?\d*\.htm',   # Press release con detalles
        ]
        
        for pattern in relevant_patterns:
            if re.match(pattern, name_lower):
                return True
        
        return False
    
    def _merge_data(self, target: Dict, source: Dict):
        """Merge source data into target."""
        for key in target.keys():
            if key in source and isinstance(source[key], list):
                target[key].extend(source[key])
    
    def _empty_result(self) -> Dict[str, List]:
        """Retorna estructura vacía de resultado."""
        return {
            "convertible_notes": [],
            "warrants": [],
            "atm_offerings": [],
            "shelf_registrations": [],
            "equity_lines": [],
        }
    
    def get_stats(self) -> Dict:
        """Retorna estadísticas de extracción."""
        return self._stats.copy()


# =============================================================================
# SINGLETON
# =============================================================================

_extractor: Optional[GeminiExtractor] = None


def get_gemini_extractor(api_key: Optional[str] = None) -> GeminiExtractor:
    """Obtiene instancia singleton del extractor."""
    global _extractor
    if _extractor is None:
        _extractor = GeminiExtractor(api_key)
    return _extractor

