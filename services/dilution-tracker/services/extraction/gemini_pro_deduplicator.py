"""
Gemini 3 Pro Deduplicator
=========================
Usa Gemini 3 Pro con Google Search para:
1. Identificar instrumentos duplicados semánticamente
2. Verificar y ajustar precios por stock splits
3. Consolidar datos eligiendo los mejores valores de cada fuente

ARQUITECTURA:
- Input: Lista de instrumentos con posibles duplicados
- Gemini 3 Pro + Google Search busca info de splits del ticker
- Output: Lista consolidada sin duplicados + reasoning

VENTAJA DE GOOGLE SEARCH:
- Puede buscar "TICKER stock split history" para verificar ratios
- Puede buscar "TICKER warrant exercise price" para validar precios actuales
"""

import asyncio
import json
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading

import httpx
import structlog

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# Configuración
GEMINI_MODEL = "gemini-3-pro-preview"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
REQUEST_TIMEOUT = 180.0  # 3 minutos - Pro necesita más tiempo con búsqueda

# Thread pool para llamadas síncronas
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="gemini_pro_dedup_")


# =============================================================================
# PROMPT PRINCIPAL - DEDUPLICACIÓN + SPLIT ADJUSTMENT
# =============================================================================

DEDUP_CONSOLIDATION_PROMPT = """
Eres un analista experto en SEC filings y estructura de capital. Tu tarea es CONSOLIDAR instrumentos financieros que pueden ser duplicados.

## TICKER: {ticker}
## COMPANY: {company_name}

## PASO 1: BUSCAR STOCK SPLITS
PRIMERO, busca en Google: "{ticker} stock split history reverse split"

Identifica TODOS los splits desde 2020:
- Fecha del split
- Ratio (ej: 1-for-8, 1-for-10, 2-for-1)
- Si fue reverse split (reduce shares) o forward split (aumenta shares)

## PASO 2: ANALIZAR INSTRUMENTOS EXTRAÍDOS
{instruments_json}

## PASO 3: IDENTIFICAR DUPLICADOS
Dos instrumentos son EL MISMO si:
1. Misma fecha de emisión (mes/año) + mismo tipo → 99% duplicado
2. Nombres similares ("Common Warrants" = "Shareholder Warrants" = "Investor Warrants")
3. Mismo ejercicio precio (post-split adjusted)

## PASO 4: AJUSTAR POR SPLIT (REGLA DETERMINÍSTICA)

⚠️ REGLA EXACTA - NO ASUMIR NADA:
Para CADA instrumento, compara su issue_date con CADA split_date:

```
SI issue_date < split_date → AJUSTAR:
   - exercise_price → MULTIPLICAR × split_ratio (ej: $2.50 × 10 = $25.00)
   - outstanding → DIVIDIR ÷ split_ratio (ej: 1,000,000 ÷ 10 = 100,000)
   - total_issued → DIVIDIR ÷ split_ratio (ej: 1,500,000 ÷ 10 = 150,000)
   
SI issue_date >= split_date → NO AJUSTAR (ya es post-split)
SI issue_date es NULL → NO AJUSTAR, marcar needs_review=true
```

EJEMPLO con reverse split 1-for-10 el 2025-12-12:
- Warrant emitido 2024-05-15: price $2.50→$25.00, outstanding 1M→100K
- Warrant emitido 2025-12-20: SIN CAMBIOS (post-split)

⚠️ CRÍTICO: En reverse split, los PRECIOS SUBEN y las CANTIDADES BAJAN.
NO uses heurísticas. USA SOLO LA FECHA para decidir.

## PASO 5: CONSOLIDAR DATOS
Para cada grupo de duplicados, elige:
- **series_name**: El nombre más descriptivo y claro
- **exercise_price**: 
  - Preferir 6-K/8-K sobre F-1 (precio final vs estimado)
  - AJUSTAR POR SPLIT si es necesario
- **total_issued**: El número del filing más cercano a la emisión
- **outstanding**: El número más reciente
- **expiration_date**: El del filing más reciente
- **source_filings**: COMBINAR todas las fuentes

## OUTPUT REQUERIDO (JSON):
{{
  "split_history": [
    {{
      "date": "YYYY-MM-DD",
      "ratio": "1-for-8",
      "type": "reverse",
      "multiplier": 8.0
    }}
  ],
  "merged_instruments": {{
    "warrants": [
      {{
        "series_name": "Nombre canónico final",
        "warrant_type": "Common|Pre-Funded|Private|Public",
        "exercise_price": 15.00,
        "exercise_price_pre_split": 1.50,
        "outstanding": 90000,
        "outstanding_pre_split": 900000,
        "total_issued": 100000,
        "total_issued_pre_split": 1000000,
        "split_adjusted": true,
        "split_adjustment_reason": "issue_date 2024-01-15 < split_date 2025-12-12, factor 10x",
        "issue_date": "2024-01-15",
        "expiration_date": "2029-01-15",
        "known_owners": "si se conocen",
        "underwriter_agent": "si se conoce",
        "price_protection": "Customary Anti-Dilution|Full Ratchet|None",
        "is_registered": true,
        "source_filings": ["F-1 2024-01-10", "6-K 2024-01-20"],
        "merged_from": ["original_id_1", "original_id_2"],
        "merge_reasoning": "Mismo mes de emisión, mismo tipo, nombres equivalentes"
      }}
    ],
    "convertible_notes": [...],
    "convertible_preferred": [...],
    "atm_offerings": [...],
    "shelf_registrations": [...]
  }},
  "unique_instruments": {{
    "warrants": [...],
    "convertible_notes": [...],
    "convertible_preferred": [...]
  }},
  "dedup_summary": {{
    "total_input": 15,
    "total_output": 8,
    "merged_groups": 4,
    "split_adjustments_made": 3
  }},
  "warnings": [
    "Posible warrant faltante: texto menciona Series B pero no extraído",
    "Precio de X parece incorrecto incluso post-split"
  ]
}}

## REGLAS CRÍTICAS:
1. NO inventes datos - si no tienes info, usa null
2. Si NO encuentras splits, split_history = []
3. Si un instrumento está SOLO (sin duplicados), va a unique_instruments
4. SIEMPRE incluye merge_reasoning para grupos fusionados
5. AJUSTE DE SPLIT: Decide SOLO basándote en comparar issue_date vs split_date
   - issue_date < split_date → split_adjusted=true
   - issue_date >= split_date → split_adjusted=false
   - issue_date=null → split_adjusted=false, needs_review=true
6. SIEMPRE incluye split_adjustment_reason explicando la decisión

## VALIDACIONES DE PRECIOS (RANGOS TÍPICOS - SOLO PARA REFERENCIA):
- Pre-funded warrants: $0.0001 - $0.01 (típico $0.001)
- Common warrants: $0.50 - $50.00 (típico $1-$10)
- Placement Agent: Similar a common
- SPAC Public/Private: Típico $11.50

NOTA: Estos rangos son SOLO para detectar posibles errores de extracción.
La decisión de ajustar o no se basa ÚNICAMENTE en comparar issue_date vs split_date.

ANALIZA AHORA:
"""


# =============================================================================
# PROMPT DE VALIDACIÓN COMPLETA - NUEVA CAPA
# =============================================================================

VALIDATION_PROMPT = """
Eres un analista experto en SEC filings. Tu tarea es VALIDAR Y COMPLETAR instrumentos financieros.

## TICKER: {ticker}
## COMPANY: {company_name}
## CURRENT STOCK PRICE: Busca en Google "{ticker} stock price"

## PASO 1: BUSCAR INFORMACIÓN ACTUAL EN GOOGLE
Usa tu herramienta de búsqueda Google para encontrar DATOS REALES:
1. "{ticker} stock split history site:sec.gov" - para verificar splits
2. "{ticker} 8-K recent offerings site:sec.gov" - para completed offerings
3. "{ticker} warrants outstanding 10-Q site:sec.gov" - para outstanding warrants actuales
4. "{ticker} S-1 status site:sec.gov" - para verificar status de S-1s
5. "{ticker} convertible notes outstanding site:sec.gov" - para datos de notas convertibles

CRÍTICO: Busca en el último 10-Q o 10-K los números EXACTOS de warrants outstanding.

## PASO 2: INSTRUMENTOS A VALIDAR
{instruments_json}

## PASO 3: VALIDACIONES REQUERIDAS

### A) PRECIOS DE WARRANTS
Para CADA warrant:
1. Compara exercise_price con el precio actual del stock
2. Si exercise_price es >10x el stock price actual Y hubo un reverse split después del issue_date:
   → El precio necesita DIVIDIRSE por el factor del split (ya fue ajustado erróneamente)
3. Si exercise_price es razonable (cerca o por debajo del stock price para ITM, hasta 5x para OTM):
   → El precio está correcto

EJEMPLO:
- Stock price actual: $3.76
- SPAC warrant exercise: $1,150 → INCORRECTO (ya multiplicado, dividir por 10 → $115)
- Warrant post-split: $2.10 → CORRECTO (emitido después del split)

### B) COMPLETED OFFERINGS - CRÍTICO
Busca en estos filings específicos:
- **424B4/424B5**: Contienen detalles FINALES de offerings (shares, price, amount raised)
- **8-K Item 3.02**: Unregistered sales of equity securities (private placements)
- **8-K Item 8.01**: Other events (warrant exercises, conversions)

Para CADA offering encontrado, extrae:
- offering_type: "Private Placement", "Warrant Exercise", "Public Offering", "Convertible Note"
- shares_issued: número exacto de shares
- price_per_share: precio exacto
- amount_raised: total recaudado
- offering_date: fecha exacta (YYYY-MM-DD)
- warrants_issued: si se emitieron warrants junto con el offering

### C) S-1 STATUS - CRÍTICO
Reglas de filings para determinar status:
- **S-1/F-1 sin EFFECT**: Status = "Filed"
- **S-1/F-1 con EFFECT**: Status = "Effective" 
- **RW (Request for Withdrawal)**: Status = "Withdrawn" ← BUSCA ESTE FILING
- **S-1/F-1 sin actividad >6 meses**: Status = "Abandoned"

Busca específicamente el filing "RW" vinculado al S-1 para confirmar withdrawal.

### D) CONVERTIBLE NOTES - Campos faltantes
Busca para completar:
- total_principal_amount
- conversion_price
- total_shares_when_converted
- price_protection type
- pp_clause (conversion terms)

### E) EQUITY LINES
Busca si hay algún SEPA, Equity Purchase Agreement o similar:
- Total capacity
- Remaining capacity
- Bank/counterparty name

## OUTPUT REQUERIDO (JSON):
{{
  "validated_instruments": {{
    "warrants": [
      {{
        "series_name": "nombre",
        "exercise_price": 115.00,  // Corregido si estaba mal
        "exercise_price_was_wrong": true,  // Flag si se corrigió
        "original_wrong_price": 1150.00,  // Precio incorrecto anterior
        "correction_reason": "Price was 10x too high due to split over-adjustment",
        "outstanding": 1644103,  // Actualizado si se encontró
        "total_issued": 1644103,
        "issue_date": "2024-03-15",
        "expiration_date": "2029-03-15",
        "is_registered": true,
        "price_protection": "Customary Anti-Dilution",
        "last_update_date": "2025-11-26"
      }}
    ],
    "convertible_notes": [
      {{
        "series_name": "April 2024 Cohen Convertible Note",
        "total_principal_amount": 1900000,  // COMPLETADO
        "remaining_principal_amount": 0,
        "conversion_price": 50.00,  // COMPLETADO
        "total_shares_when_converted": 38000,  // COMPLETADO
        "price_protection": "Variable Rate",
        "pp_clause": "Texto de las terms...",
        "issue_date": "2024-04-12",
        "maturity_date": "2025-03-14"
      }}
    ],
    "completed_offerings": [
      {{
        "offering_type": "Warrant Exercise",
        "shares_issued": 1074999,
        "price_per_share": 1.96,
        "amount_raised": 2106998,
        "warrants_issued": 2149998,
        "offering_date": "2025-01-13",
        "source": "8-K filing"
      }},
      {{
        "offering_type": "Private Placement",
        "shares_issued": 1185000,
        "price_per_share": 5.00,
        "amount_raised": 5925000,
        "warrants_issued": 960000,
        "offering_date": "2024-08-26",
        "source": "8-K filing"
      }}
    ],
    "equity_lines": [
      {{
        "series_name": "August 2024 YA II SEPA",
        "total_capacity": 50000000,
        "remaining_capacity": 50000000,
        "counterparty": "YA II PN Ltd",
        "agreement_start_date": "2024-08-26",
        "agreement_end_date": "2027-08-26"
      }}
    ],
    "s1_offerings": [
      {{
        "series_name": "February 2025 S-1 Offering",
        "status": "Withdrawn",  // CORREGIDO de "Filed"
        "status_was_wrong": true,
        "original_wrong_status": "Filed",
        "anticipated_deal_size": 10000000,
        "s1_filing_date": "2025-02-14",
        "last_update_date": "2025-02-14"
      }}
    ]
  }},
  "split_verification": {{
    "splits_found": [
      {{
        "date": "2025-12-12",
        "ratio": "1-for-10",
        "type": "reverse",
        "factor": 10
      }}
    ],
    "prices_corrected": 5,
    "instruments_affected": ["SPAC Warrants", "May 2024 Warrants", ...]
  }},
  "validation_summary": {{
    "warrants_corrected": 5,
    "convertibles_completed": 2,
    "offerings_found": 4,
    "equity_lines_found": 1,
    "s1_status_corrected": 1
  }},
  "data_quality_issues": [
    "Warning: Some warrant outstanding counts could not be verified",
    "Note: Convertible note June 2024 appears fully converted"
  ]
}}

## REGLAS CRÍTICAS:
1. NO inventes datos - si no encuentras info, mantén el valor original o usa null
2. SIEMPRE verifica precios contra el stock price actual - si un warrant está muy OTM (>20x), probablemente hay error de split
3. Para completed offerings, busca en 8-K filings recientes
4. INCLUYE la fuente de cada dato que completes

ANALIZA AHORA:
"""


# =============================================================================
# CLASE PRINCIPAL
# =============================================================================

class GeminiProDeduplicator:
    """
    Deduplicador usando Gemini 3 Pro con Google Search.
    
    Características:
    - Búsqueda de splits en tiempo real
    - Correlación semántica de nombres
    - Ajuste automático de precios por split
    - Consolidación inteligente de datos
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GOOGL_API_KEY") or settings.GOOGL_API_KEY
        
        if not self.api_key:
            logger.warning("gemini_pro_dedup_no_api_key")
    
    async def deduplicate_and_consolidate(
        self,
        ticker: str,
        company_name: str,
        instruments: Dict[str, List[Dict]],
        timeout: float = REQUEST_TIMEOUT
    ) -> Dict[str, Any]:
        """
        Deduplicación y consolidación completa.
        
        Args:
            ticker: Símbolo del ticker
            company_name: Nombre de la empresa
            instruments: Dict con listas de instrumentos por tipo:
                {
                    "warrants": [...],
                    "convertible_notes": [...],
                    "convertible_preferred": [...],
                    "atm_offerings": [...],
                    "shelf_registrations": [...]
                }
            timeout: Timeout en segundos
        
        Returns:
            Dict con instrumentos consolidados y metadata
        """
        if not self.api_key:
            logger.error("gemini_pro_dedup_missing_api_key")
            return self._fallback_passthrough(instruments)
        
        # Contar instrumentos
        total_instruments = sum(len(v) for v in instruments.values())
        
        if total_instruments == 0:
            logger.info("gemini_pro_dedup_no_instruments", ticker=ticker)
            return {"merged_instruments": instruments, "unique_instruments": {}}
        
        # Si hay muy pocos instrumentos, skip (no vale la pena)
        if total_instruments <= 2:
            logger.info("gemini_pro_dedup_skip_few_instruments", 
                       ticker=ticker, count=total_instruments)
            return self._fallback_passthrough(instruments)
        
        logger.info("gemini_pro_dedup_start",
                   ticker=ticker,
                   total_instruments=total_instruments,
                   breakdown={k: len(v) for k, v in instruments.items()})
        
        try:
            # Preparar prompt
            instruments_json = json.dumps(instruments, indent=2, default=str)
            prompt = DEDUP_CONSOLIDATION_PROMPT.format(
                ticker=ticker,
                company_name=company_name,
                instruments_json=instruments_json
            )
            
            # Llamar a Gemini Pro con Google Search
            result = await self._call_gemini_pro(ticker, prompt, timeout)
            
            if result:
                # Validar y limpiar resultado
                result = self._validate_result(result, instruments)
                
                logger.info("gemini_pro_dedup_complete",
                           ticker=ticker,
                           input_count=total_instruments,
                           output_count=result.get('dedup_summary', {}).get('total_output', '?'),
                           splits_found=len(result.get('split_history', [])),
                           merged_groups=result.get('dedup_summary', {}).get('merged_groups', 0))
                
                return result
            else:
                logger.warning("gemini_pro_dedup_no_result", ticker=ticker)
                return self._fallback_passthrough(instruments)
                
        except Exception as e:
            logger.error("gemini_pro_dedup_error", ticker=ticker, error=str(e))
            return self._fallback_passthrough(instruments)
    
    async def _call_gemini_pro(
        self,
        ticker: str,
        prompt: str,
        timeout: float
    ) -> Optional[Dict]:
        """
        Llama a Gemini 3 Pro con Google Search habilitado.
        """
        gemini_url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={self.api_key}"
        
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "systemInstruction": {
                "parts": [{
                    "text": """You are an expert financial analyst specializing in SEC filings, 
                    stock splits, and warrant structures. You have access to Google Search 
                    to verify current information about stock splits and prices.
                    
                    ALWAYS search for split history before analyzing instruments.
                    Return ONLY valid JSON - no markdown, no explanations outside JSON."""
                }]
            },
            "tools": [{"googleSearch": {}}],
            "generationConfig": {
                "temperature": 0.1,  # Bajo para precisión
                "topP": 0.8,
                "maxOutputTokens": 16384
            }
        }
        
        try:
            logger.info("gemini_pro_calling", ticker=ticker, model=GEMINI_MODEL)
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(gemini_url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    logger.error("gemini_pro_api_error",
                               status=response.status_code,
                               body=response.text[:500])
                    return None
                
                data = response.json()
                
                # Extraer texto de la respuesta
                candidates = data.get("candidates", [])
                if not candidates:
                    logger.warning("gemini_pro_no_candidates", ticker=ticker)
                    return None
                
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                
                text = ""
                for part in parts:
                    if "text" in part:
                        text += part["text"]
                
                if not text:
                    logger.warning("gemini_pro_empty_response", ticker=ticker)
                    return None
                
                # Parsear JSON
                return self._parse_json_response(text, ticker)
                
        except httpx.TimeoutException:
            logger.error("gemini_pro_timeout", ticker=ticker, timeout=timeout)
            return None
        except Exception as e:
            logger.error("gemini_pro_request_error", ticker=ticker, error=str(e))
            return None
    
    def _parse_json_response(self, text: str, ticker: str) -> Optional[Dict]:
        """
        Parsea la respuesta JSON de Gemini.
        Maneja casos donde hay texto extra antes/después del JSON.
        """
        text = text.strip()
        
        # Remover markdown code blocks si existen
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        # Buscar el JSON principal
        try:
            # Intentar parsear directo
            return json.loads(text)
        except json.JSONDecodeError:
            # Buscar { ... } en el texto
            start = text.find('{')
            end = text.rfind('}')
            
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError as e:
                    logger.error("gemini_pro_json_parse_error",
                               ticker=ticker,
                               error=str(e),
                               text_preview=text[:200])
                    return None
            
            logger.error("gemini_pro_no_json_found", ticker=ticker, text_preview=text[:200])
            return None
    
    def _validate_result(self, result: Dict, original: Dict) -> Dict:
        """
        Valida y limpia el resultado de Gemini.
        Asegura que la estructura es correcta.
        """
        # Asegurar estructura mínima
        if "merged_instruments" not in result:
            result["merged_instruments"] = {}
        
        if "unique_instruments" not in result:
            result["unique_instruments"] = {}
        
        if "split_history" not in result:
            result["split_history"] = []
        
        if "dedup_summary" not in result:
            # Calcular summary
            merged_count = sum(
                len(v) for v in result.get("merged_instruments", {}).values()
            )
            unique_count = sum(
                len(v) for v in result.get("unique_instruments", {}).values()
            )
            original_count = sum(len(v) for v in original.values())
            
            result["dedup_summary"] = {
                "total_input": original_count,
                "total_output": merged_count + unique_count,
                "merged_groups": merged_count,
                "split_adjustments_made": len([
                    w for w in result.get("merged_instruments", {}).get("warrants", [])
                    if w.get("split_adjusted")
                ])
            }
        
        return result
    
    def _fallback_passthrough(self, instruments: Dict) -> Dict:
        """
        Fallback: devuelve los instrumentos sin modificar.
        """
        return {
            "merged_instruments": {},
            "unique_instruments": instruments,
            "split_history": [],
            "dedup_summary": {
                "total_input": sum(len(v) for v in instruments.values()),
                "total_output": sum(len(v) for v in instruments.values()),
                "merged_groups": 0,
                "split_adjustments_made": 0
            },
            "warnings": ["Deduplication skipped - fallback mode"]
        }
    
    # =========================================================================
    # VALIDACIÓN COMPLETA - NUEVA CAPA CON GOOGLE SEARCH
    # =========================================================================
    
    async def validate_and_complete(
        self,
        ticker: str,
        company_name: str,
        instruments: Dict[str, List[Dict]],
        timeout: float = 240.0  # 4 minutos - validación es más exhaustiva
    ) -> Dict[str, Any]:
        """
        VALIDACIÓN COMPLETA con Google Search.
        
        Esta función:
        1. Verifica precios de warrants contra stock price actual
        2. Detecta y corrige errores de ajuste de split
        3. Completa campos faltantes de convertibles
        4. Busca completed offerings faltantes
        5. Detecta equity lines faltantes
        6. Corrige status de S-1s
        
        Args:
            ticker: Símbolo del ticker
            company_name: Nombre de la empresa
            instruments: Dict con instrumentos ya extraídos
            timeout: Timeout para la llamada a Gemini
            
        Returns:
            Dict con instrumentos validados y completados
        """
        if not self.api_key:
            logger.error("validate_and_complete_missing_api_key")
            return {"validated_instruments": instruments, "validation_summary": {"error": "No API key"}}
        
        total_instruments = sum(len(v) for v in instruments.values() if isinstance(v, list))
        
        logger.info("gemini_validate_start",
                   ticker=ticker,
                   total_instruments=total_instruments,
                   breakdown={k: len(v) for k, v in instruments.items() if isinstance(v, list)})
        
        try:
            # Preparar prompt de validación
            instruments_json = json.dumps(instruments, indent=2, default=str)
            prompt = VALIDATION_PROMPT.format(
                ticker=ticker,
                company_name=company_name,
                instruments_json=instruments_json
            )
            
            # Llamar a Gemini Pro con Google Search
            result = await self._call_gemini_pro(ticker, prompt, timeout)
            
            if result:
                logger.info("gemini_validate_complete",
                           ticker=ticker,
                           warrants_corrected=result.get('validation_summary', {}).get('warrants_corrected', 0),
                           convertibles_completed=result.get('validation_summary', {}).get('convertibles_completed', 0),
                           offerings_found=result.get('validation_summary', {}).get('offerings_found', 0),
                           equity_lines_found=result.get('validation_summary', {}).get('equity_lines_found', 0),
                           s1_corrected=result.get('validation_summary', {}).get('s1_status_corrected', 0))
                
                return result
            else:
                logger.warning("gemini_validate_no_result", ticker=ticker)
                return {"validated_instruments": instruments, "validation_summary": {"error": "No result from Gemini"}}
                
        except Exception as e:
            logger.error("gemini_validate_error", ticker=ticker, error=str(e))
            return {"validated_instruments": instruments, "validation_summary": {"error": str(e)}}


# =============================================================================
# SINGLETON Y HELPERS
# =============================================================================

_deduplicator_instance: Optional[GeminiProDeduplicator] = None


def get_gemini_pro_deduplicator() -> Optional[GeminiProDeduplicator]:
    """Obtiene la instancia singleton del deduplicador."""
    global _deduplicator_instance
    
    if _deduplicator_instance is None:
        api_key = os.environ.get("GOOGL_API_KEY") or getattr(settings, 'GOOGL_API_KEY', None)
        if api_key:
            _deduplicator_instance = GeminiProDeduplicator(api_key)
            logger.info("gemini_pro_deduplicator_initialized")
        else:
            logger.warning("gemini_pro_deduplicator_no_key")
    
    return _deduplicator_instance


async def deduplicate_with_gemini_pro(
    ticker: str,
    company_name: str,
    instruments: Dict[str, List[Dict]]
) -> Dict[str, Any]:
    """
    Función helper para deduplicación.
    
    Usage:
        result = await deduplicate_with_gemini_pro(
            "VMAR",
            "Vision Marine Technologies Inc",
            {
                "warrants": [...],
                "convertible_notes": [...]
            }
        )
    """
    deduplicator = get_gemini_pro_deduplicator()
    
    if deduplicator:
        return await deduplicator.deduplicate_and_consolidate(
            ticker, company_name, instruments
        )
    else:
        # Fallback sin deduplicación
        return {
            "merged_instruments": {},
            "unique_instruments": instruments,
            "split_history": [],
            "dedup_summary": {"error": "Deduplicator not available"}
        }


async def validate_with_gemini_pro(
    ticker: str,
    company_name: str,
    instruments: Dict[str, List[Dict]]
) -> Dict[str, Any]:
    """
    VALIDACIÓN COMPLETA con Gemini Pro + Google Search.
    
    Esta función va DESPUÉS de la extracción y deduplicación para:
    1. Corregir precios mal ajustados por splits
    2. Completar campos faltantes de convertibles
    3. Encontrar completed offerings
    4. Detectar equity lines faltantes
    5. Corregir status de S-1s
    
    Usage:
        validated = await validate_with_gemini_pro(
            "BNAI",
            "Brand Engagement Network Inc",
            {
                "warrants": [...],
                "convertible_notes": [...],
                "completed_offerings": [...],
                "s1_offerings": [...],
                "equity_lines": [...]
            }
        )
    """
    deduplicator = get_gemini_pro_deduplicator()
    
    if deduplicator:
        return await deduplicator.validate_and_complete(
            ticker, company_name, instruments
        )
    else:
        return {
            "validated_instruments": instruments,
            "validation_summary": {"error": "Validator not available"}
        }

