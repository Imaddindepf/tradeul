"""
Warrant Lifecycle Extractor v1.0
================================
Extrae eventos de lifecycle de warrants desde SEC filings:
- Ejercicios (cash y cashless)
- Ajustes de precio (splits, resets, anti-dilution)
- Expiraciones
- Amendments

Fuentes principales:
- 10-Q/10-K: Tablas de warrants con ejercicios/outstanding
- 8-K Item 3.02: Ejercicios materiales
- 8-K Item 5.03: Amendments de warrant agreements
- Exhibit 4.x: Warrant agreements con términos
"""

import asyncio
import json
import re
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from decimal import Decimal

import httpx
import structlog
from google import genai
from google.genai import types

logger = structlog.get_logger(__name__)


# =============================================================================
# PROMPTS PARA LIFECYCLE EXTRACTION
# =============================================================================

WARRANT_LIFECYCLE_PROMPT = """
Eres un analista experto en SEC filings extrayendo el HISTORIAL DE EVENTOS de warrants.

## FILINGS A ANALIZAR (en orden cronológico):
{filings_content}

## WARRANTS CONOCIDOS:
{known_warrants}

## TU TAREA:
Extraer TODOS los eventos de lifecycle para cada warrant:

1. **Exercise Events**: Cuando holders ejercen warrants
   - Busca frases: "exercised", "converted", "pursuant to exercise"
   - En 8-K Item 3.02: ejercicios materiales
   - En 10-Q/10-K tablas: diferencia entre periodos

2. **Price Adjustments**: Cambios en el exercise price
   - Splits/reverse splits
   - Anti-dilution adjustments
   - Reset provisions triggered
   - Amendments

3. **Expirations**: Warrants que expiran
   - Por fecha de expiración alcanzada
   - Por falta de ejercicio en periodo

4. **Amendments**: Modificaciones a los términos
   - Extensiones de fecha de expiración
   - Cambios en términos de ejercicio
   - Modificaciones de blocker

## TABLAS 10-Q/10-K:
Las tablas de warrants tienen estructura:
| Series | Issued | Exercised | Expired | Outstanding | Exercise Price | Expiration |

PARA CADA FILA, calcula:
- Si "Exercised" cambió: genera evento Exercise
- Si "Expired" cambió: genera evento Expiration
- Si "Exercise Price" cambió: genera evento Price_Adjustment

## OUTPUT (JSON):
{{
  "lifecycle_events": [
    {{
      "series_name": "Match al warrant conocido",
      "event_type": "Exercise|Cashless_Exercise|Price_Adjustment|Expiration|Amendment|Redemption|Cancellation",
      "event_date": "YYYY-MM-DD",
      "warrants_affected": <número>,
      "shares_issued": <para ejercicios>,
      "proceeds_received": <en USD si se menciona>,
      "exercise_method": "Cash|Cashless|null",
      "old_price": <para ajustes>,
      "new_price": <para ajustes>,
      "adjustment_reason": "Stock_Split|Reverse_Split|Reset_Provision|Anti_Dilution|Amendment",
      "adjustment_factor": <multiplicador si aplica>,
      "outstanding_after": <warrants restantes>,
      "source_filing": "form_type:YYYY-MM-DD"
    }}
  ],
  "price_adjustments": [
    {{
      "series_name": "nombre del warrant",
      "adjustment_date": "YYYY-MM-DD",
      "adjustment_type": "Stock_Split|Reverse_Split|Reset_Provision|Full_Ratchet|Weighted_Average|Amendment",
      "price_before": <precio antes>,
      "price_after": <precio después>,
      "quantity_before": <si aplica>,
      "quantity_after": <si aplica>,
      "trigger_event": "descripción del trigger",
      "source_filing": "form_type:YYYY-MM-DD"
    }}
  ],
  "updated_totals": [
    {{
      "series_name": "nombre del warrant",
      "as_of_date": "YYYY-MM-DD",
      "total_issued": <número>,
      "total_exercised": <número>,
      "total_expired": <número>,
      "outstanding": <número>,
      "current_exercise_price": <precio>,
      "source_filing": "form_type:YYYY-MM-DD"
    }}
  ]
}}

REGLAS:
1. Cada evento debe tener una fecha específica
2. Usa el source_filing para trazabilidad
3. Si un warrant está en "known_warrants", usa ESE nombre exacto para series_name
4. Si encuentras un nuevo warrant, usa formato "Month Year Type Warrants"
5. Para reverse splits, el quantity_after = quantity_before / factor

Return ONLY valid JSON.
"""


WARRANT_AGREEMENT_PROMPT = """
Eres un analista legal experto extrayendo términos de un WARRANT AGREEMENT (Exhibit 4.x).

## DOCUMENTO:
{document_content}

## TU TAREA:
Extraer TODOS los términos relevantes del warrant agreement.

## BUSCAR:

1. **Exercise Terms**:
   - Exercise price
   - Exercise window (start date, expiration date)
   - Exercise methods (cash, cashless)
   - Forced exercise provisions

2. **Ownership Blockers**:
   - Beneficial ownership cap (4.99%, 9.99%, 19.99%)
   - Blocker language exact
   - Waiver provisions

3. **Anti-Dilution & Price Protection**:
   - Anti-dilution provisions
   - Reset provisions
   - Full ratchet vs weighted average
   - Floor price

4. **Adjustments**:
   - Stock split adjustments
   - Dividend adjustments
   - Fundamental transaction provisions

5. **Redemption/Cancellation**:
   - Redemption rights
   - Call provisions
   - Cancellation terms

## OUTPUT (JSON):
{{
  "warrant_terms": {{
    "series_name": "nombre o descripción del warrant",
    "exercise_price": <precio>,
    "exercise_start_date": "YYYY-MM-DD",
    "expiration_date": "YYYY-MM-DD",
    "total_warrants": <número si se menciona>,
    "underlying_shares": <número si se menciona>
  }},
  "exercise_provisions": {{
    "cash_exercise": true|false,
    "cashless_exercise": true|false,
    "cashless_conditions": "descripción de cuándo aplica",
    "alternate_cashless_formula": true|false,
    "forced_exercise": true|false,
    "forced_exercise_price": <precio threshold>,
    "forced_exercise_days": <días sobre threshold>
  }},
  "ownership_blocker": {{
    "has_blocker": true|false,
    "blocker_percentage": <porcentaje como 4.99, 9.99>,
    "blocker_clause": "texto exacto del blocker",
    "waivable": true|false,
    "waiver_notice_days": <días para waiver>
  }},
  "anti_dilution": {{
    "has_anti_dilution": true|false,
    "protection_type": "Full Ratchet|Weighted Average|Customary|None",
    "floor_price": <precio mínimo>,
    "trigger_events": ["splits", "dividends", "offerings below exercise price"],
    "anti_dilution_clause": "texto de la cláusula"
  }},
  "reset_provisions": {{
    "has_reset": true|false,
    "reset_trigger": "descripción del trigger",
    "reset_formula": "descripción de cómo se calcula"
  }},
  "redemption": {{
    "redeemable": true|false,
    "redemption_price": <precio>,
    "redemption_conditions": "descripción"
  }},
  "adjustment_formula": {{
    "stock_split_adjustment": "descripción de cómo ajusta",
    "dividend_adjustment": "descripción",
    "fundamental_transaction": "descripción"
  }},
  "holder_rights": {{
    "transferable": true|false,
    "registration_rights": true|false,
    "participation_rights": true|false
  }}
}}

REGLAS:
1. Extrae el TEXTO EXACTO para cláusulas importantes (blocker, anti-dilution)
2. Si algo no está mencionado, usa null
3. Los porcentajes como 4.99% = 4.99 (no 0.0499)
4. Las fechas en formato YYYY-MM-DD

Return ONLY valid JSON.
"""


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class LifecycleExtractionResult:
    """Resultado de extracción de lifecycle"""
    lifecycle_events: List[Dict] = field(default_factory=list)
    price_adjustments: List[Dict] = field(default_factory=list)
    updated_totals: List[Dict] = field(default_factory=list)
    warrant_terms: Dict = field(default_factory=dict)


# =============================================================================
# LIFECYCLE EXTRACTOR
# =============================================================================

class WarrantLifecycleExtractor:
    """
    Extrae eventos de lifecycle de warrants.
    Usa Gemini para analizar 10-Q/10-K y 8-K filings.
    """
    
    def __init__(self, sec_api_key: str, gemini_api_key: str):
        from services.extraction.contextual_extractor import SECAPIClient
        
        self.sec_client = SECAPIClient(sec_api_key)
        
        # Configurar Gemini con timeout alto para documentos grandes
        http_options = types.HttpOptions(timeout=180000)  # 180 segundos
        self.gemini = genai.Client(api_key=gemini_api_key, http_options=http_options)
        # UPGRADE: gemini-3-pro-preview para mayor precisión en extracción de lifecycle
        self.model = "gemini-2.5-flash"
        
        logger.info("lifecycle_extractor_initialized", model=self.model)
    
    async def extract_lifecycle(
        self,
        ticker: str,
        cik: str,
        known_warrants: List[Dict],
        filings: Optional[List[Dict]] = None
    ) -> LifecycleExtractionResult:
        """
        Extrae eventos de lifecycle para warrants conocidos.
        
        Args:
            ticker: Ticker de la empresa
            cik: CIK de la SEC
            known_warrants: Lista de warrants ya identificados
            filings: Filings pre-descargados (opcional)
            
        Returns:
            LifecycleExtractionResult con todos los eventos
        """
        logger.info("lifecycle_extraction_start", ticker=ticker, warrants=len(known_warrants))
        
        result = LifecycleExtractionResult()
        
        # Obtener filings si no se proporcionaron
        if filings is None:
            all_filings = await self.sec_client.search_filings(cik, limit=200)
        else:
            all_filings = filings
        
        if not all_filings:
            logger.warning("no_filings_for_lifecycle", ticker=ticker)
            return result
        
        # Filtrar filings relevantes para lifecycle
        lifecycle_filings = self._filter_lifecycle_filings(all_filings)
        
        logger.info("lifecycle_filings_filtered", 
                   ticker=ticker,
                   total=len(all_filings),
                   lifecycle=len(lifecycle_filings))
        
        if not lifecycle_filings:
            return result
        
        # Agrupar por batch para procesamiento
        batches = self._create_batches(lifecycle_filings, max_filings=10)
        
        # Formatear warrants conocidos
        known_warrants_str = self._format_known_warrants(known_warrants)
        
        # Procesar cada batch
        for i, batch in enumerate(batches):
            logger.info("processing_lifecycle_batch", 
                       ticker=ticker,
                       batch=i+1,
                       total_batches=len(batches),
                       filings=len(batch))
            
            try:
                batch_result = await self._process_batch(batch, known_warrants_str, ticker)
                
                # Merge results
                result.lifecycle_events.extend(batch_result.get('lifecycle_events', []))
                result.price_adjustments.extend(batch_result.get('price_adjustments', []))
                result.updated_totals.extend(batch_result.get('updated_totals', []))
                
            except Exception as e:
                logger.error("lifecycle_batch_error", batch=i, error=str(e))
                continue
        
        # Deduplicate events by date + series + type
        result.lifecycle_events = self._dedupe_events(result.lifecycle_events)
        result.price_adjustments = self._dedupe_adjustments(result.price_adjustments)
        
        logger.info("lifecycle_extraction_complete",
                   ticker=ticker,
                   events=len(result.lifecycle_events),
                   adjustments=len(result.price_adjustments),
                   totals=len(result.updated_totals))
        
        return result
    
    async def extract_warrant_agreement(
        self,
        filing_url: str,
        exhibit_url: Optional[str] = None
    ) -> Dict:
        """
        Extrae términos de un Warrant Agreement (Exhibit 4.x).
        
        Args:
            filing_url: URL del filing que contiene el exhibit
            exhibit_url: URL directa del exhibit (opcional)
            
        Returns:
            Dict con términos extraídos
        """
        logger.info("warrant_agreement_extraction_start", url=(exhibit_url or filing_url)[:60])
        
        # Descargar contenido
        if exhibit_url:
            content = await self.sec_client.fetch_filing_content(exhibit_url)
        else:
            content = await self.sec_client.fetch_filing_content(filing_url)
        
        if not content or len(content) < 500:
            logger.warning("warrant_agreement_too_short", chars=len(content or ''))
            return {}
        
        # Truncar si es muy largo
        if len(content) > 150000:
            content = content[:150000]
        
        # Llamar a Gemini
        prompt = WARRANT_AGREEMENT_PROMPT.format(document_content=content)
        
        try:
            response = self.gemini.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            if response and response.text:
                result = json.loads(response.text)
                logger.info("warrant_agreement_extracted",
                           has_blocker=bool(result.get('ownership_blocker', {}).get('has_blocker')),
                           has_antidilution=bool(result.get('anti_dilution', {}).get('has_anti_dilution')))
                return result
                
        except json.JSONDecodeError as e:
            logger.error("warrant_agreement_json_error", error=str(e))
        except Exception as e:
            logger.error("warrant_agreement_extraction_error", error=str(e))
        
        return {}
    
    def _filter_lifecycle_filings(self, filings: List[Dict]) -> List[Dict]:
        """Filtra filings relevantes para lifecycle events"""
        relevant_forms = {
            '10-Q', '10-K', '10-K/A', '10-Q/A',  # Tablas de warrants
            '8-K', '8-K/A',  # Material events
            '6-K',  # Foreign private issuers
        }
        
        filtered = []
        for f in filings:
            form_type = f.get('formType', '')
            
            # Filtrar por tipo
            if form_type not in relevant_forms:
                continue
            
            # Para 8-K, verificar items relevantes
            if form_type.startswith('8-K'):
                items = f.get('items', [])
                items_str = ' '.join(items) if items else ''
                
                # Items relevantes:
                # 3.02: Sales of Unregistered Securities (ejercicios)
                # 5.03: Amendments to Articles (warrant amendments)
                # 1.01: Entry into Material Agreement (warrant agreements)
                relevant_items = ['3.02', '5.03', '1.01', '8.01']
                if not any(item in items_str for item in relevant_items):
                    continue
            
            filtered.append(f)
        
        # Ordenar por fecha (más antiguos primero)
        filtered.sort(key=lambda x: x.get('filedAt', ''))
        
        return filtered
    
    def _create_batches(self, filings: List[Dict], max_filings: int = 10) -> List[List[Dict]]:
        """Agrupa filings en batches para procesamiento"""
        batches = []
        current_batch = []
        
        for f in filings:
            current_batch.append(f)
            if len(current_batch) >= max_filings:
                batches.append(current_batch)
                current_batch = []
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    def _format_known_warrants(self, warrants: List[Dict]) -> str:
        """Formatea warrants conocidos para el prompt"""
        if not warrants:
            return "No hay warrants conocidos."
        
        lines = []
        for w in warrants:
            name = w.get('series_name', 'Unknown')
            price = w.get('exercise_price', 'N/A')
            issued = w.get('total_issued', 'N/A')
            exp = w.get('expiration_date', 'N/A')
            lines.append(f"- {name}: ${price} exercise, {issued} issued, expires {exp}")
        
        return "\n".join(lines)
    
    async def _process_batch(
        self,
        filings: List[Dict],
        known_warrants_str: str,
        ticker: str
    ) -> Dict:
        """Procesa un batch de filings para extraer eventos"""
        
        # Descargar contenido de cada filing
        contents = []
        for f in filings:
            url = f.get('linkToFilingDetails', '')
            form_type = f.get('formType', '')
            filed_at = f.get('filedAt', '')[:10]
            
            content = await self.sec_client.fetch_filing_content(url, f)
            
            if content:
                # Leer contenido completo (Gemini 2.5 Flash soporta 1M tokens)
                if len(content) > 500000:
                    content = content[:500000]
                
                contents.append(f"""
=== {form_type} ({filed_at}) ===
{content}
""")
        
        if not contents:
            return {}
        
        filings_content = "\n\n".join(contents)
        
        # Truncar total si es muy largo
        if len(filings_content) > 200000:
            filings_content = filings_content[:200000]
        
        # Llamar a Gemini
        prompt = WARRANT_LIFECYCLE_PROMPT.format(
            filings_content=filings_content,
            known_warrants=known_warrants_str
        )
        
        try:
            response = self.gemini.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            if response and response.text:
                return json.loads(response.text)
                
        except json.JSONDecodeError as e:
            logger.error("lifecycle_json_error", error=str(e))
        except Exception as e:
            logger.error("lifecycle_extraction_error", error=str(e))
        
        return {}
    
    def _dedupe_events(self, events: List[Dict]) -> List[Dict]:
        """Deduplica eventos por fecha + serie + tipo"""
        seen = set()
        result = []
        
        for e in events:
            key = (
                e.get('event_date'),
                e.get('series_name'),
                e.get('event_type')
            )
            
            if key not in seen:
                seen.add(key)
                result.append(e)
        
        return result
    
    def _dedupe_adjustments(self, adjustments: List[Dict]) -> List[Dict]:
        """Deduplica ajustes de precio por fecha + serie"""
        seen = set()
        result = []
        
        for a in adjustments:
            key = (
                a.get('adjustment_date'),
                a.get('series_name'),
                a.get('adjustment_type')
            )
            
            if key not in seen:
                seen.add(key)
                result.append(a)
        
        return result


# =============================================================================
# EXHIBIT 4.x FINDER
# =============================================================================

async def find_warrant_agreement_exhibits(
    sec_client,
    cik: str,
    ticker: str
) -> List[Dict]:
    """
    Encuentra todos los Exhibit 4.x (Warrant Agreements) para una empresa.
    
    Returns:
        Lista de dicts con exhibit info:
        - exhibit_number: "4.1", "4.2", etc.
        - filing_date: fecha del filing
        - form_type: tipo de filing
        - exhibit_url: URL directa al exhibit
        - description: descripción del exhibit
    """
    logger.info("searching_warrant_exhibits", ticker=ticker, cik=cik)
    
    # Buscar filings que típicamente tienen warrant agreements
    all_filings = await sec_client.search_filings(cik, limit=200)
    
    exhibits = []
    
    for f in all_filings:
        form_type = f.get('formType', '')
        
        # Los warrant agreements aparecen en:
        # - S-1, F-1 (registration)
        # - 8-K Item 1.01 (entry into material agreement)
        # - 10-K (annual exhibits)
        relevant_forms = ['S-1', 'F-1', 'S-1/A', 'F-1/A', '8-K', '10-K', '10-K/A', '6-K']
        if form_type not in relevant_forms:
            continue
        
        # Buscar exhibits 4.x en los documentos
        docs = f.get('documentFormatFiles', [])
        for doc in docs:
            doc_type = doc.get('type', '')
            description = doc.get('description', '').lower()
            
            # Buscar Exhibit 4.x o EX-4.x
            if doc_type.startswith('EX-4') or 'exhibit 4' in description:
                # Verificar si es warrant agreement
                warrant_keywords = ['warrant', 'exercise', 'option', 'securities purchase']
                if any(kw in description for kw in warrant_keywords) or 'EX-4' in doc_type:
                    exhibits.append({
                        'exhibit_number': doc_type.replace('EX-', ''),
                        'filing_date': f.get('filedAt', '')[:10],
                        'form_type': form_type,
                        'exhibit_url': doc.get('documentUrl'),
                        'description': doc.get('description', ''),
                        'filing_url': f.get('linkToFilingDetails')
                    })
    
    logger.info("warrant_exhibits_found", ticker=ticker, count=len(exhibits))
    return exhibits


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_lifecycle_extractor() -> Optional[WarrantLifecycleExtractor]:
    """
    Factory function para obtener el lifecycle extractor.
    Usa las API keys de settings.
    """
    from shared.config.settings import settings
    import os
    
    sec_api_key = settings.SEC_API_IO_KEY or os.getenv('SEC_API_IO', '')
    gemini_key = settings.GOOGL_API_KEY_V2 or os.getenv('GOOGL_API_KEY_V2', '')
    
    if sec_api_key and gemini_key:
        return WarrantLifecycleExtractor(sec_api_key, gemini_key)
    
    logger.warning("lifecycle_extractor_disabled", 
                   has_sec_api=bool(sec_api_key),
                   has_gemini=bool(gemini_key))
    return None

