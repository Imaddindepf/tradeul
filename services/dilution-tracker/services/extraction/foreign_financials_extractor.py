"""
Foreign Financials Extractor
============================
Extractor especializado para empresas extranjeras (IFRS) que no tienen datos XBRL.
Usa Gemini 3 Pro con Google Search (Grounding) para máxima precisión.

Casos de uso:
- Empresas australianas listadas en NASDAQ (F-1, 20-F, 6-K)
- Empresas israelíes, canadienses, europeas
- Cualquier empresa sin datos XBRL estructurados
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from shared.utils.logger import get_logger

logger = get_logger(__name__)


# Gemini Configuration - Using official SDK with Grounding
GEMINI_MODEL = "gemini-3-pro-preview"  # Supports Google Search + Structured Output


# =============================================================================
# PYDANTIC MODELS FOR VALIDATION
# =============================================================================

class CashPosition(BaseModel):
    """Posición de cash extraída de SEC filings"""
    total_cash: Optional[float] = Field(None, description="Total cash in USD")
    cash_and_equivalents: Optional[float] = Field(None)
    short_term_investments: Optional[float] = Field(None)
    restricted_cash: Optional[float] = Field(None)
    period_end_date: Optional[str] = Field(None)
    source_filing: Optional[str] = Field(None)
    filing_date: Optional[str] = Field(None)
    currency_reported: Optional[str] = Field(None)
    usd_conversion_rate: Optional[float] = Field(None)


class OperatingCashFlow(BaseModel):
    quarterly_ocf: Optional[float] = Field(None)
    annual_ocf: Optional[float] = Field(None)
    period: Optional[str] = Field(None)
    source_filing: Optional[str] = Field(None)


class BurnRateAnalysis(BaseModel):
    monthly_burn_rate: Optional[float] = Field(None)
    runway_months: Optional[float] = Field(None)
    calculation_method: Optional[str] = Field(None)


class CapitalEvent(BaseModel):
    date: Optional[str] = Field(None)
    event_type: Optional[str] = Field(None)
    gross_proceeds: Optional[float] = Field(None)
    source: Optional[str] = Field(None)


class DataQuality(BaseModel):
    confidence: str = Field("LOW")
    data_age_days: Optional[int] = Field(None)
    limitations: List[str] = Field(default_factory=list)


class SourceFiling(BaseModel):
    filing_type: Optional[str] = Field(None)
    filing_date: Optional[str] = Field(None)
    url: Optional[str] = Field(None)


class ForeignFinancialsResult(BaseModel):
    ticker: str
    company_name: str
    extraction_date: str
    data_found: bool = False
    cash_position: CashPosition = Field(default_factory=CashPosition)
    operating_cash_flow: OperatingCashFlow = Field(default_factory=OperatingCashFlow)
    burn_rate_analysis: BurnRateAnalysis = Field(default_factory=BurnRateAnalysis)
    recent_capital_events: List[CapitalEvent] = Field(default_factory=list)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    sources: List[SourceFiling] = Field(default_factory=list)


# =============================================================================
# PROMPT
# =============================================================================

EXTRACTION_PROMPT = """You are a forensic financial analyst extracting cash position data from SEC filings for foreign companies.

## TARGET COMPANY
Ticker: {ticker}
Company Name: {company_name}
CIK: {cik}

## YOUR MISSION
Search SEC EDGAR and extract the MOST RECENT cash position data for this company.

## REQUIRED SEARCHES
1. Search for "{ticker} SEC 6-K cash 2024 2025"
2. Search for "{ticker} 20-F annual report cash"
3. Search for "{ticker} IPO prospectus F-1"
4. Search for "{ticker} {company_name} financial statements"

## EXTRACTION RULES
1. **Total Cash = Cash + Cash Equivalents + Short-Term Investments + Restricted Cash**
2. Extract the MOST RECENT period available
3. If currency is not USD (e.g., AUD for Australian companies), convert to USD
4. Note the exact filing date and period end date
5. Calculate burn rate from operating cash flow if available

## IMPORTANT
- ONLY use data from official SEC filings (sec.gov)
- If the company recently had an IPO, add IPO proceeds to estimate current cash
- Be conservative in estimates

## REQUIRED OUTPUT FORMAT (JSON ONLY)
Return ONLY a valid JSON object with this exact structure:

{{
  "ticker": "{ticker}",
  "company_name": "{company_name}",
  "extraction_date": "{today}",
  "data_found": true,
  "cash_position": {{
    "total_cash": <number in USD or null>,
    "cash_and_equivalents": <number or null>,
    "short_term_investments": <number or null>,
    "restricted_cash": <number or null>,
    "period_end_date": "YYYY-MM-DD or null",
    "source_filing": "6-K/20-F/F-1 or null",
    "filing_date": "YYYY-MM-DD or null",
    "currency_reported": "USD/AUD/etc or null",
    "usd_conversion_rate": <number or null>
  }},
  "operating_cash_flow": {{
    "quarterly_ocf": <number or null>,
    "annual_ocf": <number or null>,
    "period": "Q3 2024 or FY 2024 or null",
    "source_filing": "6-K/20-F or null"
  }},
  "burn_rate_analysis": {{
    "monthly_burn_rate": <number or null>,
    "runway_months": <number or null>,
    "calculation_method": "description or null"
  }},
  "recent_capital_events": [
    {{
      "date": "YYYY-MM-DD",
      "event_type": "IPO/Follow-on/ATM",
      "gross_proceeds": <number>,
      "source": "8-K/6-K/424B"
    }}
  ],
  "data_quality": {{
    "confidence": "HIGH/MEDIUM/LOW",
    "data_age_days": <number or null>,
    "limitations": ["list of caveats"]
  }},
  "sources": [
    {{
      "filing_type": "6-K/20-F/F-1",
      "filing_date": "YYYY-MM-DD",
      "url": "SEC URL or null"
    }}
  ]
}}

NOW EXTRACT FINANCIAL DATA FOR {ticker}. Return ONLY the JSON, no explanations."""

SYSTEM_PROMPT = """You are an expert financial data extractor specializing in foreign company SEC filings.
Your responses must be valid JSON only - no markdown code blocks, no explanations outside JSON.
If data is not found, set data_found to false and use null values.
Always verify your sources are from official SEC filings (sec.gov).
When extracting numbers, use USD values as plain numbers (no commas, no currency symbols)."""


# =============================================================================
# EXTRACTOR CLASS
# =============================================================================

class ForeignFinancialsExtractor:
    """
    Extractor de datos financieros para empresas extranjeras usando Gemini 3 Pro.
    Usa Google Search (Grounding) con el SDK oficial de Google GenAI.
    """
    
    def __init__(self):
        self.api_key = os.environ.get("GOOGL_API_KEY")
        if not self.api_key:
            logger.warning("foreign_financials_extractor_no_api_key")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
    
    async def extract_financials(
        self,
        ticker: str,
        company_name: str = "",
        cik: str = "",
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Extrae datos financieros de una empresa extranjera.
        
        Args:
            ticker: Símbolo del ticker
            company_name: Nombre de la empresa
            cik: CIK de la SEC (opcional)
            timeout: Timeout en segundos
            
        Returns:
            Dict con datos financieros extraídos
        """
        if not self.client:
            return self._error_response(ticker, company_name, "API key not configured")
        
        if not company_name:
            company_name = ticker
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        prompt = EXTRACTION_PROMPT.format(
            ticker=ticker,
            company_name=company_name,
            cik=cik or "Unknown",
            today=today
        )
        
        logger.info("foreign_financials_extraction_start", ticker=ticker, model=GEMINI_MODEL)
        
        try:
            import asyncio
            
            # Crear herramienta de Google Search (Grounding)
            grounding_tool = types.Tool(
                google_search=types.GoogleSearch()
            )
            
            # Configuración con Grounding + JSON output
            config = types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.1,
                max_output_tokens=8192,
                system_instruction=SYSTEM_PROMPT
            )
            
            # Llamar a Gemini con timeout robusto
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt,
                        config=config
                    ),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning("foreign_financials_timeout", ticker=ticker, timeout=timeout)
                return self._error_response(ticker, company_name, f"Timeout after {timeout}s")
            
            text = response.text if response.text else ""
            
            if not text:
                return self._error_response(ticker, company_name, "Empty response from Gemini")
            
            # Parsear JSON
            result = self._parse_and_validate_json(text, ticker, company_name, today)
            
            # Agregar metadata con info de grounding si está disponible
            grounding_metadata = {}
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    gm = candidate.grounding_metadata
                    # Manejar None explícitamente
                    search_queries = getattr(gm, 'web_search_queries', None) or []
                    grounding_chunks = getattr(gm, 'grounding_chunks', None) or []
                    grounding_metadata = {
                        "search_queries": search_queries,
                        "sources_count": len(grounding_chunks)
                    }
            
            result["_metadata"] = {
                "source": "gemini_foreign_financials_extractor",
                "model": GEMINI_MODEL,
                "extracted_at": datetime.utcnow().isoformat(),
                "ticker": ticker,
                "grounding": grounding_metadata
            }
            
            # Log success
            cash = result.get("cash_position", {}).get("total_cash")
            confidence = result.get("data_quality", {}).get("confidence", "UNKNOWN")
            
            logger.info("foreign_financials_extraction_complete",
                       ticker=ticker,
                       data_found=result.get("data_found", False),
                       total_cash=cash,
                       confidence=confidence)
            
            return result
            
        except Exception as e:
            logger.error("foreign_financials_error", ticker=ticker, error=str(e))
            return self._error_response(ticker, company_name, str(e))
    
    def _parse_and_validate_json(
        self,
        text: str,
        ticker: str,
        company_name: str,
        today: str
    ) -> Dict[str, Any]:
        """Parse JSON from Gemini response and validate with Pydantic."""
        cleaned = text.strip()
        
        # Remove markdown code blocks
        if "```json" in cleaned:
            start = cleaned.find("```json") + 7
            end = cleaned.find("```", start)
            if end > start:
                cleaned = cleaned[start:end].strip()
        elif "```" in cleaned:
            start = cleaned.find("```") + 3
            end = cleaned.find("```", start)
            if end > start:
                cleaned = cleaned[start:end].strip()
        
        # Find JSON object
        if not cleaned.startswith("{"):
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace != -1 and last_brace > first_brace:
                cleaned = cleaned[first_brace:last_brace + 1]
        
        try:
            # Parse JSON
            raw_data = json.loads(cleaned)
            
            # Override with our values (in case Gemini returns wrong ticker)
            raw_data["ticker"] = ticker
            raw_data["company_name"] = company_name
            raw_data["extraction_date"] = today
            
            # Filter only valid fields and validate with Pydantic
            valid_fields = {k: v for k, v in raw_data.items() if k in ForeignFinancialsResult.model_fields}
            result = ForeignFinancialsResult(**valid_fields)
            
            return result.model_dump()
            
        except json.JSONDecodeError as e:
            logger.error("foreign_financials_json_parse_error",
                        ticker=ticker,
                        error=str(e),
                        content=cleaned[:300])
            return self._error_response(ticker, company_name, f"JSON parse error: {str(e)}")
        except Exception as e:
            logger.error("foreign_financials_validation_error",
                        ticker=ticker,
                        error=str(e))
            return self._error_response(ticker, company_name, f"Validation error: {str(e)}")
    
    def _error_response(self, ticker: str, company_name: str, error_message: str) -> Dict[str, Any]:
        """Generate error response structure."""
        return ForeignFinancialsResult(
            ticker=ticker,
            company_name=company_name or ticker,
            extraction_date=datetime.now().strftime("%Y-%m-%d"),
            data_found=False,
            data_quality=DataQuality(
                confidence="LOW",
                limitations=[error_message]
            )
        ).model_dump() | {
            "_metadata": {
                "source": "gemini_foreign_financials_extractor",
                "extracted_at": datetime.utcnow().isoformat(),
                "error": True,
                "error_message": error_message
            }
        }


# =============================================================================
# SINGLETON & HELPER
# =============================================================================

_extractor: Optional[ForeignFinancialsExtractor] = None


def get_foreign_financials_extractor() -> ForeignFinancialsExtractor:
    """Get singleton instance of ForeignFinancialsExtractor."""
    global _extractor
    if _extractor is None:
        _extractor = ForeignFinancialsExtractor()
    return _extractor


async def extract_foreign_financials(
    ticker: str,
    company_name: str = "",
    cik: str = ""
) -> Dict[str, Any]:
    """
    Helper function to extract financials for a foreign company.
    
    Usage:
        result = await extract_foreign_financials("GELS", "Gelteq Limited")
        if result.get("data_found"):
            cash = result["cash_position"]["total_cash"]
    """
    extractor = get_foreign_financials_extractor()
    return await extractor.extract_financials(ticker, company_name, cik)
