"""
SEC Full-Text Search Service - COMPREHENSIVE DILUTION DISCOVERY
================================================================
Usa SEC-API.io Full-Text Search para encontrar TODOS los filings con contenido dilutivo.

INCLUYE TODAS LAS KEYWORDS POSIBLES:
- Warrants (regular, pre-funded, penny)
- ATM/At-The-Market offerings
- Shelf Registrations (S-3, F-3, universal)
- Convertible Securities (notes, debentures, preferred)
- Private Placements (PIPE, SPA)
- Equity Lines (ELOC)
- Direct/Public Offerings
- Stock Options, RSUs, Equity Compensation
- Anti-dilution provisions
- Y MUCHO MÁS...
"""

import httpx
import asyncio
from typing import List, Dict, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from shared.config.settings import settings
from shared.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# RATE LIMITER PARA SEC-API.IO
# =============================================================================

class RateLimiter:
    """
    Rate limiter con ventana deslizante para SEC-API.io.
    
    Limits (Personal & Startups):
    - Full-Text Search: 10 req/seg
    - Query API: 20 req/seg
    """
    
    def __init__(self, requests_per_second: float = 8.0):  # Conservador: 8 de 10
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Espera hasta que sea seguro hacer otra request."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self._last_request_time
            
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                await asyncio.sleep(wait_time)
            
            self._last_request_time = asyncio.get_event_loop().time()


# Rate limiters globales para diferentes APIs
_fulltext_rate_limiter = RateLimiter(requests_per_second=8.0)  # 8 de 10 permitidos
_query_rate_limiter = RateLimiter(requests_per_second=15.0)     # 15 de 20 permitidos


# =============================================================================
# KEYWORDS EXHAUSTIVOS PARA CADA TIPO DE INSTRUMENTO DILUTIVO
# =============================================================================

DILUTION_KEYWORDS = {
    # =========================================================================
    # WARRANTS - Todos los tipos
    # =========================================================================
    "WARRANTS": [
        'warrant',
        '"warrant agreement"',
        '"warrants to purchase"',
        '"exercise price"',
        '"warrant holder"',
        '"warrant shares"',
        '"outstanding warrants"',
        '"warrant exercise"',
        '"warrant expiration"',
        '"warrant terms"',
    ],
    
    "PRE_FUNDED_WARRANTS": [
        '"pre-funded warrant"',
        '"prefunded warrant"',
        '"pre funded warrant"',
        '"nominal exercise price"',
        '"$0.0001 exercise"',
        '"$0.001 exercise"',
    ],
    
    "PENNY_WARRANTS": [
        '"penny warrant"',
        '"penny exercise"',
        '"$0.01 exercise"',
        '"one cent exercise"',
    ],
    
    "PLACEMENT_AGENT_WARRANTS": [
        '"placement agent warrant"',
        '"underwriter warrant"',
        '"broker warrant"',
        '"compensation warrant"',
    ],
    
    # =========================================================================
    # ATM / AT-THE-MARKET
    # =========================================================================
    "ATM": [
        '"at-the-market"',
        '"at the market"',
        '"ATM offering"',
        '"ATM program"',
        '"ATM facility"',
        '"ATM agreement"',
        '"equity distribution"',
        '"equity distribution agreement"',
        '"sales agreement"',
        '"open market sale"',
        '"continuous offering"',
    ],
    
    # =========================================================================
    # SHELF REGISTRATION
    # =========================================================================
    "SHELF": [
        '"shelf registration"',
        '"shelf offering"',
        '"universal shelf"',
        '"automatic shelf"',
        '"well-known seasoned issuer"',
        '"WKSI"',
        '"prospectus supplement"',
        '"base prospectus"',
        '"takedown"',
        '"shelf takedown"',
        '"Form S-3"',
        '"Form F-3"',
        '"registration statement"',
        '"effective registration"',
    ],
    
    "BABY_SHELF": [
        '"baby shelf"',
        '"General Instruction I.B.6"',
        '"Instruction I.B.6"',
        '"one-third of public float"',
        '"IB6"',
        '"float limitation"',
    ],
    
    # =========================================================================
    # CONVERTIBLE SECURITIES
    # =========================================================================
    "CONVERTIBLE_NOTES": [
        '"convertible note"',
        '"convertible notes"',
        '"convertible senior notes"',
        '"convertible subordinated notes"',
        '"senior convertible notes"',
        '"convertible debenture"',
        '"convertible debt"',
        '"convertible bond"',
        '"convertible promissory"',
        '"conversion price"',
        '"conversion rate"',
        '"convertible into common"',
        '"convertible into shares"',
        '"convert into"',
        '"upon conversion"',
        '"mandatory conversion"',
        '"optional conversion"',
        '"forced conversion"',
        '"notes due"',
    ],
    
    "CONVERTIBLE_PREFERRED": [
        '"convertible preferred"',
        '"series A preferred"',
        '"series B preferred"',
        '"series C preferred"',
        '"series D preferred"',
        '"series E preferred"',
        '"preferred stock"',
        '"participating preferred"',
        '"non-participating preferred"',
        '"liquidation preference"',
        '"dividend preference"',
        '"preferred conversion"',
    ],
    
    # =========================================================================
    # PRIVATE PLACEMENTS
    # =========================================================================
    "PRIVATE_PLACEMENT": [
        '"private placement"',
        '"private offering"',
        '"PIPE"',
        '"PIPE transaction"',
        '"PIPE financing"',
        '"Regulation D"',
        '"Rule 506"',
        '"Rule 144A"',
        '"accredited investor"',
        '"qualified institutional buyer"',
        '"QIB"',
        '"securities purchase agreement"',
        '"subscription agreement"',
        '"SPA"',
        '"stock purchase agreement"',
    ],
    
    # =========================================================================
    # EQUITY LINES / ELOC
    # =========================================================================
    "EQUITY_LINE": [
        '"equity line"',
        '"ELOC"',
        '"equity line of credit"',
        '"committed equity"',
        '"committed equity facility"',
        '"common stock purchase agreement"',
        '"CSPA"',
        '"standby equity"',
        '"SEPA"',
        '"standby equity distribution"',
        '"SEDA"',
        '"equity purchase agreement"',
    ],
    
    # =========================================================================
    # PUBLIC/DIRECT OFFERINGS
    # =========================================================================
    "PUBLIC_OFFERING": [
        '"public offering"',
        '"initial public offering"',
        '"IPO"',
        '"follow-on offering"',
        '"follow on offering"',
        '"secondary offering"',
        '"underwritten offering"',
        '"underwriting agreement"',
        '"firm commitment"',
        '"best efforts"',
        '"gross proceeds"',
        '"net proceeds"',
        '"offering price"',
        '"shares offered"',
    ],
    
    "REGISTERED_DIRECT": [
        '"registered direct"',
        '"registered direct offering"',
        '"RD offering"',
        '"direct placement"',
        '"directly to investors"',
    ],
    
    # =========================================================================
    # STOCK OPTIONS / EQUITY COMPENSATION
    # =========================================================================
    "STOCK_OPTIONS": [
        '"stock option"',
        '"option grant"',
        '"option exercise"',
        '"exercise of options"',
        '"stock option plan"',
        '"equity incentive plan"',
        '"2020 incentive plan"',
        '"2021 incentive plan"',
        '"2022 incentive plan"',
        '"2023 incentive plan"',
        '"2024 incentive plan"',
        '"inducement grant"',
        '"inducement award"',
    ],
    
    "RSU_EQUITY_COMP": [
        '"restricted stock"',
        '"RSU"',
        '"restricted stock unit"',
        '"performance share"',
        '"PSU"',
        '"performance stock unit"',
        '"stock award"',
        '"equity award"',
        '"equity compensation"',
        '"stock-based compensation"',
        '"share-based"',
        '"vesting"',
        '"cliff vesting"',
    ],
    
    "ESPP": [
        '"employee stock purchase"',
        '"ESPP"',
        '"employee stock purchase plan"',
        '"stock purchase plan"',
    ],
    
    # =========================================================================
    # ANTI-DILUTION / PROTECTIONS
    # =========================================================================
    "ANTI_DILUTION": [
        '"anti-dilution"',
        '"antidilution"',
        '"anti dilution"',
        '"weighted average"',
        '"full ratchet"',
        '"broad-based weighted"',
        '"narrow-based weighted"',
        '"price protection"',
        '"reset provision"',
        '"price reset"',
        '"floor price"',
        '"adjustment provision"',
    ],
    
    # =========================================================================
    # STOCK SPLITS / REVERSE SPLITS
    # =========================================================================
    "STOCK_SPLITS": [
        '"stock split"',
        '"reverse stock split"',
        '"reverse split"',
        '"share consolidation"',
        '"stock dividend"',
        '"stock combination"',
        '"proportionate adjustment"',
    ],
    
    # =========================================================================
    # AUTHORIZED SHARES
    # =========================================================================
    "AUTHORIZED_SHARES": [
        '"authorized shares"',
        '"authorized capital"',
        '"increase in authorized"',
        '"amendment to certificate"',
        '"certificate of incorporation"',
        '"articles of incorporation"',
        '"charter amendment"',
    ],
    
    # =========================================================================
    # DILUTION GENERAL
    # =========================================================================
    "DILUTION_GENERAL": [
        'dilution',
        'dilutive',
        '"dilutive effect"',
        '"issuance of shares"',
        '"shares issued"',
        '"shares outstanding"',
        '"fully diluted"',
        '"as-converted"',
        '"as converted"',
        '"on an as-converted"',
    ],
    
    # =========================================================================
    # SPECIFIC FILING TRIGGERS
    # =========================================================================
    "FINANCING_TRIGGERS": [
        '"financing agreement"',
        '"credit facility"',
        '"loan agreement"',
        '"security agreement"',
        '"pledge agreement"',
        '"bridge loan"',
        '"bridge financing"',
        '"venture debt"',
        '"senior secured"',
        '"subordinated"',
    ],
}


# Construir query combinada para búsqueda inicial rápida
def build_combined_query() -> str:
    """Construye una query combinada con los términos más importantes."""
    critical_terms = [
        'warrant',
        '"at-the-market"',
        '"ATM offering"',
        '"shelf registration"',
        '"convertible note"',
        '"convertible preferred"',
        '"private placement"',
        '"PIPE"',
        '"equity line"',
        '"registered direct"',
        '"public offering"',
        'dilution',
    ]
    return ' OR '.join(critical_terms)


class SECFullTextSearch:
    """
    Servicio para búsqueda full-text en SEC EDGAR usando SEC-API.io
    Encuentra TODOS los instrumentos dilutivos posibles.
    """
    
    FULLTEXT_ENDPOINT = "https://api.sec-api.io/full-text-search"
    S1_424B4_ENDPOINT = "https://api.sec-api.io/form-s1-424b4"
    FORM_D_ENDPOINT = "https://api.sec-api.io/form-d"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.SEC_API_IO_KEY
        if not self.api_key:
            logger.warning("sec_api_io_key_not_configured")
    
    # =========================================================================
    # FULL-TEXT SEARCH - BÚSQUEDA EXHAUSTIVA
    # =========================================================================
    
    async def discover_all_dilution_filings(
        self,
        cik: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_pages: int = 10
    ) -> Dict[str, Any]:
        """
        Descubre TODOS los filings con contenido dilutivo para un CIK.
        
        Returns:
            {
                "total_unique_filings": int,
                "filings_by_category": {category: [filings]},
                "all_filings": [filing_metadata],
                "categories_found": [list of categories with hits]
            }
        """
        if not self.api_key:
            logger.error("sec_api_io_key_missing")
            return {"error": "API key not configured"}
        
        # Defaults
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*7)).strftime("%Y-%m-%d")  # 7 años
        
        cik_normalized = cik.lstrip('0')
        
        all_filings: Dict[str, Dict] = {}  # accessionNo -> filing
        filings_by_category: Dict[str, List[Dict]] = defaultdict(list)
        categories_found: Set[str] = set()
        
        logger.info("fulltext_discovery_start", 
                   cik=cik_normalized, 
                   start_date=start_date, 
                   end_date=end_date,
                   total_categories=len(DILUTION_KEYWORDS))
        
        async with httpx.AsyncClient(timeout=90.0) as client:
            # Buscar por cada categoría de keywords
            for category, keywords in DILUTION_KEYWORDS.items():
                # Construir query con OR entre keywords
                query = ' OR '.join(keywords)
                
                category_filings = await self._search_with_query(
                    client=client,
                    query=query,
                    cik=cik_normalized,
                    start_date=start_date,
                    end_date=end_date,
                    max_pages=max_pages
                )
                
                if category_filings:
                    categories_found.add(category)
                    for f in category_filings:
                        acc_no = f.get("accessionNo")
                        if acc_no:
                            # Guardar filing
                            if acc_no not in all_filings:
                                all_filings[acc_no] = f
                                all_filings[acc_no]["categories"] = set()
                            
                            # Marcar categoría
                            all_filings[acc_no]["categories"].add(category)
                            filings_by_category[category].append(f)
                
                logger.debug("category_search_completed", 
                           category=category, 
                           filings_count=len(category_filings))
        
        # Convertir sets a listas para serialización
        for acc_no in all_filings:
            all_filings[acc_no]["categories"] = list(all_filings[acc_no]["categories"])
        
        result = {
            "cik": cik_normalized,
            "start_date": start_date,
            "end_date": end_date,
            "total_unique_filings": len(all_filings),
            "categories_found": sorted(list(categories_found)),
            "filings_by_category": {k: len(v) for k, v in filings_by_category.items()},
            "all_filings": sorted(
                list(all_filings.values()), 
                key=lambda x: x.get("filedAt", ""), 
                reverse=True
            )
        }
        
        logger.info("fulltext_discovery_completed",
                   cik=cik_normalized,
                   total_filings=len(all_filings),
                   categories_count=len(categories_found))
        
        return result
    
    async def _search_with_query(
        self,
        client: httpx.AsyncClient,
        query: str,
        cik: str,
        start_date: str,
        end_date: str,
        max_pages: int = 5
    ) -> List[Dict]:
        """Ejecuta búsqueda full-text con rate limiting y retry."""
        all_results = []
        
        for page in range(1, max_pages + 1):
            payload = {
                "query": query,
                "ciks": [cik],
                "startDate": start_date,
                "endDate": end_date,
                "page": str(page)
            }
            
            # Retry con backoff exponencial para errores 429
            max_retries = 3
            for retry in range(max_retries):
                try:
                    # Rate limiting - esperar antes de cada request
                    await _fulltext_rate_limiter.acquire()
                    
                    response = await client.post(
                        f"{self.FULLTEXT_ENDPOINT}?token={self.api_key}",
                        json=payload
                    )
                    
                    if response.status_code == 429:
                        # Rate limit hit - backoff exponencial
                        wait_time = (2 ** retry) * 2  # 2, 4, 8 segundos
                        logger.warning("fulltext_rate_limit_hit", 
                                      retry=retry+1, 
                                      wait_seconds=wait_time,
                                      cik=cik)
                        await asyncio.sleep(wait_time)
                        continue
                    
                    if response.status_code != 200:
                        logger.warning("fulltext_search_error", 
                                      status=response.status_code,
                                      cik=cik)
                        break
                    
                    data = response.json()
                    filings = data.get("filings", [])
                    all_results.extend(filings)
                    
                    # Si menos de 100, no hay más páginas
                    if len(filings) < 100:
                        break
                    
                    # Request exitosa, salir del retry loop
                    break
                    
                except Exception as e:
                    logger.error("fulltext_search_exception", error=str(e), retry=retry)
                    if retry < max_retries - 1:
                        await asyncio.sleep(2 ** retry)
                    else:
                        break
            else:
                # Se agotaron los retries
                logger.error("fulltext_search_max_retries", cik=cik, page=page)
                break
        
        return all_results
    
    async def search_specific_instruments(
        self,
        cik: str,
        instruments: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, List[Dict]]:
        """
        Busca instrumentos específicos.
        
        Args:
            cik: CIK de la empresa
            instruments: Lista de categorías (ej: ["WARRANTS", "ATM", "SHELF"])
            
        Returns:
            {instrument: [filings]}
        """
        result = {}
        
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*5)).strftime("%Y-%m-%d")
        
        cik_normalized = cik.lstrip('0')
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            for instrument in instruments:
                if instrument not in DILUTION_KEYWORDS:
                    logger.warning("unknown_instrument", instrument=instrument)
                    continue
                
                keywords = DILUTION_KEYWORDS[instrument]
                query = ' OR '.join(keywords)
                
                filings = await self._search_with_query(
                    client=client,
                    query=query,
                    cik=cik_normalized,
                    start_date=start_date,
                    end_date=end_date,
                    max_pages=3
                )
                
                result[instrument] = filings
        
        return result
    
    # =========================================================================
    # FORM S-1 / 424B4 API - DATOS ESTRUCTURADOS DE OFFERINGS
    # =========================================================================
    
    async def get_prospectus_data(
        self,
        cik: str,
        start_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Obtener datos estructurados de prospectuses (S-1, 424B4).
        
        Devuelve datos ya parseados:
        - Offering amounts (total, per share)
        - Securities types
        - Underwriters
        - Law firms, auditors
        - Management info
        """
        if not self.api_key:
            return []
        
        cik_normalized = cik.lstrip('0')
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*7)).strftime("%Y-%m-%d")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "query": f"cik:{cik_normalized} AND filedAt:[{start_date} TO *]",
                    "from": "0",
                    "size": "50",
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
                
                all_results = []
                
                # Paginar hasta obtener todos (con rate limiting)
                for offset in range(0, 500, 50):
                    payload["from"] = str(offset)
                    
                    # Rate limiting
                    await _query_rate_limiter.acquire()
                    
                    response = await client.post(
                        f"{self.S1_424B4_ENDPOINT}?token={self.api_key}",
                        json=payload
                    )
                    
                    if response.status_code == 429:
                        logger.warning("s1_424b4_rate_limit", offset=offset)
                        await asyncio.sleep(2)
                        continue
                    
                    if response.status_code != 200:
                        logger.warning("s1_424b4_api_error", status=response.status_code)
                        break
                    
                    data = response.json()
                    results = data.get("data", [])
                    all_results.extend(results)
                    
                    total = data.get("total", {}).get("value", 0)
                    if offset + 50 >= total:
                        break
                
                logger.info("prospectus_data_fetched",
                           cik=cik_normalized,
                           total=len(all_results))
                
                return all_results
                
        except Exception as e:
            logger.error("prospectus_api_exception", error=str(e))
            return []
    
    # =========================================================================
    # FORM D API - PRIVATE PLACEMENTS
    # =========================================================================
    
    async def get_form_d_offerings(
        self,
        cik: str,
        start_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Obtener Form D offerings (private placements).
        
        Devuelve datos estructurados:
        - Total offering amount
        - Amount sold / remaining
        - Security types (equity, debt, options)
        - Investors info
        - Sales compensation
        """
        if not self.api_key:
            return []
        
        # Form D necesita CIK con ceros (10 dígitos)
        cik_padded = cik.lstrip('0').zfill(10)
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*7)).strftime("%Y-%m-%d")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "query": f"primaryIssuer.cik:0{cik_padded}",
                    "from": "0",
                    "size": "50",
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
                
                all_results = []
                
                for offset in range(0, 200, 50):
                    payload["from"] = str(offset)
                    
                    # Rate limiting
                    await _query_rate_limiter.acquire()
                    
                    response = await client.post(
                        f"{self.FORM_D_ENDPOINT}?token={self.api_key}",
                        json=payload
                    )
                    
                    if response.status_code == 429:
                        logger.warning("form_d_rate_limit", offset=offset)
                        await asyncio.sleep(2)
                        continue
                    
                    if response.status_code != 200:
                        logger.warning("form_d_api_error", status=response.status_code)
                        break
                    
                    data = response.json()
                    results = data.get("offerings", [])
                    all_results.extend(results)
                    
                    total = data.get("total", {}).get("value", 0)
                    if offset + 50 >= total:
                        break
                
                logger.info("form_d_offerings_fetched",
                           cik=cik_padded,
                           total=len(all_results))
                
                return all_results
                
        except Exception as e:
            logger.error("form_d_exception", error=str(e))
            return []
    
    # =========================================================================
    # MÉTODO HÍBRIDO COMPLETO - COMBINA TODO
    # =========================================================================
    
    async def comprehensive_dilution_discovery(
        self,
        cik: str,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Descubrimiento COMPLETO de dilución usando todas las fuentes:
        1. Full-Text Search (todas las keywords)
        2. Form S-1/424B4 API (datos estructurados de offerings)
        3. Form D API (private placements)
        
        Returns:
            {
                "ticker": str,
                "cik": str,
                "fulltext_results": {...},
                "prospectus_data": [...],
                "form_d_offerings": [...],
                "summary": {
                    "has_warrants": bool,
                    "has_atm": bool,
                    "has_shelf": bool,
                    "has_convertibles": bool,
                    "has_private_placements": bool,
                    "has_equity_line": bool,
                    "total_filings_with_dilution": int,
                    "categories_detected": [...]
                },
                "priority_filings": [...]  # Los más importantes para procesar con Grok
            }
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365*7)).strftime("%Y-%m-%d")
        
        cik_normalized = cik.lstrip('0')
        
        logger.info("comprehensive_discovery_start", 
                   ticker=ticker, 
                   cik=cik_normalized)
        
        # 1. Full-Text Search - todas las categorías
        fulltext_results = await self.discover_all_dilution_filings(
            cik=cik_normalized,
            start_date=start_date,
            end_date=end_date
        )
        
        # 2. Form S-1/424B4 API - datos estructurados
        prospectus_data = await self.get_prospectus_data(
            cik=cik_normalized,
            start_date=start_date
        )
        
        # 3. Form D API - private placements
        form_d_data = await self.get_form_d_offerings(
            cik=cik_normalized,
            start_date=start_date
        )
        
        # Construir resumen
        categories = set(fulltext_results.get("categories_found", []))
        
        summary = {
            "has_warrants": any(c in categories for c in [
                "WARRANTS", "PRE_FUNDED_WARRANTS", "PENNY_WARRANTS", "PLACEMENT_AGENT_WARRANTS"
            ]),
            "has_atm": "ATM" in categories,
            "has_shelf": "SHELF" in categories or "BABY_SHELF" in categories,
            "has_convertibles": any(c in categories for c in [
                "CONVERTIBLE_NOTES", "CONVERTIBLE_PREFERRED"
            ]),
            "has_private_placements": "PRIVATE_PLACEMENT" in categories or len(form_d_data) > 0,
            "has_equity_line": "EQUITY_LINE" in categories,
            "has_public_offerings": "PUBLIC_OFFERING" in categories or "REGISTERED_DIRECT" in categories,
            "has_options_rsu": any(c in categories for c in [
                "STOCK_OPTIONS", "RSU_EQUITY_COMP", "ESPP"
            ]),
            "has_anti_dilution": "ANTI_DILUTION" in categories,
            "total_filings_with_dilution": fulltext_results.get("total_unique_filings", 0),
            "categories_detected": sorted(list(categories)),
            "prospectus_count": len(prospectus_data),
            "form_d_count": len(form_d_data),
        }
        
        # Identificar filings prioritarios para Grok
        priority_filings = self._identify_priority_filings(
            fulltext_results.get("all_filings", [])
        )
        
        result = {
            "ticker": ticker,
            "cik": cik_normalized,
            "discovery_date": datetime.now().isoformat(),
            "date_range": {"start": start_date, "end": end_date},
            "fulltext_results": fulltext_results,
            "prospectus_data": prospectus_data,
            "form_d_offerings": form_d_data,
            "summary": summary,
            "priority_filings": priority_filings,
        }
        
        logger.info("comprehensive_discovery_completed",
                   ticker=ticker,
                   total_filings=summary["total_filings_with_dilution"],
                   categories=len(summary["categories_detected"]),
                   priority_filings=len(priority_filings))
        
        return result
    
    def _identify_priority_filings(
        self,
        filings: List[Dict],
        max_priority: int = 50
    ) -> List[Dict]:
        """
        Identifica los filings más importantes para procesar con Grok.
        
        Prioridad:
        1. 424B5, 424B3 (prospectus supplements) - ATM, offerings
        2. S-3, F-3 (shelf registrations)
        3. S-1, F-1 (registration statements)
        4. 8-K (current reports) - solo los recientes
        5. 10-K, 10-Q (financials) - solo más recientes
        """
        priority_form_types = {
            "424B5": 1,
            "424B3": 1,
            "424B4": 1,
            "S-3": 2,
            "S-3/A": 2,
            "F-3": 2,
            "F-3/A": 2,
            "S-1": 3,
            "S-1/A": 3,
            "F-1": 3,
            "F-1/A": 3,
            "8-K": 4,
            "8-K/A": 4,
            "6-K": 4,
            "10-K": 5,
            "10-Q": 5,
            "20-F": 5,
        }
        
        # Filtrar y ordenar
        prioritized = []
        for f in filings:
            form_type = f.get("formType", "")
            priority = priority_form_types.get(form_type, 10)
            
            # Añadir score basado en categorías
            categories = f.get("categories", [])
            category_boost = 0
            if "WARRANTS" in categories or "ATM" in categories:
                category_boost = -1  # Mayor prioridad
            if "SHELF" in categories or "CONVERTIBLE_NOTES" in categories:
                category_boost = -0.5
            
            prioritized.append({
                **f,
                "_priority_score": priority + category_boost
            })
        
        # Ordenar por prioridad y fecha
        prioritized.sort(key=lambda x: (
            x["_priority_score"],
            x.get("filedAt", "") or ""
        ))
        
        # Retornar top N, removiendo score temporal
        result = []
        for f in prioritized[:max_priority]:
            f_copy = {k: v for k, v in f.items() if not k.startswith("_")}
            result.append(f_copy)
        
        return result


# Singleton
_fulltext_search: Optional[SECFullTextSearch] = None


def get_fulltext_search() -> SECFullTextSearch:
    """Get or create fulltext search instance"""
    global _fulltext_search
    if _fulltext_search is None:
        _fulltext_search = SECFullTextSearch()
    return _fulltext_search
