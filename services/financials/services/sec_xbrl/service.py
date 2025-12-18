"""
SEC XBRL Service - Servicio principal para extracción de datos financieros via SEC-API.

Usa:
- extractors.py: Extracción y normalización de datos XBRL
- calculators.py: Métricas calculadas (márgenes, YoY, FCF)
- structures.py: Estructuras jerárquicas para display
- splits.py: Ajustes por stock splits
"""

import httpx
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from collections import Counter

from shared.utils.logger import get_logger

from .extractors import XBRLExtractor
from .calculators import FinancialCalculator
from .structures import get_structure, CUSTOM_LABELS
from .splits import SplitAdjuster

logger = get_logger(__name__)


class SECXBRLService:
    """
    Servicio principal para obtener datos financieros de SEC-API.
    
    Features:
    - Extracción semántica de datos XBRL
    - Ajuste automático por stock splits
    - Métricas calculadas (márgenes, YoY, FCF)
    - Estructuras jerárquicas para display profesional
    - Soporte para empresas US (10-K/10-Q) y extranjeras (20-F/6-K)
    """
    
    BASE_URL = "https://api.sec-api.io"
    MAX_CONCURRENT_XBRL = 8
    XBRL_REQUEST_DELAY = 0.05
    
    def __init__(self, api_key: str, polygon_api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=60.0)
        self._xbrl_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_XBRL)
        
        # Componentes
        self.extractor = XBRLExtractor()
        self.calculator = FinancialCalculator()
        self.split_adjuster = SplitAdjuster(polygon_api_key)
        
        # Caché de industria
        self._industry_cache: Dict[str, Optional[str]] = {}
    
    async def close(self):
        await self.client.aclose()
    
    # =========================================================================
    # API PRINCIPAL
    # =========================================================================
    
    async def get_financials(
        self,
        ticker: str,
        period: str = "annual",
        limit: int = 10,
        cik: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtener datos financieros consolidados.
        
        Args:
            ticker: Símbolo del ticker
            period: "annual" o "quarter"
            limit: Número de períodos a obtener
            cik: CIK de la empresa (recomendado para evitar mezclar datos)
        """
        start_time = asyncio.get_event_loop().time()
        
        # Determinar form types
        if period == "annual":
            form_types = ["10-K", "20-F", "S-1", "S-1/A"]
        else:
            form_types = ["10-Q", "6-K"]
        
        # 1. Obtener filings y splits en paralelo
        filing_tasks = [self.get_filings(ticker, ft, limit + 5, cik=cik) for ft in form_types]
        splits_task = self.split_adjuster.get_splits(ticker)
        
        results = await asyncio.gather(*filing_tasks, splits_task)
        
        all_filings = []
        for i, ft in enumerate(form_types):
            all_filings.extend(results[i] or [])
        splits = results[-1]
        
        # Ordenar y deduplicar
        all_filings.sort(key=lambda x: x.get("filedAt", ""), reverse=True)
        filings = self._deduplicate_filings(all_filings, period)
        
        if not filings:
            return self._empty_response(ticker)
        
        logger.info(f"[{ticker}] Got {len(filings)} filings, {len(splits)} splits")
        
        # 2. Fetch XBRL data en paralelo
        is_quarterly = (period == "quarterly")
        xbrl_tasks = [
            self._fetch_xbrl_with_semaphore(filing, is_quarterly) 
            for filing in filings[:limit]
        ]
        
        xbrl_results = await asyncio.gather(*xbrl_tasks, return_exceptions=True)
        
        # 3. Procesar resultados
        income_data, balance_data, cashflow_data = [], [], []
        fiscal_years, period_end_dates = [], []
        raw_xbrl_latest = None  # Para extraer segmentos
        
        if is_quarterly:
            fiscal_years, period_end_dates, income_data, balance_data, cashflow_data = \
                self._process_quarterly_results(xbrl_results)
        else:
            fiscal_years, period_end_dates, income_data, balance_data, cashflow_data, raw_xbrl_latest = \
                self._process_annual_results(xbrl_results, filings, ticker)
        
        if not fiscal_years:
            return self._empty_response(ticker)
        
        num_periods = len(fiscal_years)
        logger.info(f"[{ticker}] Extracted {num_periods} periods")
        
        # 4. Consolidar semánticamente
        income_consolidated = self.extractor.consolidate_fields(income_data, fiscal_years)
        balance_consolidated = self.extractor.consolidate_fields(balance_data, fiscal_years)
        cashflow_consolidated = self.extractor.consolidate_fields(cashflow_data, fiscal_years)
        
        # 4.1 Extraer segmentos especiales (Finance Division para CAT, GE, etc.)
        if raw_xbrl_latest:
            # Finance Division Revenue
            finance_div = self.extractor.extract_finance_division_revenue(raw_xbrl_latest, fiscal_years)
            if finance_div:
                has_data = any(v is not None for v in finance_div.get('values', []))
                if has_data:
                    income_consolidated = [
                        f for f in income_consolidated 
                        if f.get('key') != 'finance_division_revenue'
                    ]
                    income_consolidated.append(finance_div)
                    logger.info(f"[{ticker}] Extracted Finance Division Revenue from segments")
        
            # Finance Division Operating Expenses + Interest Expense
            finance_costs = self.extractor.extract_finance_division_costs(raw_xbrl_latest, fiscal_years)
            if finance_costs:
                for cost_field in finance_costs:
                    has_data = any(v is not None for v in cost_field.get('values', []))
                    if has_data:
                        # Remover duplicados si existen
                        income_consolidated = [
                            f for f in income_consolidated 
                            if f.get('key') != cost_field.get('key')
                        ]
                        income_consolidated.append(cost_field)
                        logger.info(f"[{ticker}] Extracted {cost_field.get('key')} from segments")
        
        # 5. Detectar industria TEMPRANO (antes de métricas calculadas)
        # Esto permite que los cálculos como Gross Profit usen fórmulas específicas por industria
        financial_preview = {"income_statement": income_consolidated}
        industry = await self._detect_industry(ticker, financial_preview)
        logger.info(f"[{ticker}] Detected industry: {industry or 'standard'}")
        
        # 6. Ajustar presentación de Revenue ANTES de métricas
        # Para que operating_revenue esté disponible para cálculos
        income_consolidated = self.calculator.adjust_revenue_presentation(income_consolidated, industry)
        
        # 7. Recalcular EBITDA
        income_consolidated = self.calculator.recalculate_ebitda(
            income_consolidated, cashflow_consolidated, num_periods
        )
        
        # 8. Ajustar por splits
        if splits:
            income_consolidated = self.split_adjuster.adjust_fields(
                income_consolidated, splits, period_end_dates
            )
        
        # 9. Añadir métricas calculadas (con contexto de industria para fórmulas correctas)
        income_consolidated = self.calculator.add_income_metrics(
            income_consolidated, cashflow_consolidated, num_periods, industry=industry
        )
        cashflow_consolidated = self.calculator.add_cashflow_metrics(
            income_consolidated, cashflow_consolidated, num_periods
        )
        balance_consolidated = self.calculator.add_balance_metrics(
            balance_consolidated, income_consolidated, num_periods
        )
        
        # 10. Filtrar campos con pocos datos
        income_filtered = self.extractor.filter_low_value_fields(income_consolidated)
        balance_filtered = self.extractor.filter_low_value_fields(balance_consolidated)
        cashflow_filtered = self.extractor.filter_low_value_fields(cashflow_consolidated)
        
        # 11. Añadir estructura jerárquica
        income_structured = self._add_structure_metadata(income_filtered, 'income', industry)
        balance_structured = self._add_structure_metadata(balance_filtered, 'balance', industry)
        cashflow_structured = self._add_structure_metadata(cashflow_filtered, 'cashflow', industry)
        
        # 12. Enriquecer con edgartools
        income_structured = await self._enrich_income_statement(income_structured, ticker, fiscal_years)
        
        # 13. Filtrar segmentos de revenue para industrias "standard" (como TIKR)
        # TIKR solo muestra breakdown de revenue para:
        # - Banking/fintech (Interest Income, Non-Interest Income)
        # - Empresas con Finance Division (CAT, GE, etc.)
        # NO muestra breakdown de producto/servicio para tech puro (ORCL Cloud, AAPL Products)
        if industry in (None, 'standard'):
            # Segmentos de producto/servicio que NO se muestran (son informativos, no estructurales)
            product_service_segments = {
                'services_revenue', 'service_revenue', 'product_revenue', 'products_revenue',
                'cloud_services_and_license_support_revenue', 'cloud_license_and_on_premise_license_revenue',
                'cloud_revenues', 'license_revenue', 'licenses_revenue', 'maintenance_revenue',
                'hardware_revenues', 'subscription_revenue', 'advertising_revenue', 'membership_fees',
            }
            # Segmentos que SÍ se muestran (divisiones financieras, son estructuralmente diferentes)
            keep_segments = {
                'finance_division_revenue', 'financial_products_revenue', 'financing_revenue',
                'insurance_revenue', 'leasing_revenue',
            }
            income_structured = [
                f for f in income_structured 
                if f.get('key') not in product_service_segments or f.get('key') in keep_segments
            ]
        
        total_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"[{ticker}] Total: {total_time:.2f}s")
        
        # Detectar mes de cierre fiscal
        fiscal_year_end_month = None
        if period_end_dates:
            months = [int(d[5:7]) for d in period_end_dates if d and len(d) >= 7]
            if months:
                fiscal_year_end_month = Counter(months).most_common(1)[0][0]
        
        has_split_adjustments = any(f.get('split_adjusted') for f in income_structured)
        
        return {
            "symbol": ticker,
            "currency": "USD",
            "source": "sec-api-xbrl",
            "symbiotic": True,
            "split_adjusted": has_split_adjustments,
            "splits": [{"date": s.get("execution_date"), "ratio": f"{s.get('split_to')}:{s.get('split_from')}"} for s in splits] if splits else [],
            "periods": fiscal_years,
            "period_end_dates": period_end_dates,
            "fiscal_year_end_month": fiscal_year_end_month,
            "industry": industry,
            "income_statement": income_structured,
            "balance_sheet": balance_structured,
            "cash_flow": cashflow_structured,
            "processing_time_seconds": round(total_time, 2),
            "last_updated": datetime.utcnow().isoformat()
        }
    
    # =========================================================================
    # FILINGS
    # =========================================================================
    
    async def get_cik(self, ticker: str) -> Optional[str]:
        """Obtener el CIK de una empresa."""
        try:
            response = await self.client.post(
                f"{self.BASE_URL}?token={self.api_key}",
                json={
                    "query": {"query_string": {"query": f'ticker:{ticker}'}},
                    "from": "0",
                    "size": "1"
                }
            )
            response.raise_for_status()
            data = response.json()
            filings = data.get("filings", [])
            return filings[0].get("cik") if filings else None
        except Exception as e:
            logger.error(f"[{ticker}] Error getting CIK: {e}")
            return None
    
    # Mapeo de tickers alternativos (share classes diferentes)
    TICKER_ALIASES = {
        "GOOGL": ["GOOG", "GOOGL"],
        "GOOG": ["GOOG", "GOOGL"],
        "BRK.A": ["BRK-A", "BRK.A", "BRK-B", "BRK.B"],
        "BRK.B": ["BRK-A", "BRK.A", "BRK-B", "BRK.B"],
        "BRK-A": ["BRK-A", "BRK.A", "BRK-B", "BRK.B"],
        "BRK-B": ["BRK-A", "BRK.A", "BRK-B", "BRK.B"],
    }
    
    async def get_filings(
        self, 
        ticker: str, 
        form_type: str = "10-K",
        limit: int = 10,
        cik: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Obtener filings por CIK (preferido) o ticker."""
        # Aumentar tamaño de búsqueda para obtener más histórico
        search_size = max(limit + 10, 25)
        
        try:
            # 1. Buscar por CIK si está disponible (método más confiable)
            if cik:
                normalized_cik = cik.lstrip('0') or '0'
                logger.info(f"[{ticker}] Searching by CIK {normalized_cik}")
                response = await self.client.post(
                    f"{self.BASE_URL}?token={self.api_key}",
                    json={
                        "query": {"query_string": {"query": f'cik:{normalized_cik} AND formType:"{form_type}"'}},
                        "from": "0",
                        "size": str(search_size),
                        "sort": [{"filedAt": {"order": "desc"}}]
                    }
                )
                response.raise_for_status()
                filings = response.json().get("filings", [])
                if filings:
                    logger.info(f"[{ticker}] Found {len(filings)} filings by CIK")
                    return filings
            
            # 2. Buscar por ticker principal
            response = await self.client.post(
                f"{self.BASE_URL}?token={self.api_key}",
                json={
                    "query": {"query_string": {"query": f'ticker:{ticker} AND formType:"{form_type}"'}},
                    "from": "0",
                    "size": str(search_size),
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
            )
            response.raise_for_status()
            filings = response.json().get("filings", [])
            
            # 3. Si hay pocos resultados, buscar por tickers alternativos
            if len(filings) < limit and ticker.upper() in self.TICKER_ALIASES:
                aliases = self.TICKER_ALIASES[ticker.upper()]
                ticker_query = " OR ".join([f'ticker:{t}' for t in aliases])
                logger.info(f"[{ticker}] Few results, searching aliases: {aliases}")
                
                response = await self.client.post(
                    f"{self.BASE_URL}?token={self.api_key}",
                    json={
                        "query": {"query_string": {"query": f'({ticker_query}) AND formType:"{form_type}"'}},
                        "from": "0",
                        "size": str(search_size),
                        "sort": [{"filedAt": {"order": "desc"}}]
                    }
                )
                response.raise_for_status()
                alias_filings = response.json().get("filings", [])
                if len(alias_filings) > len(filings):
                    filings = alias_filings
                    logger.info(f"[{ticker}] Found {len(filings)} filings via aliases")
            
            # 4. Si aún hay pocos, intentar buscar por nombre de compañía
            if len(filings) < limit:
                # Extraer CIK del primer filing si existe
                if filings and filings[0].get("cik"):
                    cik_from_filing = filings[0].get("cik")
                    logger.info(f"[{ticker}] Trying CIK from filing: {cik_from_filing}")
                    response = await self.client.post(
                        f"{self.BASE_URL}?token={self.api_key}",
                        json={
                            "query": {"query_string": {"query": f'cik:{cik_from_filing} AND formType:"{form_type}"'}},
                            "from": "0",
                            "size": str(search_size),
                            "sort": [{"filedAt": {"order": "desc"}}]
                        }
                    )
                    response.raise_for_status()
                    cik_filings = response.json().get("filings", [])
                    if len(cik_filings) > len(filings):
                        filings = cik_filings
                        logger.info(f"[{ticker}] Found {len(filings)} filings by extracted CIK")
            
            return filings
            
        except Exception as e:
            logger.error(f"[{ticker}] Error getting filings: {e}")
            return []
    
    async def get_xbrl_data(self, accession_no: str, max_retries: int = 3) -> Optional[Dict]:
        """Obtener datos XBRL con retry."""
        for attempt in range(max_retries):
            try:
                response = await self.client.get(
                    f"{self.BASE_URL}/xbrl-to-json",
                    params={"accession-no": accession_no, "token": self.api_key}
                )
                
                if response.status_code == 429:
                    await asyncio.sleep((attempt + 1) * 2)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Error getting XBRL for {accession_no}: {e}")
                await asyncio.sleep((attempt + 1) * 2)
        
        return None
    
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    def _deduplicate_filings(self, all_filings: List[Dict], period: str) -> List[Dict]:
        """Deduplicar filings por año/período."""
        if period == "annual":
            seen_years = set()
            filings = []
            for f in all_filings:
                fiscal_year = f.get("filedAt", "")[:4]
                form = f.get("formType", "")
                
                if fiscal_year not in seen_years:
                    filings.append(f)
                    seen_years.add(fiscal_year)
                elif form == "10-K":
                    for i, existing in enumerate(filings):
                        if existing.get("filedAt", "")[:4] == fiscal_year:
                            if existing.get("formType") == "20-F":
                                filings[i] = f
                            break
            return filings
        else:
            seen_periods = set()
            filings = []
            for f in all_filings:
                period_of_report = f.get("periodOfReport", "")
                if period_of_report not in seen_periods:
                    filings.append(f)
                    seen_periods.add(period_of_report)
            return filings
    
    async def _fetch_xbrl_with_semaphore(
        self, 
        filing: Dict[str, Any],
        is_quarterly: bool = False
    ) -> Optional[Tuple[str, str, str, Dict]]:
        """Fetch XBRL data con semáforo."""
        async with self._xbrl_semaphore:
            accession_no = filing.get("accessionNo")
            filed_at = filing.get("filedAt", "")
            
            await asyncio.sleep(self.XBRL_REQUEST_DELAY)
            
            xbrl = await self.get_xbrl_data(accession_no)
            if not xbrl:
                return None
            
            period_end = self._get_period_end_date(xbrl, filed_at)
            
            if is_quarterly and period_end:
                try:
                    month = int(period_end[5:7])
                    year = period_end[:4]
                    quarter = (month - 1) // 3 + 1
                    period_label = f"Q{quarter} {year}"
                except:
                    period_label = filed_at[:4]
            else:
                period_label = period_end[:4] if period_end else filed_at[:4]
            
            return (period_label, filed_at, period_end, xbrl)
    
    def _get_period_end_date(self, xbrl: Dict, filed_at: str) -> str:
        """Obtener la fecha de fin del período."""
        for section in ["BalanceSheets", "StatementsOfFinancialPosition"]:
            if section in xbrl:
                section_data = xbrl[section]
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        if isinstance(value, dict) and "period" in value:
                            period = value["period"]
                            if isinstance(period, dict) and "endDate" in period:
                                return period["endDate"]
        
        if filed_at and len(filed_at) >= 10:
            return filed_at[:10]
        
        return filed_at[:4] + "-12-31" if filed_at else ""
    
    def _extract_filing_data(
        self, 
        xbrl: Dict, 
        fiscal_year: str
    ) -> Tuple[Dict, Dict, Dict]:
        """Extraer datos de income, balance y cashflow."""
        income_fields = {}
        balance_fields = {}
        cashflow_fields = {}
        
        for section_name, section_data in xbrl.items():
            if not isinstance(section_data, dict):
                continue
            if self.extractor.should_skip_section(section_name):
                continue
            
            section_category = self.extractor.get_section_category(section_name)
            fields = self.extractor.extract_section_fields(xbrl, section_name, fiscal_year)
            
            for field_key, field_data in fields.items():
                is_primary_statement = any(x in section_name.lower() for x in [
                    'statementsof', 'balancesheets', 'consolidatedstatements'
                ])
                
                if is_primary_statement and section_category:
                    category = section_category
                else:
                    original_name = field_data[1] if isinstance(field_data, tuple) else field_key
                    concept_category = self.extractor.classify_concept(original_name)
                    category = concept_category or section_category
                
                if category == "income":
                    if field_key not in income_fields:
                        income_fields[field_key] = field_data
                elif category == "balance":
                    if field_key not in balance_fields:
                        balance_fields[field_key] = field_data
                elif category == "cashflow":
                    if field_key not in cashflow_fields:
                        cashflow_fields[field_key] = field_data
        
        return income_fields, balance_fields, cashflow_fields
    
    def _process_quarterly_results(self, xbrl_results: List) -> Tuple:
        """Procesar resultados quarterly."""
        income_data, balance_data, cashflow_data = [], [], []
        fiscal_years, period_end_dates = [], []
        
        for result in xbrl_results:
            if result is None or isinstance(result, Exception):
                continue
            
            fiscal_year, filed_at, period_end, xbrl = result
            quarters = self._extract_all_quarters_from_xbrl(xbrl)
            
            if quarters:
                q_label, q_end_date, q_income, q_balance, q_cashflow = quarters[0]
                
                if q_label not in fiscal_years:
                    fiscal_years.append(q_label)
                    period_end_dates.append(q_end_date)
                    income_data.append(q_income)
                    balance_data.append(q_balance)
                    cashflow_data.append(q_cashflow)
        
        return fiscal_years, period_end_dates, income_data, balance_data, cashflow_data
    
    def _process_annual_results(self, xbrl_results: List, filings: List, ticker: str) -> Tuple:
        """
        Procesar resultados annual.
        
        IMPORTANTE: Combina datos de múltiples 10-Ks a nivel de CAMPO, no de año.
        Esto permite que si un 10-K no tiene un campo específico para un año,
        se use el dato del 10-K que sí lo tiene.
        
        Returns:
            Tuple de (fiscal_years, period_end_dates, income_data, balance_data, cashflow_data, raw_xbrl)
            donde raw_xbrl es el XBRL más reciente para extraer segmentos
        """
        all_years_data = {}
        FORM_PRIORITY = {"10-K": 1, "20-F": 2, "S-1": 3, "S-1/A": 3}
        
        # Guardar el XBRL más reciente para extraer segmentos
        raw_xbrl_latest = None
        
        for i, result in enumerate(xbrl_results):
            if result is None or isinstance(result, Exception):
                continue
            
            fiscal_year, filed_at, period_end, xbrl = result
            form_type = filings[i].get("formType", "10-K") if i < len(filings) else "10-K"
            
            # Guardar el primer XBRL válido (más reciente) para segmentos
            if raw_xbrl_latest is None:
                raw_xbrl_latest = xbrl
            
            all_periods = self._extract_all_annual_periods(xbrl, form_type)
            
            for year_data in all_periods:
                year, end_date, income, balance, cashflow, ft = year_data
                priority = FORM_PRIORITY.get(ft, 99)
                
                if year not in all_years_data:
                    # Primera vez que vemos este año
                    all_years_data[year] = {
                        'end_date': end_date,
                        'income': income,
                        'balance': balance,
                        'cashflow': cashflow,
                        'form_type': ft,
                        'priority': priority
                    }
                else:
                    # Año ya existe - combinar a nivel de campo
                    existing = all_years_data[year]
                    existing_priority = existing['priority']
                    
                    # Si el nuevo filing tiene mayor prioridad, reemplazar todo
                    if priority < existing_priority:
                        all_years_data[year] = {
                            'end_date': end_date,
                            'income': income,
                            'balance': balance,
                            'cashflow': cashflow,
                            'form_type': ft,
                            'priority': priority
                        }
                    else:
                        # Misma prioridad: combinar campos faltantes (None)
                        # Esto permite que datos de 10-Ks anteriores llenen campos
                        # que el 10-K más reciente no tiene para ese año
                        self._merge_fields(existing['income'], income)
                        self._merge_fields(existing['balance'], balance)
                        self._merge_fields(existing['cashflow'], cashflow)
        
        fiscal_years, period_end_dates = [], []
        income_data, balance_data, cashflow_data = [], [], []
        
        for year in sorted(all_years_data.keys(), reverse=True):
            year_info = all_years_data[year]
            fiscal_years.append(year)
            period_end_dates.append(year_info['end_date'])
            income_data.append(year_info['income'])
            balance_data.append(year_info['balance'])
            cashflow_data.append(year_info['cashflow'])
        
        sources_used = {}
        for year in all_years_data:
            ft = all_years_data[year]['form_type']
            sources_used[ft] = sources_used.get(ft, 0) + 1
        logger.info(f"[{ticker}] Year sources: {sources_used}")
        
        return fiscal_years, period_end_dates, income_data, balance_data, cashflow_data, raw_xbrl_latest
    
    def _merge_fields(self, existing: Dict, new: Dict) -> None:
        """
        Combinar campos de dos diccionarios.
        Solo agrega campos que están en 'new' pero no en 'existing' (o son None).
        """
        if not new:
            return
        for key, value in new.items():
            if key not in existing:
                existing[key] = value
            elif existing[key] is None and value is not None:
                # El campo existe pero es None, usar el nuevo valor
                existing[key] = value
    
    def _extract_all_annual_periods(self, xbrl: Dict, form_type: str) -> List:
        """Extraer TODOS los años anuales de un XBRL."""
        from datetime import datetime
        
        annual_periods = {}
        
        # Buscar secciones de income statement (nombres varían por empresa)
        income_sections = [
            name for name in xbrl.keys()
            if any(kw in name.lower() for kw in ['income', 'operations', 'results', 'earnings'])
            and 'note' not in name.lower() and 'table' not in name.lower()
        ]
        
        # Fallback a nombres estándar si no encontramos nada
        if not income_sections:
            income_sections = ["StatementsOfIncome", "StatementsOfOperations", "StatementsOfComprehensiveIncome"]
        
        for section in income_sections:
            section_data = xbrl.get(section, {})
            for field_name, values in section_data.items():
                if not isinstance(values, list):
                    continue
                for item in values:
                    if not isinstance(item, dict) or item.get("segment"):
                        continue
                    period = item.get("period", {})
                    start = period.get("startDate", "")
                    end = period.get("endDate", "")
                    
                    if not start or not end:
                        continue
                    
                    try:
                        start_dt = datetime.strptime(start, "%Y-%m-%d")
                        end_dt = datetime.strptime(end, "%Y-%m-%d")
                        days = (end_dt - start_dt).days
                        
                        if 350 <= days <= 380:
                            fiscal_year = end[:4]
                            if fiscal_year not in annual_periods:
                                annual_periods[fiscal_year] = end
                    except ValueError:
                        continue
        
        if not annual_periods:
            return []
        
        results = []
        for fiscal_year in sorted(annual_periods.keys(), reverse=True):
            end_date = annual_periods[fiscal_year]
            income, balance, cashflow = self._extract_filing_data(xbrl, fiscal_year)
            
            if income or balance:
                results.append((fiscal_year, end_date, income, balance, cashflow, form_type))
        
        return results
    
    def _extract_all_quarters_from_xbrl(self, xbrl: Dict) -> List:
        """Extraer TODOS los trimestres de un XBRL."""
        from datetime import datetime
        
        quarterly_periods = set()
        income_sections = ["StatementsOfIncome", "StatementsOfComprehensiveIncome", "StatementsOfOperations"]
        
        for section in income_sections:
            section_data = xbrl.get(section, {})
            if not isinstance(section_data, dict):
                continue
            
            for field_name, values in section_data.items():
                if not isinstance(values, list):
                    continue
                
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    
                    period = item.get("period", {})
                    if not isinstance(period, dict):
                        continue
                    
                    start_date = period.get("startDate", "")
                    end_date = period.get("endDate", "")
                    
                    if start_date and end_date:
                        try:
                            start = datetime.strptime(start_date, "%Y-%m-%d")
                            end = datetime.strptime(end_date, "%Y-%m-%d")
                            days = (end - start).days
                            
                            if 80 <= days <= 100:
                                month = end.month
                                year = end.year
                                quarter = (month - 1) // 3 + 1
                                period_label = f"Q{quarter} {year}"
                                quarterly_periods.add((end_date, period_label))
                        except:
                            continue
        
        if not quarterly_periods:
            return []
        
        results = []
        for end_date, period_label in sorted(quarterly_periods, reverse=True):
            income_data = self._extract_fields_for_period(xbrl, "income", end_date)
            balance_data = self._extract_fields_for_period(xbrl, "balance", end_date)
            cashflow_data = self._extract_fields_for_period(xbrl, "cashflow", end_date)
            
            if income_data:
                results.append((period_label, end_date, income_data, balance_data, cashflow_data))
        
        return results
    
    def _extract_fields_for_period(self, xbrl: Dict, category: str, target_end_date: str) -> Dict:
        """Extraer campos para un período específico."""
        results = {}
        target_year_month = target_end_date[:7] if target_end_date else ""
        
        for section_name, section_data in xbrl.items():
            if not isinstance(section_data, dict):
                continue
            if self.extractor.should_skip_section(section_name):
                continue
            
            for field_name, values in section_data.items():
                if not isinstance(values, list):
                    continue
                
                concept_category = self.extractor.classify_concept(field_name)
                section_category = self.extractor.get_section_category(section_name)
                field_category = concept_category or section_category
                
                if field_category != category:
                    continue
                
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    
                    period = item.get("period", {})
                    if not isinstance(period, dict):
                        continue
                    
                    end_date = period.get("endDate", "")
                    instant = period.get("instant", "")
                    
                    date_match = False
                    if end_date == target_end_date or instant == target_end_date:
                        date_match = True
                    elif category == "balance" and target_year_month:
                        if (end_date and end_date[:7] == target_year_month) or \
                           (instant and instant[:7] == target_year_month):
                            date_match = True
                    
                    if date_match:
                        try:
                            raw_value = item.get("value")
                            if raw_value is None:
                                continue
                            value = float(raw_value)
                            normalized = self.extractor._camel_to_snake(field_name)
                            
                            segment = item.get("segment")
                            if normalized not in results or segment is None:
                                results[normalized] = (value, field_name)
                        except (ValueError, TypeError):
                            continue
        
        return results
    
    def _add_structure_metadata(
        self,
        fields: List[Dict],
        statement_type: str,
        industry: Optional[str] = None
    ) -> List[Dict]:
        """Añadir metadata de estructura jerárquica."""
        structure = get_structure(statement_type, industry)
        
        if not structure:
            return fields
        
        industry_specific_sections = [
            'Insurance Revenue', 'Insurance Costs', 'Insurance Assets', 'Insurance Liabilities',
            'Net Interest Income', 'Credit Provisions', 'Non-Interest Income', 'Non-Interest Expense',
            'Banking Assets', 'Banking Liabilities', 'Rental Revenue', 'Property Expenses', 'FFO',
        ]
        
        enriched = []
        for field in fields:
            key = field.get('key', '')
            field_copy = field.copy()
            
            if key in CUSTOM_LABELS:
                field_copy['label'] = CUSTOM_LABELS[key]
            
            if key in structure:
                meta = structure[key]
                field_copy['section'] = meta['section']
                field_copy['display_order'] = meta['order']
                field_copy['indent_level'] = meta['indent']
                field_copy['is_subtotal'] = meta['is_subtotal']
                
                if 'label' in meta:
                    field_copy['label'] = meta['label']
                
                field_copy['is_industry_specific'] = meta['section'] in industry_specific_sections
            else:
                field_copy['section'] = 'Other'
                field_copy['display_order'] = 9000
                field_copy['indent_level'] = 0
                field_copy['is_subtotal'] = False
                field_copy['is_industry_specific'] = False
            
            enriched.append(field_copy)
        
        enriched.sort(key=lambda x: x.get('display_order', 9999))
        
        return enriched
    
    async def _detect_industry(self, ticker: str, financial_data: Optional[Dict] = None) -> Optional[str]:
        """
        Detectar industria usando el sistema multi-tier profesional.
        
        Tiers:
        1. Company Overrides (curated) - Prioridad MÁXIMA
        2. Data-Driven Detection - Análisis de estructura financiera
        3. SIC Code Mapping - Mapeo estándar
        4. Default (standard) - Estructura GAAP estándar
        """
        if ticker in self._industry_cache:
            return self._industry_cache[ticker]
        
        try:
            # Importar el detector profesional
            from services.industry.detector import detect_industry
            
            # Obtener SIC code
            sic = None
            try:
                import edgar
                edgar.set_identity("Tradeul API api@tradeul.com")
                company = edgar.Company(ticker)
                sic = int(company.sic) if company.sic else None
            except Exception as e:
                logger.warning(f"[{ticker}] Could not get SIC code: {e}")
            
            # Detectar usando el sistema multi-tier
            industry = detect_industry(
                ticker=ticker,
                sic_code=sic,
                financial_data=financial_data
            )
            
            self._industry_cache[ticker] = industry
            return industry
            
        except Exception as e:
            logger.warning(f"[{ticker}] Could not detect industry: {e}")
            self._industry_cache[ticker] = None
            return None
    
    async def _enrich_income_statement(
        self, 
        income_fields: List[Dict], 
        ticker: str,
        periods: List[str]
    ) -> List[Dict]:
        """Enriquecer income statement con campos de edgartools."""
        try:
            from ..edgar import get_edgar_service
            
            service = get_edgar_service()
            enrichment_data = await service.get_enrichment_values(ticker, periods)
            
            if not enrichment_data:
                return income_fields
            
            # Corregir revenue si es necesario
            if 'revenue_total' in enrichment_data:
                revenue_field = next((f for f in income_fields if f['key'] == 'revenue'), None)
                if revenue_field:
                    corrected_values = enrichment_data['revenue_total']
                    original_values = revenue_field.get('values', [])
                    corrected = False
                    for i in range(len(original_values)):
                        orig = original_values[i] if i < len(original_values) else None
                        corr = corrected_values[i] if i < len(corrected_values) else None
                        if orig is not None and corr is not None:
                            if orig < corr * 0.5:
                                original_values[i] = corr
                                corrected = True
                    if corrected:
                        revenue_field['corrected'] = True
                        logger.info(f"[{ticker}] Revenue corrected from edgartools")
            
            existing_keys = {f['key'] for f in income_fields}
            
            ENRICHMENT_STRUCTURE = {
                'investment_income': {
                    'section': 'Revenue', 'order': 105, 'indent': 1,
                    'is_subtotal': False, 'label': 'Investment & Other Income', 'data_type': 'monetary',
                },
                'products_revenue': {
                    'section': 'Revenue', 'order': 106, 'indent': 1,
                    'is_subtotal': False, 'label': 'Products Revenue', 'data_type': 'monetary',
                },
                'services_revenue': {
                    'section': 'Revenue', 'order': 107, 'indent': 1,
                    'is_subtotal': False, 'label': 'Services Revenue', 'data_type': 'monetary',
                },
                'premiums': {
                    'section': 'Revenue', 'order': 104, 'indent': 1,
                    'is_subtotal': False, 'label': 'Premiums', 'data_type': 'monetary',
                },
            }
            
            added = []
            for key, values in enrichment_data.items():
                if key in existing_keys or key == 'revenue_total':
                    continue
                
                if not any(v is not None and v != 0 for v in values):
                    continue
                
                structure = ENRICHMENT_STRUCTURE.get(key, {})
                if not structure:
                    continue
                
                income_fields.append({
                    'key': key,
                    'label': structure['label'],
                    'values': values,
                    'data_type': structure['data_type'],
                    'section': structure['section'],
                    'display_order': structure['order'],
                    'indent_level': structure['indent'],
                    'is_subtotal': structure['is_subtotal'],
                    'source': 'edgartools',
                })
                added.append(key)
            
            if added:
                logger.info(f"[{ticker}] Enriched: {added}")
                income_fields.sort(key=lambda x: x.get('display_order', 9999))
            
            return income_fields
            
        except Exception as e:
            logger.warning(f"[{ticker}] Enrichment failed: {e}")
            return income_fields
    
    def _empty_response(self, ticker: str) -> Dict[str, Any]:
        return {
            "symbol": ticker,
            "currency": "USD",
            "source": "sec-api-xbrl",
            "symbiotic": True,
            "periods": [],
            "period_end_dates": [],
            "fiscal_year_end_month": None,
            "income_statement": [],
            "balance_sheet": [],
            "cash_flow": [],
            "last_updated": datetime.utcnow().isoformat()
        }

