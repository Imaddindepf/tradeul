"""
Contextual Dilution Extractor v4
================================
Nueva arquitectura que usa el CONTEXTO LARGO de Gemini (1M tokens)
para correlacionar información entre múltiples filings.

PROBLEMA RESUELTO:
- Arquitectura v3 procesaba cada filing por separado
- El mismo warrant aparecía con nombres diferentes en cada filing
- Gemini no podía correlacionar "Common Warrants" = "Shareholder Warrants"

SOLUCIÓN:
1. Agrupar filings por File Number (registration chains)
2. Procesar cada cadena con TODO su contenido junto
3. Procesar material events con CONTEXTO ACUMULADO de lo ya extraído
4. Gemini ve todo el contexto y puede identificar duplicados

FLUJO:
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Registration    │     │ Registration    │     │ Material Events │
│ Chain #1        │ →   │ Chain #2        │ →   │ (con contexto)  │
│ (F-1+424B4)     │     │ (F-3+ATM)       │     │ (6-K/8-K)       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │  Contexto Acumulado    │
                    │  (instrumentos únicos) │
                    └────────────────────────┘
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

import httpx
import structlog
from google import genai
from google.genai import types

from shared.config.settings import settings

logger = structlog.get_logger(__name__)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Gemini 2.5 Flash: 1,048,576 tokens input, 65,536 tokens output
# 4 chars ≈ 1 token → 1M tokens ≈ 4M chars
MAX_TOKENS_PER_BATCH = 900_000  # ~900K tokens (dejamos margen para prompt)
CHARS_PER_TOKEN = 4
MAX_CONTENT_PER_FILING = 500_000  # 500K chars - leer filings COMPLETOS (algunos 424B tienen 300K+)
MAX_FILINGS_PER_BATCH = 5  # Menos filings pero COMPLETOS (5 × 500K = 2.5M chars = ~625K tokens)


# =============================================================================
# PROMPTS PARA EXTRACCIÓN CON CONTEXTO
# =============================================================================

REGISTRATION_CHAIN_PROMPT = """
Eres un analista experto en SEC filings analizando una CADENA DE REGISTRO completa.

Esta cadena contiene todos los filings relacionados con un mismo File Number:
- El filing inicial (F-1, S-1, F-3, S-3)
- Amendments (F-1/A, S-1/A, etc.)
- El EFFECT (cuando se hace efectivo)
- El prospectus final (424B4, 424B5)

## TIPOS DE OFFERING:
1. **S-1/F-1**: IPO o follow-on offering (venta directa de acciones)
2. **Shelf (S-3/F-3)**: Registro para vender en el futuro (capacidad total)
3. **ATM**: At-The-Market offering (ventas graduales via placement agent)

TU TAREA:
Extraer los instrumentos dilutivos de esta cadena de registro.

OUTPUT (JSON):
{{
  "offering": {{
    "type": "S-1|F-1|Shelf|ATM",
    "series_name": "Month Year [Underwriter] Type",
    "file_number": "333-XXXXXX",
    "status": "Filed|Effective|Priced|Withdrawn",
    "filing_date": "YYYY-MM-DD",
    "effect_date": "YYYY-MM-DD or null",
    "total_capacity": <capacidad total del shelf/ATM en USD>,
    "remaining_capacity": <capacidad restante>,
    "final_deal_size": <para offerings priced>,
    "final_pricing": <precio por acción>,
    "shares_offered": <número>,
    "underwriter": "nombre del placement agent/underwriter",
    "baby_shelf_restricted": true/false
  }},
  "warrants": [
    {{
      "series_name": "Month Year Type Warrants",
      "warrant_type": "Common|Pre-Funded|Placement Agent|Underwriter",
      "exercise_price": <precio EXACTO como aparece>,
      "total_issued": <número>,
      "outstanding": <warrants restantes, si se menciona>,
      "issue_date": "YYYY-MM-DD",
      "exercisable_date": "YYYY-MM-DD",
      "expiration_date": "YYYY-MM-DD",
      "known_owners": "nombres de holders si se mencionan",
      "underwriter_agent": "nombre del underwriter/placement agent",
      "price_protection": "Customary Anti-Dilution|Full Ratchet|None",
      "is_registered": true/false
    }}
  ],
  "notes": [],
  "preferred": []
}}

REGLAS:
1. El 424B4/424B5 tiene los datos FINALES (precios reales, no rangos)
2. Si hay discrepancia entre filings, usar el MÁS RECIENTE
3. Los precios de warrants deben ser EXACTOS como aparecen

## FORMATO DE NOMBRES (CRÍTICO):
El series_name SIEMPRE debe seguir este patrón:
  [Month Year] [Calificador opcional] [Tipo de Instrumento]

Ejemplos de buenos nombres:
- "December 2025 Common Warrants"
- "December 2025 Pre-Funded Warrants"
- "December 2025 Placement Agent Warrants"
- "August 2025 S-1 Offering"
- "October 2024 ThinkEquity ATM" (incluye underwriter si es relevante)
- "December 2023 Series A Convertible Preferred"
- "January 2024 Convertible Notes"

Si hay múltiples del mismo tipo en el mismo mes, agregar numeración:
- "December 2023 Warrants 1", "December 2023 Warrants 2"

Return ONLY valid JSON.
"""

MATERIAL_EVENTS_WITH_CONTEXT_PROMPT = """
Eres un analista experto en SEC filings analizando eventos materiales (8-K/6-K).

## CONTEXTO - INSTRUMENTOS YA IDENTIFICADOS:
{existing_context}

## FILINGS A ANALIZAR (en orden cronológico):
{filings_content}

## TU TAREA:
1. Analiza cada filing buscando instrumentos dilutivos (warrants, notes, preferred, ATM)
2. ANTES de crear un nuevo instrumento, verifica si YA existe en el contexto
3. Si existe, extrae solo INFO NUEVA (ejercicios, conversiones, actualizaciones)
4. Si NO existe, créalo como NUEVO

## BUSCA TAMBIÉN ATM AGREEMENTS:
Los ATM (At-The-Market) se anuncian en 6-K/8-K como:
- "ATM Agreement" o "Sales Agreement" con placement agent
- "At-The-Market Offering Program"
- Incluye: capacidad total, placement agent, fecha de inicio

## CRÍTICO - COMPLETED OFFERINGS (424B4/424B5):
Los filings 424B4 y 424B5 contienen los DETALLES FINALES de ofertas CERRADAS:
- Busca "gross proceeds", "net proceeds", "aggregate offering price"
- Busca número exacto de shares vendidos
- Busca precio por acción del deal
- Busca warrants emitidos junto con el offering
- La FECHA del filing 424B = fecha aproximada del cierre

Ejemplos de texto en 424B:
- "We are offering X shares of common stock at $Y per share"
- "Gross proceeds of approximately $Z million"
- "Together with warrants to purchase up to X shares"

## REGLAS DE IDENTIFICACIÓN:
Los nombres pueden variar entre filings:
- "January 2025 Common Warrants" = "January 2025 Shareholder Warrants" = "January 2025 Private Placement Warrants"
- USA LA FECHA DE EMISIÓN como identificador principal
- Mismo mes/año + mismo tipo = MISMO instrumento (aunque el nombre varíe)

## REGLAS DE PRECIOS:
- Extrae el precio del filing MÁS CERCANO a la fecha de emisión
- Si un filing posterior tiene un precio MUY diferente, probablemente es PRE-SPLIT
- Precios típicos: $0.001-$50 (post-split), $100-$2000 (pre-split histórico)

## OUTPUT (JSON):
{{
  "new_instruments": {{
    "warrants": [
      {{
        "series_name": "Month Year Type Warrants",
        "warrant_type": "Common|Pre-Funded|Placement Agent|Underwriter",
        "exercise_price": <precio EXACTO>,
        "total_issued": <número>,
        "outstanding": <restantes si se menciona>,
        "issue_date": "YYYY-MM-DD",
        "exercisable_date": "YYYY-MM-DD",
        "expiration_date": "YYYY-MM-DD",
        "known_owners": "nombres de holders",
        "underwriter_agent": "ThinkEquity|Joseph Gunnar|etc",
        "price_protection": "Customary Anti-Dilution|Full Ratchet|None",
        "is_registered": true/false
      }}
    ],
    "convertible_notes": [...],
    "convertible_preferred": [...],
    "atm_offerings": [
      {{
        "series_name": "October 2024 ThinkEquity ATM",
        "total_capacity": 11750000,
        "remaining_capacity": 8500000,
        "amount_sold": 3250000,
        "placement_agent": "ThinkEquity",
        "agreement_date": "2024-10-17",
        "status": "Active|Exhausted|Terminated"
      }}
    ],
    "completed_offerings": [
      {{
        "offering_type": "Private Placement|Public Offering|Warrant Exercise|Note Conversion|ATM Sale",
        "offering_date": "YYYY-MM-DD",
        "shares_issued": <número exacto de shares>,
        "price_per_share": <precio exacto>,
        "amount_raised": <gross proceeds en USD>,
        "warrants_issued": <si se emitieron warrants junto>,
        "warrant_coverage_pct": <% warrant coverage si aplica>,
        "placement_agent": "nombre del agent",
        "source_filing": "424B5|8-K|etc",
        "notes": "detalles adicionales"
      }}
    ]
  }},
  "updates": [
    {{
      "instrument_id": "existing_series_name",
      "update_type": "exercise|conversion|amendment|info",
      "data": {{...}}
    }}
  ],
  "correlations": [
    {{
      "names": ["Common Warrants", "Shareholder Warrants"],
      "is_same_instrument": true,
      "reason": "Same issue date January 2025"
    }}
  ]
}}

IMPORTANTE:
- NO dupliques instrumentos que ya están en el contexto
- Si el filing solo MENCIONA un instrumento existente, ponlo en "updates" no en "new"
- Los precios de tablas históricas NO son precios actuales

## FORMATO DE NOMBRES (CRÍTICO):
El series_name SIEMPRE debe seguir este patrón:
  [Month Year] [Calificador opcional] [Tipo de Instrumento]

Ejemplos de buenos nombres:
- "December 2025 Common Warrants"
- "January 2025 Pre-Funded Warrants"
- "September 2024 Placement Agent Warrants"
- "December 2023 Series A Convertible Preferred"
- "December 2023 Series B Convertible Preferred"
- "May 2022 Convertible Notes"

Si hay múltiples del mismo tipo en el mismo mes, distinguir con:
- Series: "April 2024 Series A Warrants", "April 2024 Series B Warrants"
- Holder: "January 2024 Perceptive Warrants"
- Número: "December 2023 Warrants 1", "December 2023 Warrants 2"

Return ONLY valid JSON.
"""


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class ExtractedInstrument:
    """Instrumento extraído con trazabilidad"""
    type: str  # warrant, note, preferred
    series_name: str
    data: Dict[str, Any]
    source_filings: List[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class ExtractionContext:
    """Contexto acumulado durante la extracción"""
    ticker: str
    warrants: List[Dict] = field(default_factory=list)
    convertible_notes: List[Dict] = field(default_factory=list)
    convertible_preferred: List[Dict] = field(default_factory=list)
    s1_offerings: List[Dict] = field(default_factory=list)
    shelf_registrations: List[Dict] = field(default_factory=list)
    atm_offerings: List[Dict] = field(default_factory=list)
    completed_offerings: List[Dict] = field(default_factory=list)  # NUEVO: offerings cerrados
    # Idempotencia / trazabilidad (no serializable a output final)
    processed_accessions: set = field(default_factory=set, repr=False)
    
    def to_context_string(self) -> str:
        """Genera string de contexto para el prompt"""
        lines = []
        
        if self.s1_offerings:
            lines.append("### S-1/F-1 OFFERINGS:")
            for o in self.s1_offerings:
                lines.append(f"  - {o.get('series_name')}: ${o.get('final_deal_size')} @ ${o.get('final_pricing')}")
        
        if self.shelf_registrations:
            lines.append("\n### SHELF REGISTRATIONS:")
            for s in self.shelf_registrations:
                lines.append(f"  - {s.get('series_name')}: ${s.get('total_capacity')} capacity")
        
        if self.atm_offerings:
            lines.append("\n### ATM OFFERINGS:")
            for a in self.atm_offerings:
                lines.append(f"  - {a.get('series_name')}: ${a.get('total_capacity')} capacity")
        
        if self.warrants:
            lines.append("\n### WARRANTS YA IDENTIFICADOS:")
            for w in self.warrants:
                lines.append(f"  - {w.get('series_name')}: ${w.get('exercise_price')} exercise, {w.get('total_issued')} issued")
                lines.append(f"    Issue date: {w.get('issue_date')}, Sources: {w.get('_sources', [])}")
        
        if self.convertible_notes:
            lines.append("\n### CONVERTIBLE NOTES YA IDENTIFICADOS:")
            for n in self.convertible_notes:
                lines.append(f"  - {n.get('series_name')}: ${n.get('total_principal_amount')} @ ${n.get('conversion_price')}")
        
        if self.convertible_preferred:
            lines.append("\n### CONVERTIBLE PREFERRED YA IDENTIFICADOS:")
            for p in self.convertible_preferred:
                lines.append(f"  - {p.get('series_name')}: ${p.get('total_dollar_amount_issued')} @ ${p.get('conversion_price')}")
        
        if not lines:
            return "No hay instrumentos identificados aún."
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario para resultado final"""
        result = {
            'warrants': self.warrants,
            'convertible_notes': self.convertible_notes,
            'convertible_preferred': self.convertible_preferred,
            's1_offerings': self.s1_offerings,
            'shelf_registrations': self.shelf_registrations,
            'atm_offerings': self.atm_offerings,
            'completed_offerings': self.completed_offerings,  # NUEVO
        }
        # Propagar flag de Gemini Pro para evitar doble ajuste de splits
        if hasattr(self, '_gemini_pro_adjusted') and self._gemini_pro_adjusted:
            result['_gemini_pro_adjusted'] = True
        return result


# =============================================================================
# CLIENTE SEC-API.IO
# =============================================================================

class SECAPIClient:
    """Cliente para SEC-API.io"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sec-api.io"
        self.filing_reader_url = "https://api.sec-api.io/filing-reader"
        self.sec_headers = {
            "User-Agent": "TradeUL Research contact@tradeul.com",
            "Accept": "text/plain,text/html"
        }
    
    async def search_filings(self, cik: str, limit: int = 300) -> List[Dict]:
        """Busca todos los filings de una empresa"""
        # Limpiar CIK - remover ceros iniciales para query
        cik_clean = cik.lstrip('0') if cik else cik
        
        async with httpx.AsyncClient(timeout=60) as client:
            all_filings = []
            offset = 0
            page_size = 50
            
            while offset < limit:
                query = {
                    "query": {"query_string": {"query": f"cik:{cik_clean}"}},
                    "from": offset,
                    "size": min(page_size, limit - offset),
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
                
                response = await client.post(
                    f"{self.base_url}?token={self.api_key}",
                    json=query,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code != 200:
                    logger.error("sec_api_error", status=response.status_code)
                    break
                
                data = response.json()
                filings = data.get('filings', [])
                
                if not filings:
                    break
                
                all_filings.extend(filings)
                offset += len(filings)
                
                logger.debug("sec_api_page_fetched", offset=offset, count=len(filings))
            
            logger.info("sec_api_filings_fetched", total=len(all_filings), cik=cik)
            return all_filings
    
    async def fetch_filing_content(self, url: str, filing_data: Optional[Dict] = None, 
                                     extract_sections: bool = True) -> Optional[str]:
        """
        Descarga el contenido de un filing.
        Prioriza el archivo .txt completo que contiene todo el texto.
        
        Args:
            url: URL del filing
            filing_data: Metadatos del filing
            extract_sections: Si True, extrae solo secciones relevantes para dilución
        """
        import re
        from bs4 import BeautifulSoup
        from services.extraction.section_extractor import (
            extract_sections_for_dilution,
            clean_html_preserve_structure
        )
        
        # Método 1: Buscar archivo .txt completo en los documentos del filing
        if filing_data:
            docs = filing_data.get('documentFormatFiles', [])
            for doc in docs:
                doc_url = doc.get('documentUrl', '')
                if doc_url.endswith('.txt') and 'submission' in doc.get('description', '').lower():
                    txt_content = await self._fetch_sec_direct(doc_url)
                    if txt_content and len(txt_content) > 1000:
                        logger.debug("filing_txt_fetched", url=doc_url[:60], chars=len(txt_content))
                        return txt_content
        
        # Método 2: Construir URL del .txt desde la URL del filing
        # URL típica: .../000110465925123289/tm2534000d1_6k.htm
        # TXT URL:    .../000110465925123289/0001104659-25-123289.txt
        txt_url = self._build_txt_url(url)
        if txt_url:
            txt_content = await self._fetch_sec_direct(txt_url)
            if txt_content and len(txt_content) > 1000:
                logger.debug("filing_txt_constructed", url=txt_url[:60], chars=len(txt_content))
                return txt_content
        
        # Método 3: SEC-API.io filing-reader (fallback)
        try:
            full_url = f"{self.filing_reader_url}?token={self.api_key}&url={url}"
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(full_url)
                
                if response.status_code == 200:
                    content = response.text
                    
                    # Detectar si es PDF binario
                    if content.startswith('%PDF') or '%PDF-' in content[:100]:
                        logger.debug("filing_is_pdf_skipping", url=url[:60])
                        return self._try_pdf_fallback(url)
                    
                    # v4.1: Limpiar HTML preservando estructura de tablas
                    try:
                        text = clean_html_preserve_structure(content)
                        
                        # v4.1: Extraer solo secciones relevantes para dilución
                        if extract_sections and len(text) > 50000:
                            text = extract_sections_for_dilution(text)
                        
                        return text[:200000]
                    except Exception:
                        content = re.sub(r'<[^>]+>', ' ', content)
                        content = re.sub(r'\s+', ' ', content)
                        return content[:200000]
                
                return None
        except Exception as e:
            logger.warning("filing_fetch_error", url=url[:50], error=str(e))
            return None
    
    def _build_txt_url(self, htm_url: str) -> Optional[str]:
        """Construye la URL del archivo .txt completo desde la URL del filing"""
        import re
        # Extraer el accession number del path
        # Ejemplo: /000110465925123289/tm2534000d1_6k.htm -> 0001104659-25-123289.txt
        match = re.search(r'/(\d{18})/[^/]+\.htm', htm_url)
        if match:
            acc_no_raw = match.group(1)  # 000110465925123289
            # Formatear: 0001104659-25-123289
            acc_formatted = f"{acc_no_raw[:10]}-{acc_no_raw[10:12]}-{acc_no_raw[12:]}"
            base_url = htm_url.rsplit('/', 1)[0]
            return f"{base_url}/{acc_formatted}.txt"
        return None
    
    async def _fetch_sec_direct(self, url: str) -> Optional[str]:
        """Descarga contenido directamente de SEC.gov"""
        from services.extraction.section_extractor import clean_html_preserve_structure
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=self.sec_headers)
                if response.status_code == 200:
                    content = response.text
                    # Verificar que no es error de SEC
                    if 'Request Originates from an Undeclared' in content:
                        logger.warning("sec_rate_limited", url=url[:60])
                        return None
                    
                    # v4.1: Limpiar preservando estructura si tiene HTML
                    if '<html' in content.lower() or '<table' in content.lower():
                        content = clean_html_preserve_structure(content)
                    
                    return content[:200000]
        except Exception as e:
            logger.debug("sec_direct_fetch_error", url=url[:50], error=str(e))
        return None
    
    def _try_pdf_fallback(self, url: str) -> Optional[str]:
        """
        v4.1: Intenta extraer texto de PDF usando pypdf.
        Fallback best-effort para no perder exhibits importantes.
        """
        try:
            import pypdf
            import io
            import httpx
            
            # Descargar PDF
            with httpx.Client(timeout=30) as client:
                response = client.get(url, headers=self.sec_headers)
                if response.status_code != 200:
                    return None
                
                pdf_bytes = response.content
            
            # Extraer texto
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            
            for page in reader.pages[:50]:  # Máximo 50 páginas
                try:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                except Exception:
                    continue
            
            if text_parts:
                combined = '\n\n'.join(text_parts)
                logger.info("pdf_text_extracted", url=url[:50], chars=len(combined))
                return combined[:100000]
            
            logger.warning("pdf_no_text_extracted", url=url[:50])
            return None
            
        except ImportError:
            logger.debug("pypdf_not_installed_skip_pdf", url=url[:50])
            return None
        except Exception as e:
            logger.warning("pdf_extraction_failed", url=url[:50], error=str(e))
            return None


# =============================================================================
# EXTRACTOR CONTEXTUAL PRINCIPAL
# =============================================================================

class ContextualDilutionExtractor:
    """
    Extractor que mantiene contexto entre filings.
    Usa el contexto largo de Gemini (1M tokens) para correlacionar datos.
    """
    
    def __init__(self, sec_api_key: str, gemini_api_key: str):
        self.sec_client = SECAPIClient(sec_api_key)
        
        # v4.1: Configurar timeout de 120 segundos para evitar que se cuelgue
        # con requests muy grandes (800K+ chars)
        http_options = types.HttpOptions(timeout=120000)  # 120 segundos en ms
        self.gemini = genai.Client(api_key=gemini_api_key, http_options=http_options)
        self.model = "gemini-2.5-flash"
        
        logger.info("contextual_extractor_initialized", model=self.model, timeout_ms=120000)
    
    async def extract_all(self, ticker: str, cik: str, company_name: str = "", use_gemini_pro_dedup: bool = True) -> Dict:
        """
        Extracción completa con contexto acumulado.
        
        Args:
            ticker: Símbolo del ticker
            cik: CIK de la empresa
            company_name: Nombre de la empresa (para Gemini Pro)
            use_gemini_pro_dedup: Si True, usa Gemini 3 Pro para deduplicación inteligente
        
        Returns:
            Dict con todos los instrumentos extraídos, deduplicados por contexto
        """
        logger.info("contextual_extraction_start", ticker=ticker, cik=cik, 
                   gemini_pro_dedup=use_gemini_pro_dedup)
        
        # Inicializar contexto
        context = ExtractionContext(ticker=ticker)
        
        # PASO 1: Obtener todos los filings
        all_filings = await self.sec_client.search_filings(cik, limit=300)
        
        if not all_filings:
            logger.warning("no_filings_found", ticker=ticker)
            return context.to_dict()
        
        # PASO 2: Categorizar filings (híbrido: registro vs transacciones)
        registration_chains, transaction_filings, financials = self._categorize_filings(all_filings)
        
        logger.info("filings_categorized",
                   ticker=ticker,
                   chains=len(registration_chains),
                   events=len(transaction_filings),
                   financials=len(financials))
        
        # PASO 3: Procesar registration chains (cada una actualiza el contexto)
        for file_no, chain_filings in registration_chains.items():
            await self._process_registration_chain(file_no, chain_filings, context)
        
        # PASO 4: Procesar transacciones (424B/8-K/6-K) por accessionNo CON CONTEXTO
        await self._process_transactions_with_context(transaction_filings, context)
        
        # DEBUG: Log estado antes de deduplicación
        logger.info("pre_dedup_state",
                   ticker=ticker,
                   raw_warrants=len(context.warrants),
                   raw_notes=len(context.convertible_notes),
                   raw_preferred=len(context.convertible_preferred),
                   raw_atm=len(context.atm_offerings),
                   raw_shelf=len(context.shelf_registrations))
        
        # =========================================================================
        # PASO 5: DEDUPLICACIÓN - Gemini 3 Pro vs Heurística
        # =========================================================================
        
        if use_gemini_pro_dedup:
            # v4.4: Usar Gemini 3 Pro con Google Search para deduplicación inteligente
            # - Busca splits en tiempo real
            # - Ajusta precios automáticamente
            # - Correlaciona nombres semánticamente
            context = await self._gemini_pro_dedup(ticker, company_name, context)
        else:
            # Fallback: Pipeline heurístico original (v4.1-v4.3)
            # PASO 5a: Validación two-pass
            context.warrants = self._validate_instruments(context.warrants, 'warrant')
            context.convertible_notes = self._validate_instruments(context.convertible_notes, 'note')
            
            # PASO 5b: Deduplicación semántica con IDs deterministas
            context.warrants = self._semantic_deduplicate(context.warrants, 'warrant')
            context.convertible_notes = self._semantic_deduplicate(context.convertible_notes, 'note')
            context.convertible_preferred = self._semantic_deduplicate(context.convertible_preferred, 'preferred')
            
            logger.info("post_semantic_dedup",
                       ticker=ticker,
                       dedup_warrants=len(context.warrants),
                       dedup_notes=len(context.convertible_notes),
                       dedup_preferred=len(context.convertible_preferred))
            
            # PASO 5c: Event-Sourced Resolution - resuelve conflictos F-1 vs 6-K
            context.warrants = self._resolve_source_conflicts(context.warrants, 'warrant')
            context.convertible_notes = self._resolve_source_conflicts(context.convertible_notes, 'note')
            context.convertible_preferred = self._resolve_source_conflicts(context.convertible_preferred, 'preferred')
        
        # DEBUG: Log estado después de deduplicación
        logger.info("post_dedup_state",
                   ticker=ticker,
                   method="gemini_pro" if use_gemini_pro_dedup else "heuristic",
                   final_warrants=len(context.warrants),
                   final_notes=len(context.convertible_notes),
                   final_preferred=len(context.convertible_preferred))
        
        # PASO 6: Filtrar warrants (remover underwriter/placement agent)
        context.warrants = self._filter_warrants(context.warrants)
        
        logger.info("contextual_extraction_complete",
                   ticker=ticker,
                   warrants=len(context.warrants),
                   notes=len(context.convertible_notes),
                   preferred=len(context.convertible_preferred),
                   s1=len(context.s1_offerings),
                   shelf=len(context.shelf_registrations),
                   atm=len(context.atm_offerings),
                   completed=len(context.completed_offerings))
        
        return context.to_dict()
    
    async def _gemini_pro_dedup(self, ticker: str, company_name: str, context: ExtractionContext) -> ExtractionContext:
        """
        v4.4: Deduplicación inteligente con Gemini 3 Pro + Google Search.
        
        Ventajas:
        - Busca stock splits en tiempo real
        - Ajusta precios automáticamente por split
        - Correlaciona nombres semánticamente (Common = Shareholder = Investor)
        - Consolida datos eligiendo las mejores fuentes
        """
        try:
            from services.extraction.gemini_pro_deduplicator import deduplicate_with_gemini_pro
            
            # Preparar instrumentos para dedup
            instruments = {
                "warrants": context.warrants,
                "convertible_notes": context.convertible_notes,
                "convertible_preferred": context.convertible_preferred,
                "atm_offerings": context.atm_offerings,
                "shelf_registrations": context.shelf_registrations
            }
            
            # Llamar a Gemini Pro
            result = await deduplicate_with_gemini_pro(
                ticker=ticker,
                company_name=company_name or ticker,
                instruments=instruments
            )
            
            # Extraer resultados
            merged = result.get("merged_instruments", {})
            unique = result.get("unique_instruments", {})
            split_history = result.get("split_history", [])
            summary = result.get("dedup_summary", {})
            warnings = result.get("warnings", [])
            
            # Log resultados
            logger.info("gemini_pro_dedup_result",
                       ticker=ticker,
                       input=summary.get("total_input", "?"),
                       output=summary.get("total_output", "?"),
                       merged_groups=summary.get("merged_groups", 0),
                       split_adjustments=summary.get("split_adjustments_made", 0),
                       splits_found=len(split_history),
                       warnings=warnings)
            
            # Combinar merged + unique
            context.warrants = merged.get("warrants", []) + unique.get("warrants", [])
            context.convertible_notes = merged.get("convertible_notes", []) + unique.get("convertible_notes", [])
            context.convertible_preferred = merged.get("convertible_preferred", []) + unique.get("convertible_preferred", [])
            context.atm_offerings = merged.get("atm_offerings", []) + unique.get("atm_offerings", [])
            context.shelf_registrations = merged.get("shelf_registrations", []) + unique.get("shelf_registrations", [])
            
            # Guardar metadata de split para referencia
            if split_history:
                context._split_history = split_history
            
            # Marcar que Gemini Pro ya ajustó precios por split
            # Esto evita que Python vuelva a ajustar (doble ajuste)
            split_adjustments = summary.get("split_adjustments_made", 0)
            if split_adjustments > 0 or split_history:
                context._gemini_pro_adjusted = True
                logger.info("gemini_pro_marked_adjusted", 
                           ticker=ticker, 
                           split_adjustments=split_adjustments,
                           splits=len(split_history))
            
            return context
            
        except ImportError as e:
            logger.warning("gemini_pro_dedup_import_error", error=str(e))
            # Fallback a heurística
            return await self._fallback_heuristic_dedup(ticker, context)
        except Exception as e:
            logger.error("gemini_pro_dedup_error", ticker=ticker, error=str(e))
            # Fallback a heurística
            return await self._fallback_heuristic_dedup(ticker, context)
    
    async def _fallback_heuristic_dedup(self, ticker: str, context: ExtractionContext) -> ExtractionContext:
        """Fallback a deduplicación heurística si Gemini Pro falla."""
        logger.info("fallback_to_heuristic_dedup", ticker=ticker)
        
        # Validación
        context.warrants = self._validate_instruments(context.warrants, 'warrant')
        context.convertible_notes = self._validate_instruments(context.convertible_notes, 'note')
        
        # Dedup semántica
        context.warrants = self._semantic_deduplicate(context.warrants, 'warrant')
        context.convertible_notes = self._semantic_deduplicate(context.convertible_notes, 'note')
        context.convertible_preferred = self._semantic_deduplicate(context.convertible_preferred, 'preferred')
        
        # Resolución de conflictos
        context.warrants = self._resolve_source_conflicts(context.warrants, 'warrant')
        context.convertible_notes = self._resolve_source_conflicts(context.convertible_notes, 'note')
        context.convertible_preferred = self._resolve_source_conflicts(context.convertible_preferred, 'preferred')
        
        return context
    
    def _semantic_deduplicate(self, instruments: List[Dict], inst_type: str) -> List[Dict]:
        """
        Deduplicación semántica usando embeddings.
        Agrupa instrumentos similares y mergea tomando los mejores datos.
        
        Args:
            instruments: Lista de instrumentos a deduplicar
            inst_type: Tipo ('warrant', 'note', 'preferred')
            
        Returns:
            Lista deduplicada
        """
        if not instruments or len(instruments) <= 1:
            return instruments
        
        try:
            from services.extraction.semantic_deduplicator import SemanticDeduplicator
            
            deduplicator = SemanticDeduplicator(similarity_threshold=0.85)
            result = deduplicator.deduplicate(instruments, inst_type)
            
            logger.info("semantic_dedup_result",
                       inst_type=inst_type,
                       original=result.original_count,
                       deduplicated=result.deduplicated_count,
                       clusters=len(result.merged_clusters))
            
            return result.final_instruments
            
        except Exception as e:
            logger.error("semantic_dedup_error", 
                        inst_type=inst_type, 
                        error=str(e))
            # Fallback: devolver original sin deduplicar
            return instruments
    
    def _resolve_source_conflicts(self, instruments: List[Dict], inst_type: str) -> List[Dict]:
        """
        v4.2: Event-Sourced Resolution - resuelve conflictos entre fuentes.
        
        Problema que resuelve:
        - El F-1 prospectus tiene precio ESTIMADO ($0.6625)
        - El 6-K closing tiene precio FINAL ($0.375)
        - Ambos son el MISMO warrant pero con datos diferentes
        
        Solución:
        - Agrupar por MES + TIPO (no por fileNo)
        - Priorizar 6-K/8-K > 424B4 > F-1 para precios/cantidades
        - Conservar términos del F-1 si no están en 6-K
        
        Returns:
            Lista de instrumentos con conflictos resueltos
        """
        if not instruments or len(instruments) <= 1:
            return instruments
        
        try:
            from services.extraction.instrument_resolver import resolve_instrument_duplicates
            
            before_count = len(instruments)
            resolved = resolve_instrument_duplicates(instruments)
            after_count = len(resolved)
            
            if before_count != after_count:
                logger.info("source_conflicts_resolved",
                           inst_type=inst_type,
                           before=before_count,
                           after=after_count,
                           merged=before_count - after_count)
            
            return resolved
            
        except Exception as e:
            logger.error("source_conflict_resolution_error",
                        inst_type=inst_type,
                        error=str(e))
            # Fallback: devolver sin resolver
            return instruments
    
    def _validate_instruments(self, instruments: List[Dict], inst_type: str) -> List[Dict]:
        """
        v4.1: Two-pass validation - verifica y corrige datos extraídos.
        
        - Detecta precios alucinados (ej: pre-funded con $125)
        - Agrega confidence scores
        - Aplica correcciones automáticas de alta confianza
        """
        if not instruments:
            return instruments
        
        try:
            from services.extraction.validator import validate_warrant, apply_corrections
            
            validated = []
            corrected_count = 0
            flagged_count = 0
            
            for inst in instruments:
                if inst_type == 'warrant':
                    # Usar texto fuente si está disponible, o string vacío
                    source_text = inst.get('_source_text', '')
                    result = validate_warrant(inst, source_text)
                    
                    # Agregar metadata de validación
                    inst['_validation_confidence'] = result.confidence_score
                    
                    if result.issues:
                        inst['_validation_issues'] = [
                            {'field': i.field, 'severity': i.severity, 'message': i.message}
                            for i in result.issues
                        ]
                        flagged_count += 1
                    
                    # Aplicar correcciones automáticas
                    if result.corrected_values:
                        inst = apply_corrections(inst, result)
                        corrected_count += 1
                    
                    # Solo incluir si no tiene errores críticos
                    if result.is_valid or result.confidence_score >= 0.5:
                        validated.append(inst)
                    else:
                        logger.warning("instrument_rejected_by_validation",
                                     name=inst.get('series_name'),
                                     issues=[i.message for i in result.issues if i.severity == 'error'])
                else:
                    validated.append(inst)
            
            if corrected_count > 0 or flagged_count > 0:
                logger.info("validation_complete",
                          inst_type=inst_type,
                          total=len(instruments),
                          flagged=flagged_count,
                          corrected=corrected_count,
                          rejected=len(instruments) - len(validated))
            
            return validated
            
        except ImportError as e:
            logger.warning("validator_not_available", error=str(e))
            return instruments
        except Exception as e:
            logger.error("validation_error", inst_type=inst_type, error=str(e))
            return instruments
    
    def _filter_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Filtra warrants según las reglas de DilutionTracker:
        - MANTENER: Common Warrants, Pre-Funded Warrants, Public Warrants, Private Warrants (SPAC)
        - REMOVER: Underwriter Warrants, Placement Agent Warrants
        
        FIX v4.3: NO filtrar SPAC Private Warrants.
        Los Private Warrants de un SPAC son para sponsors/affiliates y SON dilutivos.
        Solo filtrar si el NOMBRE explícitamente dice "placement agent" o "underwriter".
        """
        filtered = []
        removed_count = 0
        
        for w in warrants:
            if not isinstance(w, dict):
                continue
            name = (w.get('series_name') or '').lower()
            warrant_type = (w.get('warrant_type') or '').lower()
            
            # SPAC Private Warrants - NO FILTRAR
            # Detectar si es un SPAC private warrant (para sponsors/affiliates)
            is_spac_private = (
                'private' in name or 
                'pipe' in name or
                'sponsor' in name or
                'founder' in name
            )
            
            # Si es private warrant, mantener (incluso si warrant_type dice placement agent por error del LLM)
            if is_spac_private:
                filtered.append(w)
                continue
            
            # Patrones a filtrar - solo si el NOMBRE explícitamente los menciona
            # (no confiar en warrant_type que puede ser mal extraído por el LLM)
            is_underwriter = 'underwriter warrant' in name or 'underwriter' in name
            is_placement_agent = 'placement agent warrant' in name or 'placement agent' in name
            
            if is_underwriter or is_placement_agent:
                removed_count += 1
                logger.debug("warrant_filtered",
                           name=w.get('series_name'),
                           reason="underwriter/placement_agent")
                continue
            
            filtered.append(w)
        
        if removed_count > 0:
            logger.info("warrants_filtered",
                       removed=removed_count,
                       remaining=len(filtered))
        
        return filtered
    
    def _categorize_filings(self, filings: List[Dict]) -> Tuple[Dict, List, List]:
        """
        Categoriza filings siguiendo la tabla de referencia:
        - Registro (fileNo): S-1/F-1/S-3/F-3 + amendments/EFFECT/RW/MEF/LETTER
        - Transacciones/Eventos (filingID/accessionNo): 424B4/424B5 + 8-K/6-K (incluye /A)
        - Financials: 10-Q/10-K/20-F/40-F (para futuras mejoras de outstanding/remaining)
        """
        registration_chains: Dict[str, List[Dict]] = {}
        transaction_filings: List[Dict] = []
        financials: List[Dict] = []
        
        for f in filings:
            form = (f.get('formType') or '').upper()
            
            # Extraer fileNo de entities (estructura SEC-API.io)
            file_no = None
            entities = f.get('entities', [])
            if entities and isinstance(entities, list) and len(entities) > 0:
                file_no = entities[0].get('fileNo')
            # Fallback a campos directos
            if not file_no:
                file_no = f.get('fileNumber') or f.get('fileNo')
            
            # Transacciones/Eventos
            if form in ['8-K', '6-K', '8-K/A', '6-K/A', '424B4', '424B5', '424B2', '424B3']:
                transaction_filings.append(f)
            
            # Financials
            elif form in ['10-Q', '10-K', '20-F', '40-F']:
                financials.append(f)
            
            # Registro (con File Number 333-XXXXXX)
            # Nota: NO metemos 424B aquí; los tratamos como transacciones atómicas.
            elif file_no and file_no.startswith('333-') and any(x in form for x in ['S-1', 'F-1', 'S-3', 'F-3', 'EFFECT', 'RW', 'MEF', 'LETTER']):
                if file_no not in registration_chains:
                    registration_chains[file_no] = []
                registration_chains[file_no].append(f)
        
        return registration_chains, transaction_filings, financials
    
    async def _process_registration_chain(
        self, 
        file_no: str, 
        chain_filings: List[Dict],
        context: ExtractionContext
    ):
        """
        Procesa una cadena de registro completa.
        Descarga todos los filings y los envía juntos a Gemini.
        """
        if not chain_filings:
            return
        
        # Ordenar por fecha
        chain_filings.sort(key=lambda x: x.get('filedAt', ''))
        
        # Determinar tipo de cadena
        forms = [f.get('formType', '').upper() for f in chain_filings]
        
        if any('S-1' in f or 'F-1' in f for f in forms):
            chain_type = "IPO/Follow-on"
        elif any('S-3' in f or 'F-3' in f for f in forms):
            chain_type = "Shelf/ATM"
        else:
            logger.debug("chain_skip_unknown_type", file_no=file_no, forms=forms)
            return
        
        logger.debug("processing_chain", 
                    file_no=file_no, 
                    chain_type=chain_type,
                    filings=len(chain_filings))
        
        # Descargar contenido de filings clave (424B4, 424B5, o el más reciente)
        key_filings = self._select_key_filings(chain_filings)
        
        logger.debug("chain_key_filings_selected",
                    file_no=file_no,
                    key_forms=[f.get('formType') for f in key_filings])
        
        contents = []
        for f in key_filings:
            url = f.get('linkToFilingDetails') or f.get('linkToHtml')
            if url:
                content = await self.sec_client.fetch_filing_content(url, filing_data=f)
                if content:
                    contents.append({
                        'form': f.get('formType'),
                        'date': f.get('filedAt', '')[:10],
                        'content': content
                    })
                else:
                    logger.debug("chain_filing_no_content",
                               file_no=file_no,
                               form=f.get('formType'),
                               url=url[:80])
        
        # Si no hay contenido de key filings, intentar con todos los filings de la cadena
        if not contents:
            logger.debug("chain_trying_all_filings", file_no=file_no)
            for f in chain_filings:
                url = f.get('linkToFilingDetails') or f.get('linkToHtml')
                if url:
                    content = await self.sec_client.fetch_filing_content(url, filing_data=f)
                    if content and len(content) > 5000:  # Solo si tiene contenido sustancial
                        contents.append({
                            'form': f.get('formType'),
                            'date': f.get('filedAt', '')[:10],
                            'content': content
                        })
                        break  # Tomar el primero que funcione
        
        if not contents:
            logger.debug("chain_no_content", file_no=file_no)
            return
        
        # Construir prompt con todos los contenidos
        combined_content = "\n\n".join([
            f"=== {c['form']} ({c['date']}) ===\n{c['content']}"
            for c in contents
        ])
        
        # Llamar a Gemini con retry para rate limiting
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.gemini.models.generate_content(
                    model=self.model,
                    contents=[combined_content, REGISTRATION_CHAIN_PROMPT],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                
                result = self._parse_json(response.text)
                
                # Agregar al contexto
                self._add_chain_to_context(result, file_no, context)
                
                logger.info("chain_processed",
                           file_no=file_no,
                           chain_type=chain_type,
                           offering=bool(result.get('offering')),
                           warrants=len(result.get('warrants', [])))
                
                # Delay entre llamadas exitosas para evitar rate limit
                time.sleep(2)
                break
                
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait_time = (attempt + 1) * 10  # 10s, 20s, 30s
                    logger.warning("gemini_rate_limit_retry", file_no=file_no, attempt=attempt+1, wait=wait_time)
                    time.sleep(wait_time)
                else:
                    logger.error("chain_extraction_error", file_no=file_no, error=str(e))
                    break
    
    def _select_key_filings(self, chain_filings: List[Dict]) -> List[Dict]:
        """Selecciona los filings más importantes de una cadena"""
        # OJO: 424B* se trata como TRANSACCIÓN (filingID/accessionNo), no como parte del REGISTRO.
        # Para el registro priorizamos: EFFECT/amendments y el form principal (S-1/F-1/S-3/F-3).
        key_forms_priority1 = ['EFFECT', 'S-3/A', 'F-3/A', 'S-1/A', 'F-1/A']
        key_forms_priority2 = ['S-3', 'F-3', 'S-1', 'F-1']
        
        key_filings = []
        
        # Buscar por prioridad
        for priority_forms in [key_forms_priority1, key_forms_priority2]:
            for f in chain_filings:
                form = (f.get('formType') or '').upper()
                if any(k in form for k in priority_forms) and f not in key_filings:
                    key_filings.append(f)
        
        if not key_filings:
            # Si no encontramos nada, tomar los más recientes
            key_filings = chain_filings[-2:] if len(chain_filings) > 1 else chain_filings
        
        # v4.1: Limitar a 3 filings por cadena (balance entre contexto y velocidad)
        # Con timeout de 120s configurado en el cliente, podemos procesar más
        return key_filings[:3]
    
    def _add_chain_to_context(self, result: Dict, file_no: str, context: ExtractionContext):
        """Agrega los resultados de una cadena al contexto"""
        # Offering
        offering = result.get('offering', {})
        if offering:
            offering['file_number'] = file_no
            offering['_source'] = f"chain:{file_no}"
            offering['_sources'] = list(dict.fromkeys((offering.get('_sources') or []) + [offering['_source']]))
            
            if offering.get('type') in ['S-1', 'F-1']:
                # Mantener compatibilidad con modelos: S1OfferingModel espera campos específicos,
                # pero aquí almacenamos el dict crudo; el builder tolera campos extra.
                self._upsert_instrument(context.s1_offerings, offering, inst_type='s1')
            elif offering.get('type') == 'Shelf':
                self._upsert_instrument(context.shelf_registrations, offering, inst_type='shelf')
            elif offering.get('type') == 'ATM':
                self._upsert_instrument(context.atm_offerings, offering, inst_type='atm')
        
        # Warrants de la cadena
        for w in result.get('warrants', []):
            if not isinstance(w, dict):
                logger.warning("skipping_invalid_warrant", value=str(w)[:50], file_no=file_no)
                continue
            w = self._normalize_instrument(w, 'warrant')
            w['_source'] = f"chain:{file_no}"
            w['_sources'] = list(dict.fromkeys((w.get('_sources') or []) + [w['_source']]))
            w['ticker'] = context.ticker
            self._upsert_instrument(context.warrants, w, inst_type='warrant')
        
        # Notes y Preferred (menos comunes en registration chains)
        for n in result.get('notes', []):
            if not isinstance(n, dict):
                continue
            n = self._normalize_instrument(n, 'note')
            n['_source'] = f"chain:{file_no}"
            n['_sources'] = list(dict.fromkeys((n.get('_sources') or []) + [n['_source']]))
            n['ticker'] = context.ticker
            self._upsert_instrument(context.convertible_notes, n, inst_type='note')
        
        for p in result.get('preferred', []):
            if not isinstance(p, dict):
                continue
            p = self._normalize_instrument(p, 'preferred')
            p['_source'] = f"chain:{file_no}"
            p['_sources'] = list(dict.fromkeys((p.get('_sources') or []) + [p['_source']]))
            p['ticker'] = context.ticker
            self._upsert_instrument(context.convertible_preferred, p, inst_type='preferred')
    
    async def _process_transactions_with_context(
        self,
        transaction_filings: List[Dict],
        context: ExtractionContext
    ):
        """
        Procesa transacciones/eventos (424B*/8-K/6-K) CON CONTEXTO, por accessionNo (filingID).
        Esto evita mezclar múltiples eventos en un batch y mejora:
        - trazabilidad (filing_url por instrumento)
        - idempotencia (no reprocesar accessionNo)
        - dedupe/merge incremental
        """
        if not transaction_filings:
            return

        cutoff = (datetime.now() - timedelta(days=1095)).isoformat()
        recent = [e for e in transaction_filings if (e.get('filedAt') or '') >= cutoff]
        recent.sort(key=lambda x: x.get('filedAt', ''))

        logger.info(
            "processing_transactions",
            ticker=context.ticker,
            total=len(transaction_filings),
            recent=len(recent),
        )

        for idx, filing in enumerate(recent):
            await self._process_single_transaction_filing(filing, context, idx=idx + 1, total=len(recent))

    def _get_filing_identity(self, filing: Dict) -> Dict[str, str]:
        """Extrae identidad estable del filing (accessionNo + url + form + date)."""
        form = (filing.get('formType') or '').upper()
        date = (filing.get('filedAt') or '')[:10]
        accession = filing.get('accessionNo') or filing.get('accessionNumber') or ''
        url = filing.get('linkToFilingDetails') or filing.get('linkToHtml') or ''
        # Some APIs provide 18-digit accession in URL path; keep best effort.
        return {"form": form, "date": date, "accession": accession, "url": url}

    async def _process_single_transaction_filing(
        self,
        filing: Dict,
        context: ExtractionContext,
        idx: int,
        total: int
    ):
        """Procesa un único filing de transacción con contexto y hace upsert/merge en el contexto."""
        ident = self._get_filing_identity(filing)
        accession = ident["accession"] or ident["url"]
        if not accession:
            return

        if accession in context.processed_accessions:
            return
        context.processed_accessions.add(accession)

        url = ident["url"]
        if not url:
            return

        content = await self.sec_client.fetch_filing_content(url, filing_data=filing)
        if not content:
            return

        # keyword gate para 8-K/6-K (424B suele ser relevante aunque no mencione "warrant")
        form = ident["form"]
        content_lower = content.lower()
        if form in ['8-K', '6-K', '8-K/A', '6-K/A']:
            gate_keywords = [
                'convertible', 'warrant', 'preferred', 'securities purchase',
                'private placement', 'exercise price', 'conversion price',
                'subscription agreement', 'note purchase', 'issuance',
                'at-the-market', 'atm', 'sales agreement', 'registered direct',
                'equity line', 'purchase agreement'
            ]
            if not any(k in content_lower for k in gate_keywords):
                return

        filings_content = f"=== {form} ({ident['date']}) ===\n{content[:MAX_CONTENT_PER_FILING]}"
        prompt = MATERIAL_EVENTS_WITH_CONTEXT_PROMPT.format(
            existing_context=context.to_context_string(),
            filings_content=filings_content
        )

        logger.info(
            "gemini_transaction_call",
            ticker=context.ticker,
            idx=idx,
            total=total,
            form=form,
            date=ident["date"],
            accession=ident["accession"][:32] if ident["accession"] else "",
            content_chars=min(len(content), MAX_CONTENT_PER_FILING),
        )

        # Retry para rate limiting
        import time
        result = None
        for attempt in range(3):
            try:
                response = self.gemini.models.generate_content(
                    model=self.model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                result = self._parse_json(response.text)
                time.sleep(1)  # Delay entre llamadas
                break
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait_time = (attempt + 1) * 10
                    logger.warning("gemini_rate_limit_retry", form=form, attempt=attempt+1, wait=wait_time)
                    time.sleep(wait_time)
                else:
                    logger.error("transaction_extraction_error", form=form, date=ident["date"], error=str(e))
                    return

        if result is None:
            return

        if not isinstance(result, dict):
            return

        new_instruments = result.get('new_instruments', {}) or {}
        if not isinstance(new_instruments, dict):
            new_instruments = {}

        source_tag = f"{form}:{ident['date']}:{ident['accession'] or ''}".strip(':')
        filing_url = url

        # Upsert warrants
        for w in new_instruments.get('warrants', []) or []:
            if not isinstance(w, dict):
                continue
            w = self._normalize_instrument(w, 'warrant')
            w['ticker'] = context.ticker
            w['filing_url'] = w.get('filing_url') or filing_url
            w['_source'] = source_tag
            self._upsert_instrument(context.warrants, w, inst_type='warrant')

        # Upsert notes
        for n in new_instruments.get('convertible_notes', []) or []:
            if not isinstance(n, dict):
                continue
            n = self._normalize_instrument(n, 'note')
            n['ticker'] = context.ticker
            n['filing_url'] = n.get('filing_url') or filing_url
            n['_source'] = source_tag
            self._upsert_instrument(context.convertible_notes, n, inst_type='note')

        # Upsert preferred
        for p in new_instruments.get('convertible_preferred', []) or []:
            if not isinstance(p, dict):
                continue
            p = self._normalize_instrument(p, 'preferred')
            p['ticker'] = context.ticker
            p['filing_url'] = p.get('filing_url') or filing_url
            p['_source'] = source_tag
            self._upsert_instrument(context.convertible_preferred, p, inst_type='preferred')

        # Upsert ATM
        for atm in new_instruments.get('atm_offerings', []) or []:
            if not isinstance(atm, dict):
                continue
            atm = self._normalize_instrument(atm, 'atm')
            atm['ticker'] = context.ticker
            atm['filing_url'] = atm.get('filing_url') or filing_url
            atm['_source'] = source_tag
            self._upsert_instrument(context.atm_offerings, atm, inst_type='atm')

        # Upsert Completed Offerings (de 424B filings)
        for co in new_instruments.get('completed_offerings', []) or []:
            if not isinstance(co, dict):
                continue
            co['ticker'] = context.ticker
            co['filing_url'] = co.get('filing_url') or filing_url
            co['_source'] = source_tag
            # No deduplicamos completed offerings - cada deal es único
            context.completed_offerings.append(co)

    def _instrument_key(self, instrument: Dict, inst_type: str) -> str:
        """
        Clave de dedupe/upsert: usa campos estables (mes+tipo+precio).
        NO incluye nombre literal para evitar duplicados por variaciones de texto.
        
        FIX v4.3: Removido name[:32] del key - causaba duplicados cuando
        el mismo warrant se extraía con nombres ligeramente diferentes.
        """
        issue_date = instrument.get('issue_date') or instrument.get('agreement_start_date') or instrument.get('filing_date') or ''
        # Normalizar a YYYY-MM (ignora día exacto para agrupar mismo mes)
        issue_month = issue_date[:7] if len(str(issue_date)) >= 7 else str(issue_date)
        
        # Helper para normalizar precio a 2 decimales
        def normalize_price(p):
            if p is None or p == '':
                return ''
            try:
                return f"{float(str(p).replace('$','').replace(',','')):.2f}"
            except (ValueError, TypeError):
                return str(p)
        
        # Helper para extraer warrant_type de series_name si warrant_type está vacío
        def get_warrant_type(inst):
            wt = (inst.get('warrant_type') or '').strip().lower()
            if wt:
                return wt
            # Fallback: extraer de series_name
            name = (inst.get('series_name') or '').lower()
            if 'pre-funded' in name or 'prefunded' in name:
                return 'pre-funded'
            if 'private' in name or 'pipe' in name:
                return 'private'
            if 'public' in name:
                return 'public'
            if 'placement agent' in name:
                return 'placement agent'
            if 'common' in name:
                return 'common'
            return 'unknown'
        
        if inst_type == 'warrant':
            wt = get_warrant_type(instrument)
            price = normalize_price(instrument.get('exercise_price'))
            # Key: mes + tipo + precio (SIN nombre)
            return f"warrant|{issue_month}|{wt}|{price}"
        if inst_type == 'note':
            price = normalize_price(instrument.get('conversion_price'))
            return f"note|{issue_month}|{price}"
        if inst_type == 'preferred':
            price = normalize_price(instrument.get('conversion_price'))
            series = (instrument.get('series') or '').strip().lower()
            return f"preferred|{issue_month}|{series}|{price}"
        if inst_type == 'atm':
            agent = (instrument.get('placement_agent') or '').strip().lower()
            cap = instrument.get('total_capacity') or ''
            return f"atm|{issue_month}|{agent}|{cap}"
        if inst_type == 'shelf':
            cap = instrument.get('total_capacity') or ''
            file_no = instrument.get('file_number') or instrument.get('fileNo') or ''
            return f"shelf|{issue_month}|{file_no}|{cap}"
        if inst_type == 's1':
            file_no = instrument.get('file_number') or ''
            return f"s1|{issue_month}|{file_no}"
        return f"{inst_type}|{issue_month}"

    def _merge_instruments(self, base: Dict, incoming: Dict) -> Dict:
        """Merge conservando el mejor dato y acumulando sources."""
        merged = dict(base)
        # Preferir valores no vacíos del incoming
        for k, v in incoming.items():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            if merged.get(k) in [None, '', [], {}]:
                merged[k] = v
            else:
                # Para _sources, unir
                if k == '_sources' and isinstance(v, list):
                    prev = merged.get('_sources') or []
                    merged['_sources'] = list(dict.fromkeys(prev + v))
        # Normalizar trazabilidad
        src = incoming.get('_source')
        if src:
            sources = merged.get('_sources') or []
            if src not in sources:
                merged['_sources'] = sources + [src]
        if '_sources' in merged and merged['_sources'] and '_source' not in merged:
            merged['_source'] = merged['_sources'][-1]
        return merged

    def _upsert_instrument(self, bucket: List[Dict], instrument: Dict, inst_type: str):
        """Inserta o mergea un instrumento en el bucket según clave estable."""
        key = self._instrument_key(instrument, inst_type)
        for i, existing in enumerate(bucket):
            if not isinstance(existing, dict):
                continue
            if self._instrument_key(existing, inst_type) == key:
                bucket[i] = self._merge_instruments(existing, instrument)
                # Conteo de merges
                bucket[i]['_merged_from'] = int(bucket[i].get('_merged_from') or 1) + 1
                return
        # Nuevo
        instrument['_sources'] = list(dict.fromkeys((instrument.get('_sources') or []) + ([instrument.get('_source')] if instrument.get('_source') else [])))
        instrument['_merged_from'] = instrument.get('_merged_from') or 1
        bucket.append(instrument)
    
    async def _batch_events_by_tokens(self, events: List[Dict]) -> List[List[Dict]]:
        """Agrupa eventos en batches que no excedan MAX_TOKENS_PER_BATCH"""
        batches = []
        current_batch = []
        current_tokens = 0
        
        for event in events:
            # Estimar tokens (descargamos después, estimamos por promedio)
            estimated_tokens = 10000  # ~40K chars promedio por filing
            
            if current_tokens + estimated_tokens > MAX_TOKENS_PER_BATCH and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            
            current_batch.append(event)
            current_tokens += estimated_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    async def _process_event_batch(
        self,
        events: List[Dict],
        context: ExtractionContext,
        batch_num: int
    ):
        """Procesa un batch de material events con contexto"""
        logger.info("processing_event_batch",
                   batch=batch_num,
                   events=len(events),
                   ticker=context.ticker)
        
        # Descargar contenido de eventos con keywords dilutivos
        contents = []
        dilution_keywords = [
            'convertible', 'warrant', 'preferred', 'securities purchase',
            'private placement', 'exercise price', 'conversion price',
            # Keywords adicionales comunes
            'stock purchase', 'subscription agreement', 'note purchase',
            'series a', 'series b', 'series c', 'placement agent',
            'offering', 'shares issued', 'issuance', 'debenture',
            'equity line', 'at-the-market', 'atm', 'registered direct',
            # ATM específicos
            'sales agreement', 'atm agreement', 'at the market', 'shelf takedown'
        ]
        
        downloaded_count = 0
        matched_count = 0
        
        for event in events[:100]:  # Limitar a 100 eventos por batch
            url = event.get('linkToFilingDetails') or event.get('linkToHtml')
            if not url:
                continue
            
            # Pasar el evento completo para acceder a documentFormatFiles
            content = await self.sec_client.fetch_filing_content(url, filing_data=event)
            if not content:
                continue
            
            downloaded_count += 1
            
            # Verificar si tiene keywords dilutivos
            content_lower = content.lower()
            if not any(kw in content_lower for kw in dilution_keywords):
                logger.debug("event_no_keywords", 
                           form=event.get('formType'),
                           date=event.get('filedAt', '')[:10],
                           content_len=len(content))
                continue
            
            matched_count += 1
            logger.debug("event_has_dilution_content",
                        form=event.get('formType'),
                        date=event.get('filedAt', '')[:10],
                        keywords_sample=[kw for kw in dilution_keywords[:5] if kw in content_lower])
            
            contents.append({
                'form': event.get('formType'),
                'date': event.get('filedAt', '')[:10],
                'content': content[:MAX_CONTENT_PER_FILING]  # Limitar contenido
            })
            
            # Limitar número de filings por batch
            if len(contents) >= MAX_FILINGS_PER_BATCH:
                logger.info("event_batch_limit_reached", matched=matched_count, limit=MAX_FILINGS_PER_BATCH)
                break
        
        logger.info("event_batch_content_stats",
                   batch=batch_num,
                   downloaded=downloaded_count,
                   matched=matched_count)
        
        if not contents:
            logger.debug("event_batch_no_dilution_content", batch=batch_num)
            return
        
        # Construir contenido combinado
        filings_content = "\n\n".join([
            f"=== {c['form']} ({c['date']}) ===\n{c['content']}"
            for c in contents
        ])
        
        # Construir prompt con contexto
        prompt = MATERIAL_EVENTS_WITH_CONTEXT_PROMPT.format(
            existing_context=context.to_context_string(),
            filings_content=filings_content
        )
        
        # Llamar a Gemini con contexto
        try:
            total_chars = sum(len(c['content']) for c in contents)
            logger.info("gemini_calling_with_context",
                       batch=batch_num,
                       filings=len(contents),
                       total_chars=total_chars,
                       context_instruments=len(context.warrants) + len(context.convertible_notes))
            
            response = self.gemini.models.generate_content(
                model=self.model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            logger.debug("gemini_response_received",
                        batch=batch_num,
                        response_len=len(response.text) if response.text else 0)
            
            result = self._parse_json(response.text)
            
            # Validar que result es un diccionario
            if not isinstance(result, dict):
                logger.error("gemini_invalid_response_type",
                            batch=batch_num,
                            result_type=type(result).__name__,
                            result_preview=str(result)[:200])
                return
            
            # Procesar nuevos instrumentos
            new_instruments = result.get('new_instruments', {})
            if not isinstance(new_instruments, dict):
                new_instruments = {}
            
            for w in new_instruments.get('warrants', []):
                if not isinstance(w, dict):
                    continue
                w = self._normalize_instrument(w, 'warrant')
                w['_source'] = f"events_batch:{batch_num}"
                w['ticker'] = context.ticker
                context.warrants.append(w)
            
            for n in new_instruments.get('convertible_notes', []):
                if not isinstance(n, dict):
                    continue
                n = self._normalize_instrument(n, 'note')
                n['_source'] = f"events_batch:{batch_num}"
                n['ticker'] = context.ticker
                context.convertible_notes.append(n)
            
            for p in new_instruments.get('convertible_preferred', []):
                if not isinstance(p, dict):
                    continue
                p = self._normalize_instrument(p, 'preferred')
                p['_source'] = f"events_batch:{batch_num}"
                p['ticker'] = context.ticker
                context.convertible_preferred.append(p)
            
            # ATM offerings de material events
            for atm in new_instruments.get('atm_offerings', []):
                if not isinstance(atm, dict):
                    continue
                atm = self._normalize_instrument(atm, 'atm')
                atm['_source'] = f"events_batch:{batch_num}"
                atm['ticker'] = context.ticker
                context.atm_offerings.append(atm)
            
            # Completed Offerings de material events (8-K closings, 424B)
            for co in new_instruments.get('completed_offerings', []):
                if not isinstance(co, dict):
                    continue
                co['_source'] = f"events_batch:{batch_num}"
                co['ticker'] = context.ticker
                context.completed_offerings.append(co)
            
            # Log correlaciones identificadas
            correlations = result.get('correlations', [])
            if correlations:
                logger.info("correlations_identified",
                           batch=batch_num,
                           correlations=correlations)
            
            logger.info("event_batch_processed",
                       batch=batch_num,
                       new_warrants=len(new_instruments.get('warrants', [])),
                       new_notes=len(new_instruments.get('convertible_notes', [])),
                       new_preferred=len(new_instruments.get('convertible_preferred', [])),
                       new_completed=len(new_instruments.get('completed_offerings', [])),
                       updates=len(result.get('updates', [])))
            
        except Exception as e:
            logger.error("event_batch_error", batch=batch_num, error=str(e))
    
    def _normalize_instrument(self, instrument: Dict, inst_type: str) -> Dict:
        """
        Normaliza un instrumento extraído:
        - Unifica el campo series_name desde varios posibles campos
        - Genera nombre si no existe usando el patrón [Mes Año] [Calificador] [Tipo]
        - Limpia formatos de precio
        """
        # Unificar campo de nombre
        name = (
            instrument.get('series_name') or 
            instrument.get('name') or 
            instrument.get('instrument_id') or
            instrument.get('id') or
            instrument.get('series') or
            ''
        )
        
        # Normalizaciones específicas por tipo para compatibilidad con modelos
        if inst_type == 'atm':
            # Gemini puede devolver agreement_date; el modelo espera agreement_start_date
            if instrument.get('agreement_date') and not instrument.get('agreement_start_date'):
                instrument['agreement_start_date'] = instrument.get('agreement_date')
            # Some prompts might use placement_agent/underwriter, keep placement_agent for model
            if instrument.get('underwriter') and not instrument.get('placement_agent'):
                instrument['placement_agent'] = instrument.get('underwriter')

        # Si no hay nombre, generar uno basado en fecha y tipo
        if not name or name == '?':
            # Para algunos tipos, el "issue_date" real vive en otro campo
            issue_date = instrument.get('issue_date', '') or instrument.get('agreement_start_date', '') or instrument.get('agreement_date', '') or instrument.get('filing_date', '')
            
            # Extraer mes y año de la fecha
            if issue_date:
                try:
                    from datetime import datetime
                    if isinstance(issue_date, str):
                        # Intentar parsear diferentes formatos
                        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y', '%Y']:
                            try:
                                dt = datetime.strptime(issue_date[:10], fmt)
                                month_year = dt.strftime('%B %Y')
                                break
                            except:
                                continue
                        else:
                            month_year = issue_date[:7]  # fallback YYYY-MM
                    else:
                        month_year = str(issue_date)
                except:
                    month_year = 'Unknown Date'
            else:
                month_year = 'Unknown Date'
            
            # Determinar calificador
            warrant_type = instrument.get('warrant_type', instrument.get('type', ''))
            
            # Generar nombre según tipo de instrumento
            if inst_type == 'warrant':
                if warrant_type:
                    name = f"{month_year} {warrant_type} Warrants"
                else:
                    name = f"{month_year} Warrants"
            elif inst_type == 'note':
                name = f"{month_year} Convertible Notes"
            elif inst_type == 'preferred':
                series = instrument.get('series', '')
                if series:
                    name = f"{month_year} {series} Convertible Preferred"
                else:
                    name = f"{month_year} Convertible Preferred"
            elif inst_type == 'atm':
                agent = instrument.get('placement_agent', '')
                if agent:
                    name = f"{month_year} {agent} ATM"
                else:
                    name = f"{month_year} ATM"
        
        instrument['series_name'] = name
        
        # Limpiar precio (remover dobles $, prefijos de moneda)
        for price_field in ['exercise_price', 'conversion_price']:
            if price_field in instrument:
                price = str(instrument[price_field])
                # Remover símbolos de moneda y limpiar
                price = price.replace('$$', '$').replace('C$', '').replace('US$', '')
                price = price.replace('CAD$', '').replace('USD$', '')
                # Si es número puro, extraerlo
                import re
                match = re.search(r'[\d,.]+', price)
                if match:
                    try:
                        clean_price = float(match.group().replace(',', ''))
                        instrument[price_field] = clean_price
                    except:
                        instrument[price_field] = price
        
        return instrument
    
    def _parse_json(self, text: str) -> Dict:
        """Parsea JSON de respuesta de Gemini"""
        if not text:
            logger.warning("gemini_empty_response")
            return {}
        
        try:
            # Limpiar markdown si existe
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            result = json.loads(text.strip())
            
            # Si Gemini devuelve una lista, convertir a dict
            if isinstance(result, list):
                logger.warning("gemini_returned_list_converting", items=len(result))
                # Intentar extraer instrumentos de la lista
                return {
                    'warrants': [r for r in result if isinstance(r, dict) and 'exercise_price' in r],
                    'notes': [r for r in result if isinstance(r, dict) and 'conversion_price' in r and 'principal' in str(r).lower()],
                    'preferred': [r for r in result if isinstance(r, dict) and 'conversion_price' in r and 'preferred' in str(r).lower()]
                }
            
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError as e:
            logger.warning("json_parse_error", 
                          error=str(e), 
                          text_len=len(text),
                          text_preview=text[:500] if text else "empty")
            return {}
            return {}


# =============================================================================
# SINGLETON
# =============================================================================

_extractor_instance: Optional[ContextualDilutionExtractor] = None

def get_contextual_extractor() -> Optional[ContextualDilutionExtractor]:
    """Obtiene instancia singleton del extractor contextual"""
    global _extractor_instance
    
    if _extractor_instance is None:
        sec_key = settings.SEC_API_IO_KEY if hasattr(settings, 'SEC_API_IO_KEY') else None
        gemini_key = settings.GOOGL_API_KEY_V2 if hasattr(settings, 'GOOGL_API_KEY_V2') else None
        
        if sec_key and gemini_key:
            _extractor_instance = ContextualDilutionExtractor(sec_key, gemini_key)
        else:
            logger.warning("contextual_extractor_disabled",
                          has_sec_key=bool(sec_key),
                          has_gemini_key=bool(gemini_key))
    
    return _extractor_instance

