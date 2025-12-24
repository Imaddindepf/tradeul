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

MAX_TOKENS_PER_BATCH = 200_000  # ~200K tokens por llamada (más conservador)
CHARS_PER_TOKEN = 4  # Aproximación: 4 caracteres = 1 token
MAX_CONTENT_PER_FILING = 30_000  # 30K chars max por filing
MAX_FILINGS_PER_BATCH = 15  # Max 15 filings por batch de Gemini


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
        "placement_agent": "ThinkEquity",
        "agreement_date": "2024-10-17",
        "status": "Active|Exhausted|Terminated"
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
        return {
            'warrants': self.warrants,
            'convertible_notes': self.convertible_notes,
            'convertible_preferred': self.convertible_preferred,
            's1_offerings': self.s1_offerings,
            'shelf_registrations': self.shelf_registrations,
            'atm_offerings': self.atm_offerings,
        }


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
    
    async def fetch_filing_content(self, url: str, filing_data: Optional[Dict] = None) -> Optional[str]:
        """
        Descarga el contenido de un filing.
        Prioriza el archivo .txt completo que contiene todo el texto.
        """
        import re
        from bs4 import BeautifulSoup
        
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
                        return None
                    
                    # Limpiar HTML
                    try:
                        soup = BeautifulSoup(content, 'html.parser')
                        for tag in soup(['script', 'style', 'head', 'meta', 'link']):
                            tag.decompose()
                        text = soup.get_text(separator=' ', strip=True)
                        text = re.sub(r'\s+', ' ', text)
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
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=self.sec_headers)
                if response.status_code == 200:
                    content = response.text
                    # Verificar que no es error de SEC
                    if 'Request Originates from an Undeclared' in content:
                        logger.warning("sec_rate_limited", url=url[:60])
                        return None
                    return content[:200000]
        except Exception as e:
            logger.debug("sec_direct_fetch_error", url=url[:50], error=str(e))
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
        self.gemini = genai.Client(api_key=gemini_api_key)
        self.model = "gemini-2.5-flash"
        
        logger.info("contextual_extractor_initialized", model=self.model)
    
    async def extract_all(self, ticker: str, cik: str) -> Dict:
        """
        Extracción completa con contexto acumulado.
        
        Returns:
            Dict con todos los instrumentos extraídos, deduplicados por contexto
        """
        logger.info("contextual_extraction_start", ticker=ticker, cik=cik)
        
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
        
        # PASO 5: Filtrar warrants (remover underwriter/placement agent)
        context.warrants = self._filter_warrants(context.warrants)
        
        logger.info("contextual_extraction_complete",
                   ticker=ticker,
                   warrants=len(context.warrants),
                   notes=len(context.convertible_notes),
                   preferred=len(context.convertible_preferred),
                   s1=len(context.s1_offerings),
                   shelf=len(context.shelf_registrations),
                   atm=len(context.atm_offerings))
        
        return context.to_dict()
    
    def _filter_warrants(self, warrants: List[Dict]) -> List[Dict]:
        """
        Filtra warrants según las reglas de DilutionTracker:
        - MANTENER: Common Warrants, Pre-Funded Warrants
        - REMOVER: Underwriter Warrants, Placement Agent Warrants
        
        Razón: Underwriter/Placement Agent warrants son cantidades pequeñas
        que raramente se ejercen.
        """
        filtered = []
        removed_count = 0
        
        for w in warrants:
            if not isinstance(w, dict):
                continue
            name = (w.get('series_name') or '').lower()
            warrant_type = (w.get('warrant_type') or '').lower()
            
            # Patrones a filtrar
            is_underwriter = 'underwriter' in name or warrant_type == 'underwriter'
            is_placement_agent = 'placement agent' in name or warrant_type == 'placement agent'
            
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
        
        # Llamar a Gemini
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
            
        except Exception as e:
            logger.error("chain_extraction_error", file_no=file_no, error=str(e))
    
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
        
        return key_filings[:4]  # Máximo 4 filings por cadena
    
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
        except Exception as e:
            logger.error("transaction_extraction_error", form=form, date=ident["date"], error=str(e))
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

    def _instrument_key(self, instrument: Dict, inst_type: str) -> str:
        """
        Clave de dedupe/upsert: prioriza issue_date + tipo + (precio si aplica) + series_name.
        Mantiene estabilidad incluso si cambia ligeramente el nombre.
        """
        issue_date = instrument.get('issue_date') or instrument.get('agreement_start_date') or instrument.get('filing_date') or ''
        name = (instrument.get('series_name') or '').strip().lower()
        if inst_type == 'warrant':
            wt = (instrument.get('warrant_type') or '').strip().lower()
            price = instrument.get('exercise_price') or ''
            return f"warrant|{issue_date}|{wt}|{price}|{name[:32]}"
        if inst_type == 'note':
            price = instrument.get('conversion_price') or ''
            return f"note|{issue_date}|{price}|{name[:32]}"
        if inst_type == 'preferred':
            price = instrument.get('conversion_price') or ''
            series = (instrument.get('series') or '').strip().lower()
            return f"preferred|{issue_date}|{series}|{price}|{name[:32]}"
        if inst_type == 'atm':
            agent = (instrument.get('placement_agent') or '').strip().lower()
            cap = instrument.get('total_capacity') or ''
            return f"atm|{issue_date}|{agent}|{cap}|{name[:32]}"
        if inst_type == 'shelf':
            cap = instrument.get('total_capacity') or ''
            file_no = instrument.get('file_number') or instrument.get('fileNo') or ''
            return f"shelf|{issue_date}|{file_no}|{cap}|{name[:32]}"
        if inst_type == 's1':
            file_no = instrument.get('file_number') or ''
            return f"s1|{issue_date}|{file_no}|{name[:32]}"
        return f"{inst_type}|{issue_date}|{name[:64]}"

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

