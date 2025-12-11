"""
SEC-API XBRL Financials Service - PROFESSIONAL HYBRID APPROACH

Arquitectura de 3 capas:
1. CORE FIELDS (~80 campos): Regex preciso para campos principales
   → Revenue, Net Income, EPS, Assets, etc. con importancia asignada
2. FASB LABELS (10,732 campos): Labels oficiales de US-GAAP 2025
   → Si no hay match en CORE, usa el label oficial de FASB
3. FILTROS: Eliminar campos irrelevantes (OCI, reclassifications, etc.)

Source FASB: https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-lab-2025.xml
"""

import httpx
import asyncio
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from collections import defaultdict
from shared.utils.logger import get_logger

# FASB US-GAAP 2025 Taxonomy (siguiendo TDH - Taxonomy Development Handbook)
# - FASB_LABELS: Standard labels para display
# - FASB_DATA_TYPES: monetary, shares, percent, perShare, etc.
# - FASB_TOTAL_LABELS: Labels especiales para totales
# - FASB_BALANCE: debit (outflow) vs credit (inflow)
try:
    from .fasb_labels import FASB_LABELS, FASB_DATA_TYPES, FASB_TOTAL_LABELS, FASB_BALANCE
except ImportError:
    FASB_LABELS = {}
    FASB_DATA_TYPES = {}
    FASB_TOTAL_LABELS = {}
    FASB_BALANCE = {}
    
logger = get_logger(__name__)


class SECXBRLFinancialsService:
    """
    Servicio simbiótico profesional para SEC-API XBRL.
    Sin hardcodeos - todo es dinámico y basado en análisis semántico.
    Incluye ajuste automático por stock splits usando Polygon.
    
    NUEVO ENFOQUE (v2): Procesar TODAS las secciones del XBRL y clasificar
    cada campo por su concepto FASB, no por la sección en la que aparece.
    Esto captura campos como InterestExpense, EffectiveTaxRate, SharesOutstanding
    que antes se perdían por estar en secciones "Details".
    """
    
    BASE_URL = "https://api.sec-api.io"
    POLYGON_URL = "https://api.polygon.io"
    
    # CLASIFICACIÓN POR CONCEPTO (no por sección)
    # Patrones para determinar la categoría de cada campo XBRL
    INCOME_PATTERNS = [
        r'revenue', r'sales', r'cost.*goods', r'cost.*revenue', r'gross_profit',
        r'operating.*income', r'operating.*expense', r'research.*development',
        r'selling.*marketing', r'general.*admin', r'sg.*a', r'depreciation',
        r'amortization', r'interest.*income', r'interest.*expense', r'finance.*cost',
        r'income.*before.*tax', r'income.*tax', r'net_income', r'profit_loss',
        r'earnings.*share', r'eps', r'weighted.*average.*shares', r'shares.*outstanding',
        r'dividend.*per.*share', r'effective.*tax.*rate', r'nonoperating', r'other_income',
        r'foreign.*currency.*transaction', r'gain_loss', r'equity.*method.*investment',
        r'comprehensive_income',  # Ahora lo incluimos para capturar más datos
    ]
    
    BALANCE_PATTERNS = [
        r'^assets', r'current_assets', r'cash.*equivalent', r'^cash$', r'receivable',
        r'inventory', r'prepaid', r'property.*plant', r'goodwill', r'intangible',
        r'investment', r'^liabilities', r'current_liabilities', r'payable', r'accrued',
        r'debt', r'borrowing', r'deferred.*revenue', r'lease.*liability', r'equity',
        r'retained.*earnings', r'common.*stock', r'treasury', r'paid.*capital',
        r'accumulated.*other.*comprehensive', r'working.*capital', r'book.*value',
    ]
    
    CASHFLOW_PATTERNS = [
        r'cash.*operating', r'cash.*investing', r'cash.*financing', r'operating.*activities',
        r'investing.*activities', r'financing.*activities', r'capital.*expenditure',
        r'capex', r'dividend.*paid', r'repurchase.*stock', r'stock.*issued',
        r'proceeds.*debt', r'repayment.*debt', r'acquisition', r'free.*cash.*flow',
        r'change.*working.*capital', r'depreciation.*amortization',
    ]
    
    # Secciones a IGNORAR completamente (no contienen datos financieros útiles)
    SKIP_SECTIONS = {
        'CoverPage', 'DocumentAndEntityInformation', 'AuditInformation',
        'AccountingPolicies', 'Policies', 'Tables', 'Parenthetical',
        'InsiderTradingArrangements', 'SignificantAccountingPolicies',
    }
    
    # Configuración de paralelismo (SEC-API: 10 req/s para XBRL)
    MAX_CONCURRENT_XBRL = 8  # 8 paralelas = ~80% del límite (margen de seguridad)
    XBRL_REQUEST_DELAY = 0.05  # 50ms entre requests (20 req/s teórico, pero con 8 concurrent = ~8/s real)
    
    def __init__(self, api_key: str, polygon_api_key: str = None):
        self.api_key = api_key
        self.polygon_api_key = polygon_api_key
        self.client = httpx.AsyncClient(timeout=60.0)
        self._splits_cache: Dict[str, List[Dict]] = {}  # Cache de splits por ticker
        self._xbrl_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_XBRL)
    
    async def close(self):
        await self.client.aclose()
    
    # =========================================================================
    # STOCK SPLITS - Polygon API
    # =========================================================================
    
    async def get_splits(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Obtener historial de splits de Polygon.
        Cachea los resultados para evitar llamadas repetidas.
        """
        if not self.polygon_api_key:
            return []
        
        # Check cache
        if ticker in self._splits_cache:
            return self._splits_cache[ticker]
        
        try:
            response = await self.client.get(
                f"{self.POLYGON_URL}/v3/reference/splits",
                params={
                    "ticker": ticker,
                    "limit": 100,
                    "apiKey": self.polygon_api_key
                }
            )
            response.raise_for_status()
            data = response.json()
            
            splits = data.get("results", [])
            # Ordenar por fecha de ejecución descendente
            splits.sort(key=lambda x: x.get("execution_date", ""), reverse=True)
            
            self._splits_cache[ticker] = splits
            logger.info(f"Found {len(splits)} splits for {ticker}")
            return splits
            
        except Exception as e:
            logger.warning(f"Error getting splits for {ticker}: {e}")
            return []
    
    def _get_split_adjustment_factor(
        self, 
        splits: List[Dict], 
        period_end_date: str
    ) -> float:
        """
        Calcular el factor de ajuste acumulativo para una fecha.
        
        Para ajustar datos históricos al valor actual:
        - Multiplicar EPS por este factor
        - Dividir Shares por este factor
        
        Ejemplo: GOOGL split 20:1 en 2022-07-18
        - Datos de 2021 (antes del split): factor = 1/20 = 0.05
        - EPS 2021 original: $58.61 → Ajustado: $58.61 * 0.05 = $2.93
        """
        if not splits or not period_end_date:
            return 1.0
        
        factor = 1.0
        
        for split in splits:
            execution_date = split.get("execution_date", "")
            split_from = split.get("split_from", 1)
            split_to = split.get("split_to", 1)
            
            if not execution_date or split_from == 0:
                continue
            
            # Si el período es ANTES del split, aplicar el factor
            if period_end_date < execution_date:
                # split_to / split_from = factor de ajuste
                # Ej: 20:1 split → 20/1 = 20 → factor = 1/20 = 0.05
                split_factor = split_to / split_from
                factor *= (1.0 / split_factor)
        
        return factor
    
    def _adjust_for_splits(
        self,
        fields: List[Dict[str, Any]],
        splits: List[Dict[str, Any]],
        period_dates: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Ajustar campos de Shares y EPS por splits históricos.
        
        IMPORTANTE: Los filings SEC recientes "restatan" datos históricos post-split,
        pero los datos MUY antiguos pueden venir de filings pre-split y necesitar ajuste.
        
        Estrategia: Detectar valores que parecen pre-split comparando magnitudes.
        - Shares: Si un valor es ~20x menor → multiplicar por factor
        - EPS: Si un valor es ~20x mayor → dividir por factor
        """
        if not splits:
            return fields
        
        shares_keys = {'shares_basic', 'shares_diluted'}
        eps_keys = {'eps_basic', 'eps_diluted'}
        
        # Encontrar el split más grande (ej: GOOGL 20:1)
        max_split_factor = 1.0
        max_split_date = ""
        for split in splits:
            split_from = split.get("split_from", 1)
            split_to = split.get("split_to", 1)
            if split_from > 0:
                factor = split_to / split_from
                if factor > max_split_factor:
                    max_split_factor = factor
                    max_split_date = split.get("execution_date", "")
        
        if max_split_factor <= 1.5:  # No hay split significativo
            return fields
        
        adjusted_fields = []
        
        for field in fields:
            key = field['key']
            
            if key in shares_keys:
                values = field['values']
                
                # Encontrar la mediana de valores post-split (períodos recientes)
                post_split_values = []
                for i, v in enumerate(values):
                    if v is not None and i < len(period_dates):
                        date = period_dates[i]
                        if date and date > max_split_date:
                            post_split_values.append(v)
                
                if not post_split_values:
                    adjusted_fields.append(field)
                    continue
                
                median_post_split = sorted(post_split_values)[len(post_split_values)//2]
                
                # Ajustar valores que parecen pre-split (mucho menores)
                adjusted_values = []
                for i, v in enumerate(values):
                    if v is None:
                        adjusted_values.append(None)
                    elif v > 0 and median_post_split / v > max_split_factor * 0.5:
                        # Este valor parece pre-split, multiplicar por factor
                        adjusted_values.append(v * max_split_factor)
                    else:
                        adjusted_values.append(v)
                
                if adjusted_values != values:
                    logger.info(f"Split-adjusted {key}: detected pre-split values")
                
                adjusted_fields.append({
                    **field,
                    'values': adjusted_values,
                    'split_adjusted': adjusted_values != values
                })
            
            elif key in eps_keys:
                values = field['values']
                
                # Para EPS, usar método basado en fecha: si el período es ANTES del split,
                # los datos deberían estar ya ajustados en los filings recientes.
                # Pero verificamos comparando con valores post-split.
                
                # Obtener valores post-split para referencia
                post_split_values = []
                for i, v in enumerate(values):
                    if v is not None and i < len(period_dates):
                        date = period_dates[i]
                        if date and date > max_split_date:
                            post_split_values.append(v)
                
                if not post_split_values:
                    adjusted_fields.append(field)
                    continue
                
                median_post_split = sorted(post_split_values)[len(post_split_values)//2]
                
                # Ajustar TODOS los períodos pre-split que tengan valores > mediana * 1.5
                # (esto captura tanto los muy altos como los moderadamente altos)
                adjusted_values = []
                for i, v in enumerate(values):
                    if v is None:
                        adjusted_values.append(None)
                    elif i < len(period_dates):
                        date = period_dates[i]
                        # Si es período pre-split Y el valor es > 1.5x mediana, ajustar
                        if date and date < max_split_date and v > median_post_split * 1.5:
                            adjusted_values.append(v / max_split_factor)
                        else:
                            adjusted_values.append(v)
                    else:
                        adjusted_values.append(v)
                
                if adjusted_values != values:
                    logger.info(f"Split-adjusted {key}: detected pre-split values")
                
                adjusted_fields.append({
                    **field,
                    'values': adjusted_values,
                    'split_adjusted': adjusted_values != values
                })
            
            else:
                adjusted_fields.append(field)
        
        return adjusted_fields
    
    def _get_period_end_date(self, xbrl: Dict[str, Any], filed_at: str) -> str:
        """
        Obtener la fecha de fin del período del filing.
        Busca en los datos XBRL o usa la fecha de filing como fallback.
        """
        # Intentar obtener del balance sheet (tiene fechas de período)
        for section in ["BalanceSheets", "StatementsOfFinancialPosition"]:
            if section in xbrl:
                section_data = xbrl[section]
                if isinstance(section_data, dict):
                    # Buscar la primera fecha disponible
                    for key, value in section_data.items():
                        if isinstance(value, dict) and "period" in value:
                            period = value["period"]
                            if isinstance(period, dict) and "endDate" in period:
                                return period["endDate"]
        
        # Fallback: usar la fecha del filing (YYYY-MM-DD)
        if filed_at and len(filed_at) >= 10:
            return filed_at[:10]
        
        return filed_at[:4] + "-12-31" if filed_at else ""
    
    # =========================================================================
    # NORMALIZACIÓN SEMÁNTICA PROFESIONAL
    # Basado en conceptos contables estándar (US GAAP / IFRS)
    # =========================================================================
    
    def _camel_to_snake(self, name: str) -> str:
        """Convertir CamelCase a snake_case"""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def _classify_concept_category(self, field_name: str) -> Optional[str]:
        """
        Clasificar un campo XBRL en su categoría (income/balance/cashflow)
        basándose en el CONCEPTO del campo, NO en la sección donde aparece.
        
        Esto permite capturar campos como InterestExpense, EffectiveTaxRate,
        SharesOutstanding que pueden aparecer en secciones "Details".
        
        Returns: 'income', 'balance', 'cashflow', o None si no es relevante
        """
        name = self._camel_to_snake(field_name).lower()
        
        # Primero verificar si debe ser ignorado
        if self._should_skip_field(field_name):
            return None
        
        # Verificar contra patrones de cada categoría
        for pattern in self.CASHFLOW_PATTERNS:
            if re.search(pattern, name):
                return 'cashflow'
        
        for pattern in self.BALANCE_PATTERNS:
            if re.search(pattern, name):
                return 'balance'
        
        for pattern in self.INCOME_PATTERNS:
            if re.search(pattern, name):
                return 'income'
        
        # Si no matchea ningún patrón, intentar inferir de la sección
        # (esto es un fallback, el método principal es por concepto)
        return None
    
    def _should_skip_section(self, section_name: str) -> bool:
        """
        Determinar si una sección completa debe ser ignorada.
        """
        # Secciones explícitamente ignoradas
        for skip in self.SKIP_SECTIONS:
            if skip in section_name:
                return True
        
        # Secciones de tablas o notas (no tienen datos principales)
        name_lower = section_name.lower()
        if any(x in name_lower for x in ['table', 'note', 'schedule', 'policy', 'policies']):
            # Pero NO ignorar NetIncomePerShareSchedule (tiene shares outstanding)
            if 'earningspershare' in name_lower or 'netincomepershare' in name_lower:
                return False
            if 'incometax' in name_lower:  # Tiene effective tax rate
                return False
            if 'supplemental' in name_lower:  # Tiene interest income/expense
                return False
            return True
        
        return False
    
    def _detect_financial_concept(self, field_name: str) -> Tuple[str, str, int, str]:
        """
        Detectar el concepto financiero de un campo XBRL.
        Usa patrones basados en estándares contables (TDH compliant).
        
        Returns: (canonical_key, display_label, importance_score, data_type)
        
        data_type puede ser:
        - "monetary": Valores en moneda (USD)
        - "shares": Número de acciones
        - "perShare": Valores por acción (EPS)
        - "percent": Porcentajes
        - "ratio": Ratios financieros
        - "string": Texto
        """
        name = self._camel_to_snake(field_name).lower()
        
        # Patrones ordenados por especificidad (más específico primero)
        # Format: (pattern_regex, canonical_key, label, importance, data_type)
        # Soporta US GAAP e IFRS
        # data_type según TDH: monetary, shares, perShare, percent
        patterns = [
            # === INCOME STATEMENT (orden de aparición en P&L) ===
            
            # Revenue (US GAAP + IFRS)
            (r'^revenue$|^revenues$|^net_sales|^sales_revenue|revenue.*contract.*customer|^total_revenue', 
             'revenue', 'Revenue', 10000, 'monetary'),
            
            # Cost of Revenue / Cost of Sales (US GAAP + IFRS)
            # Incluye InformationTechnologyAndDataProcessing (crypto/fintech companies)
            (r'cost.*revenue|cost.*goods.*sold|cost.*sales|^cost_of_sales$|information.*technology.*data.*processing', 
             'cost_of_revenue', 'Cost of Revenue', 9500, 'monetary'),
            
            # Gross Profit
            (r'gross_profit', 
             'gross_profit', 'Gross Profit', 9400, 'monetary'),
            
            # R&D (US GAAP + IFRS)
            # Amazon: "Technology and Infrastructure/Content"
            (r'research.*development|r_and_d|technology.*infrastructure|technology.*content', 
             'rd_expenses', 'R&D Expenses', 9000, 'monetary'),
            
            # SG&A (US GAAP)
            (r'selling.*general.*admin|sg.*a', 
             'sga_expenses', 'SG&A Expenses', 8900, 'monetary'),
            
            # Selling & Marketing / Distribution Costs (US GAAP + IFRS)
            (r'selling.*marketing|sales.*marketing|selling_expense|distribution_cost|^marketing_expense$', 
             'sales_marketing', 'Sales & Marketing', 8850, 'monetary'),
            
            # Fulfillment (Amazon, e-commerce specific)
            (r'fulfillment.*expense|fulfillment.*cost', 
             'fulfillment_expense', 'Fulfillment Expense', 8840, 'monetary'),
            
            # Administrative Expense (IFRS specific)
            (r'^administrative_expense$|^general.*admin', 
             'ga_expenses', 'G&A Expenses', 8800, 'monetary'),
            
            # Operating Expenses
            (r'operating_expenses|costs.*expenses|total.*operating.*cost', 
             'operating_expenses', 'Operating Expenses', 8500, 'monetary'),
            
            # Restructuring Charges
            (r'restructuring.*charge|restructuring.*cost|merger.*restructur', 
             'restructuring_charges', 'Restructuring Charges', 8200, 'monetary'),
            
            # IMPORTANTE: Nonoperating ANTES de Operating
            # Campos como CryptoAssetGainLoss se clasifican automáticamente por la sección
            (r'^nonoperating|^other.*income|^other.*expense|other_nonoperating', 
             'other_income', 'Other Income/Expense', 7000, 'monetary'),
            
            # Operating Income / Profit from Operations (US GAAP + IFRS)
            (r'^operating_income|^income.*operations|profit_loss_from_operating|operating_profit', 
             'operating_income', 'Operating Income', 8000, 'monetary'),
            
            # Finance Income (IFRS specific)
            (r'^finance_income$|^interest_income|investment_income.*interest', 
             'interest_income', 'Interest Income', 7500, 'monetary'),
            
            # Finance Costs / Interest Expense (US GAAP + IFRS)
            (r'^finance_cost|^interest_expense|finance_expense', 
             'interest_expense', 'Interest Expense', 7400, 'monetary'),
            
            # Income Before Tax / Profit Before Tax (US GAAP + IFRS)
            (r'income.*before.*tax|profit.*loss.*before.*tax|income.*continuing.*operations.*before', 
             'income_before_tax', 'Income Before Tax', 6500, 'monetary'),
            
            # Income Tax (US GAAP + IFRS)
            (r'income.*tax.*expense|income.*tax.*benefit|provision.*income.*tax|^income_tax$', 
             'income_tax', 'Income Tax', 6000, 'monetary'),
            
            # Net Income / Profit or Loss (US GAAP + IFRS)
            (r'^net_income$|^net_income_loss$|^profit_loss$|^profit_loss_attributable', 
             'net_income', 'Net Income', 5500, 'monetary'),
            
            # EPS Basic (US GAAP + IFRS)
            (r'earnings.*share.*basic|eps.*basic|basic_earnings.*per.*share', 
             'eps_basic', 'EPS Basic', 5000, 'perShare'),
            
            # EPS Diluted (US GAAP + IFRS)
            (r'earnings.*share.*diluted|eps.*diluted|diluted_earnings.*per.*share', 
             'eps_diluted', 'EPS Diluted', 4900, 'perShare'),
            
            # Shares Basic
            (r'weighted.*shares.*basic|shares.*outstanding.*basic', 
             'shares_basic', 'Shares Basic', 4800, 'shares'),
            
            # Shares Diluted
            (r'weighted.*shares.*diluted|diluted.*shares', 
             'shares_diluted', 'Shares Diluted', 4700, 'shares'),
            
            # Depreciation (US GAAP + IFRS)
            (r'depreciation.*amortization|depreciation_depletion', 
             'depreciation', 'D&A', 4500, 'monetary'),
            
            # === BALANCE SHEET ===
            # Assets
            (r'^assets$|^total_assets', 'total_assets', 'Total Assets', 10000, 'monetary'),
            (r'assets_current|current_assets|^assets_current$', 'current_assets', 'Current Assets', 9500, 'monetary'),
            (r'cash.*equivalents|cash_and_cash|^cash$', 'cash', 'Cash & Equivalents', 9400, 'monetary'),
            (r'short.*term.*investments|marketable.*securities.*current|available.*sale.*securities.*current', 'st_investments', 'Short-term Investments', 9300, 'monetary'),
            (r'accounts.*receivable|receivables.*net|^receivables$|nontrade.*receivables', 'receivables', 'Accounts Receivable', 9200, 'monetary'),
            (r'inventory|inventories', 'inventory', 'Inventory', 9100, 'monetary'),
            (r'prepaid.*expense|other.*assets.*current', 'prepaid', 'Prepaid & Other', 9000, 'monetary'),
            (r'property.*plant.*equipment', 'ppe', 'PP&E', 8500, 'monetary'),
            (r'goodwill$', 'goodwill', 'Goodwill', 8400, 'monetary'),
            (r'intangible', 'intangibles', 'Intangible Assets', 8300, 'monetary'),
            (r'long.*term.*investments|investments.*noncurrent|available.*sale.*securities.*noncurrent', 'lt_investments', 'Long-term Investments', 8200, 'monetary'),
            
            # Liabilities
            (r'^liabilities$|^total_liabilities', 'total_liabilities', 'Total Liabilities', 7500, 'monetary'),
            (r'liabilities_current|current_liabilities|^liabilities_current$', 'current_liabilities', 'Current Liabilities', 7400, 'monetary'),
            (r'accounts.*payable|payable.*and.*accrued', 'accounts_payable', 'Accounts Payable', 7300, 'monetary'),
            (r'accrued.*liabilities|accrued.*expenses|accrued_income_taxes', 'accrued_liabilities', 'Accrued Liabilities', 7250, 'monetary'),
            (r'short.*term.*debt|short.*term.*borrowings|current.*portion.*long.*term|notes.*payable.*current', 'st_debt', 'Short-term Debt', 7200, 'monetary'),
            (r'long.*term.*debt|long.*term.*notes|convertible.*long.*term|notes.*payable.*noncurrent', 'lt_debt', 'Long-term Debt', 7000, 'monetary'),
            (r'contract.*customer.*liability|deferred.*revenue|unearned.*revenue', 'deferred_revenue', 'Deferred Revenue', 6900, 'monetary'),
            (r'operating.*lease.*liability', 'lease_liability', 'Lease Liabilities', 6800, 'monetary'),
            
            # Equity
            (r'stockholders.*equity|total.*equity|^equity$|liabilities_and_stockholders', 'total_equity', 'Total Equity', 6500, 'monetary'),
            (r'retained_earnings|accumulated_deficit', 'retained_earnings', 'Retained Earnings', 6400, 'monetary'),
            (r'common.*stock.*value|^common_stock$', 'common_stock', 'Common Stock', 6300, 'monetary'),
            (r'additional.*paid.*capital|paid.*capital', 'apic', 'Additional Paid-in Capital', 6200, 'monetary'),
            (r'treasury.*stock', 'treasury_stock', 'Treasury Stock', 6100, 'monetary'),
            (r'accumulated.*other.*comprehensive', 'aoci', 'AOCI', 6000, 'monetary'),
            
            # === CASH FLOW ===
            # Operating Activities
            (r'net.*cash.*operating|operating_activities|^cash.*flows.*operating', 'operating_cf', 'Operating Cash Flow', 10000, 'monetary'),
            (r'change.*receivables|increase.*decrease.*receivables', 'cf_receivables', 'Δ Receivables', 9500, 'monetary'),
            (r'change.*inventory|increase.*decrease.*inventory', 'cf_inventory', 'Δ Inventory', 9400, 'monetary'),
            (r'change.*payables|increase.*decrease.*payables|increase.*decrease.*accounts.*payable', 'cf_payables', 'Δ Payables', 9300, 'monetary'),
            (r'share.*based.*compensation|stock.*compensation|stock_based_compensation', 'stock_compensation', 'Stock Compensation', 9200, 'monetary'),
            
            # Investing Activities
            (r'net.*cash.*investing|investing_activities|^cash.*flows.*investing', 'investing_cf', 'Investing Cash Flow', 9000, 'monetary'),
            (r'capital.*expenditure|payments.*acquire.*property|purchase.*property.*plant|payments.*property', 'capex', 'CapEx', 8500, 'monetary'),
            (r'purchase.*investments|payments.*acquire.*investments', 'purchase_investments', 'Purchases of Investments', 8400, 'monetary'),
            (r'sale.*investments|proceeds.*sale.*investments|maturities.*investments', 'sale_investments', 'Sales of Investments', 8300, 'monetary'),
            (r'acquisitions|payments.*acquisitions|business.*combinations', 'acquisitions', 'Acquisitions', 8200, 'monetary'),
            
            # Financing Activities  
            (r'net.*cash.*financing|financing_activities|^cash.*flows.*financing', 'financing_cf', 'Financing Cash Flow', 8000, 'monetary'),
            (r'dividends.*paid|payments.*dividends', 'dividends_paid', 'Dividends Paid', 7500, 'monetary'),
            (r'repurchase.*common.*stock|stock.*repurchased|payments.*repurchase', 'stock_repurchased', 'Stock Repurchased', 7400, 'monetary'),
            (r'proceeds.*issuance.*common.*stock|proceeds.*stock|proceeds.*issuing.*shares', 'stock_issued', 'Stock Issued', 7300, 'monetary'),
            (r'proceeds.*debt|proceeds.*borrowings|proceeds.*long.*term', 'debt_issued', 'Debt Issued', 7200, 'monetary'),
            (r'repayments.*debt|payments.*long.*term|repayments.*borrowings', 'debt_repaid', 'Debt Repaid', 7100, 'monetary'),
        ]
        
        # Buscar el primer patrón que coincida
        for pattern, key, label, importance, dtype in patterns:
            if re.search(pattern, name):
                return (key, label, importance, dtype)
        
        # Si no hay match en CORE patterns, usar label oficial de FASB
        # El nombre original del campo está en CamelCase, buscar directamente
        original_name = ''.join(w.capitalize() for w in name.split('_'))
        
        if original_name in FASB_LABELS:
            fasb_label = FASB_LABELS[original_name]
            # Limpiar label (quitar paréntesis innecesarios)
            clean_label = fasb_label.replace(' (Loss)', '').replace(' Attributable to Parent', '')
            # Obtener data type de FASB
            fasb_type = FASB_DATA_TYPES.get(original_name, 'monetary')
            return (name, clean_label, 100, fasb_type)
        
        # Último fallback: generar label del nombre
        words = name.split('_')[:4]
        auto_label = ' '.join(w.capitalize() for w in words if w not in {'and', 'the', 'of', 'to', 'in'})
        
        return (name, auto_label, 50, 'monetary')  # Asumir monetary por defecto
    
    def _should_skip_field(self, field_name: str) -> bool:
        """
        Determinar si un campo debe ser ignorado.
        Ignora campos secundarios que no aportan información principal.
        """
        name = field_name.lower()
        
        # Patrones de campos a ignorar
        skip_patterns = [
            r'comprehensive_income',  # OCI es secundario
            r'reclassification',
            r'adjustment',
            r'discontinued',
            r'preferred.*dividends',
            r'noncontrolling',
            r'segment',  # Datos por segmento
            r'_hedge_',
            r'_aoci_',
            r'unrealized_holding',
            r'accumulated_depreciation',  # Depreciación acumulada (no gasto del año)
            r'accumulated_depletion',
            r'accumulated_amortization',
        ]
        
        return any(re.search(p, name) for p in skip_patterns)
    
    # =========================================================================
    # BÚSQUEDA DE FILINGS
    # =========================================================================
    
    async def get_cik(self, ticker: str) -> Optional[str]:
        """Obtener el CIK de una empresa"""
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
            logger.error(f"Error getting CIK for {ticker}: {e}")
            return None
    
    async def get_filings(
        self, 
        ticker: str, 
        form_type: str = "10-K",
        limit: int = 10,
        cik: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtener filings por CIK (preferido) o ticker.
        
        IMPORTANTE: Usar CIK garantiza que solo obtenemos filings de la empresa
        actual, evitando mezclar datos de empresas que reutilizaron el mismo ticker.
        
        Args:
            ticker: Símbolo del ticker (usado como fallback y para logging)
            form_type: Tipo de formulario ("10-K", "10-Q", "20-F", "6-K")
            limit: Número máximo de filings
            cik: CIK de la empresa (opcional pero RECOMENDADO)
        """
        try:
            # ESTRATEGIA:
            # 1. Si tenemos CIK → buscar SOLO por CIK (más preciso)
            # 2. Si no tenemos CIK → buscar por ticker y extraer CIK del primer resultado
            
            if cik:
                # Normalizar CIK: SEC-API espera sin ceros a la izquierda (1751008 no 0001751008)
                normalized_cik = cik.lstrip('0') or '0'
                
                # Búsqueda PRECISA por CIK (evita tickers reutilizados como APP)
                logger.info(f"[{ticker}] Searching by CIK {normalized_cik} for {form_type}")
                response = await self.client.post(
                    f"{self.BASE_URL}?token={self.api_key}",
                    json={
                        "query": {"query_string": {"query": f'cik:{normalized_cik} AND formType:"{form_type}"'}},
                        "from": "0",
                        "size": str(limit + 5),
                        "sort": [{"filedAt": {"order": "desc"}}]
                    }
                )
                response.raise_for_status()
                filings = response.json().get("filings", [])
                return filings[:limit]
            
            # Fallback: buscar por ticker (puede mezclar empresas con mismo ticker)
            logger.warning(f"[{ticker}] No CIK provided, falling back to ticker search (may include old company data)")
            response = await self.client.post(
                f"{self.BASE_URL}?token={self.api_key}",
                json={
                    "query": {"query_string": {"query": f'ticker:{ticker} AND formType:"{form_type}"'}},
                    "from": "0",
                    "size": str(limit),
                    "sort": [{"filedAt": {"order": "desc"}}]
                }
            )
            response.raise_for_status()
            data = response.json()
            filings = data.get("filings", [])
            
            # Si tenemos filings, extraer CIK del más reciente para búsqueda adicional
            if filings and len(filings) < limit * 0.8:
                extracted_cik = filings[0].get("cik")
                if extracted_cik:
                    logger.info(f"[{ticker}] Extracted CIK {extracted_cik}, expanding search")
                    response = await self.client.post(
                        f"{self.BASE_URL}?token={self.api_key}",
                        json={
                            "query": {"query_string": {"query": f'cik:{extracted_cik} AND formType:"{form_type}"'}},
                            "from": "0",
                            "size": str(limit + 5),
                            "sort": [{"filedAt": {"order": "desc"}}]
                        }
                    )
                    response.raise_for_status()
                    cik_filings = response.json().get("filings", [])
                    if len(cik_filings) > len(filings):
                        filings = cik_filings
            
            return filings[:limit]
            
        except Exception as e:
            logger.error(f"Error getting filings for {ticker}: {e}")
            return []
    
    async def get_xbrl_data(self, accession_no: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Obtener datos XBRL con retry"""
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
    # EXTRACCIÓN SIMBIÓTICA
    # =========================================================================
    
    def _extract_all_fields_from_section(
        self, 
        xbrl_data: Dict, 
        section_name: str,
        fiscal_year: str
    ) -> Dict[str, Tuple[float, str]]:
        """
        Extraer todos los campos de una sección XBRL.
        Soporta tanto US GAAP (valores consolidados) como IFRS (valores segmentados).
        Returns: {normalized_name: (value, original_name)}
        """
        section_data = xbrl_data.get(section_name, {})
        results = {}
        
        for field_name, values in section_data.items():
            if not isinstance(values, list) or not values:
                continue
            
            # Prioridad 1: Valores consolidados (sin segmento) - US GAAP style
            consolidated = [
                item for item in values 
                if isinstance(item, dict) and "segment" not in item and item.get("value") is not None
            ]
            
            # Prioridad 2: Si no hay consolidados, usar valores segmentados - IFRS style
            # Sumar segmentos de producto/servicio (no geográficos) del mismo período
            if not consolidated:
                period_sums = {}  # {end_date: sum of product segments}
                period_max = {}   # {end_date: max value as fallback}
                
                for item in values:
                    if not isinstance(item, dict) or item.get("value") is None:
                        continue
                    period = item.get("period", {})
                    end_date = period.get("endDate") or period.get("instant", "")
                    if not end_date:
                        continue
                    
                    try:
                        val = float(item["value"])
                    except (ValueError, TypeError):
                        continue
                    
                    # Track max value as fallback
                    if end_date not in period_max or abs(val) > abs(period_max[end_date]):
                        period_max[end_date] = val
                    
                    # Check if this is a product/service segment (not geographic)
                    segment = item.get("segment", {})
                    segment_dim = segment.get("dimension", "") if isinstance(segment, dict) else ""
                    segment_val = segment.get("value", "") if isinstance(segment, dict) else ""
                    
                    # Product segments typically have "Member" suffix and product-related dimensions
                    is_product_segment = (
                        "ProductsAndServices" in segment_dim or
                        "Revenue" in segment_val or
                        "Member" in segment_val and "country:" not in segment_val and "srt:" not in segment_val
                    )
                    
                    if is_product_segment:
                        if end_date not in period_sums:
                            period_sums[end_date] = 0
                        period_sums[end_date] += val
                
                # Use sum if available, otherwise use max
                period_values = {}
                for end_date in set(list(period_sums.keys()) + list(period_max.keys())):
                    if end_date in period_sums and period_sums[end_date] != 0:
                        period_values[end_date] = period_sums[end_date]
                    elif end_date in period_max:
                        period_values[end_date] = period_max[end_date]
                
                # Convertir a formato consolidado
                consolidated = [
                    {"value": str(v), "period": {"endDate": d}}
                    for d, v in period_values.items()
                ]
            
            if not consolidated:
                continue
            
            # Buscar valor del año fiscal
            best_value = None
            best_date = ""
            
            for item in consolidated:
                period = item.get("period", {})
                end_date = period.get("endDate") or period.get("instant", "")
                
                # Coincidir por año fiscal (4 dígitos)
                if end_date and end_date[:4] == str(fiscal_year)[:4]:
                    try:
                        best_value = float(item["value"])
                        break
                    except (ValueError, TypeError):
                        continue
                
                # Fallback: tomar el más reciente
                if end_date > best_date:
                    try:
                        best_value = float(item["value"])
                        best_date = end_date
                    except (ValueError, TypeError):
                        continue
            
            if best_value is not None:
                normalized = self._camel_to_snake(field_name)
                results[normalized] = (best_value, field_name)
        
        return results
    
    def _consolidate_fields_semantically(
        self,
        all_periods_data: List[Dict[str, Tuple[float, str]]],
        fiscal_years: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Consolidar campos semánticamente relacionados usando detección de conceptos financieros.
        """
        # Paso 1: Agrupar por concepto financiero detectado
        concept_groups: Dict[str, Dict] = {}
        
        for period_idx, period_data in enumerate(all_periods_data):
            for normalized_name, (value, original) in period_data.items():
                # Ignorar campos secundarios
                if self._should_skip_field(normalized_name):
                    continue
                
                # Detectar concepto financiero (ahora incluye data_type)
                canonical_key, label, importance, data_type = self._detect_financial_concept(normalized_name)
                
                # Crear grupo si no existe
                if canonical_key not in concept_groups:
                    concept_groups[canonical_key] = {
                        'key': canonical_key,
                        'label': label,
                        'importance': importance,
                        'data_type': data_type,  # TDH: monetaryItemType, sharesItemType, etc.
                        'values': [None] * len(all_periods_data),
                        'sources': []
                    }
                
                # Añadir valor (solo si no hay uno ya)
                if concept_groups[canonical_key]['values'][period_idx] is None:
                    concept_groups[canonical_key]['values'][period_idx] = value
                
                # Registrar fuente
                if original not in concept_groups[canonical_key]['sources']:
                    concept_groups[canonical_key]['sources'].append(original)
        
        # Paso 2: Convertir a lista y ordenar por importancia
        consolidated_fields = []
        
        for concept_key, group in concept_groups.items():
            # Solo incluir si tiene al menos un valor
            if any(v is not None for v in group['values']):
                # Obtener balance de FASB para el primer source field
                balance = None
                for src in group['sources']:
                    if src in FASB_BALANCE:
                        balance = FASB_BALANCE[src]
                        break
                
                field_data = {
                    'key': group['key'],
                    'label': group['label'],
                    'values': group['values'],
                    'importance': group['importance'],
                    'data_type': group.get('data_type', 'monetary'),  # TDH compliant
                    'source_fields': group['sources']
                }
                
                # Solo añadir balance si lo encontramos (no hardcodear)
                if balance:
                    field_data['balance'] = balance  # "debit" o "credit"
                
                consolidated_fields.append(field_data)
        
        # Paso 3: Añadir campos calculados
        consolidated_fields = self._add_calculated_fields(consolidated_fields, len(all_periods_data))
        
        # Paso 4: Ordenar por importancia
        consolidated_fields.sort(key=lambda x: x['importance'], reverse=True)
        
        return consolidated_fields
    
    # Patrones para clasificar gastos (IFRS "por naturaleza" → "por función")
    # Gastos DIRECTOS (Cost of Revenue): relacionados con producción/ventas
    DIRECT_COST_PATTERNS = [
        r'energy.*transmission', r'energy.*cost', r'electricity',
        r'site.*expense', r'hosting', r'data.*center',
        r'cost.*sales', r'cost.*goods', r'cost.*revenue',
        r'raw.*material', r'direct.*cost', r'production.*cost',
        r'mining.*cost', r'fuel', r'utilities',
    ]
    
    # Gastos OPERATIVOS (OpEx): SG&A y similares
    OPEX_PATTERNS = [
        r'employee.*benefit', r'salaries', r'wages', r'compensation',
        r'share.*based.*payment', r'stock.*compensation',
        r'professional.*fee', r'legal.*fee', r'consulting',
        r'administrative', r'general.*admin', r'office',
        r'selling.*expense', r'marketing', r'advertising',
        r'research.*development', r'r.*d',
        r'other.*expense', r'miscellaneous',
    ]
    
    def _classify_expense(self, field_key: str) -> str:
        """
        Clasificar un gasto como 'direct' (Cost of Revenue) u 'opex' (Operating Expense).
        """
        key_lower = field_key.lower()
        
        for pattern in self.DIRECT_COST_PATTERNS:
            if re.search(pattern, key_lower):
                return 'direct'
        
        for pattern in self.OPEX_PATTERNS:
            if re.search(pattern, key_lower):
                return 'opex'
        
        # Por defecto, gastos sin clasificar van a opex
        return 'opex'
    
    def _add_calculated_fields(self, fields: List[Dict], num_periods: int) -> List[Dict]:
        """
        Añadir campos calculados si no existen.
        
        Para empresas IFRS "por naturaleza" (sin Gross Profit/Cost of Revenue):
        1. Clasificar gastos como directos vs operativos
        2. Cost of Revenue = suma de gastos directos
        3. Gross Profit = Revenue - Cost of Revenue
        4. Operating Expenses = suma de gastos operativos
        5. Operating Income = Gross Profit - Operating Expenses
        6. EBITDA = Operating Income + D&A
        """
        field_map = {f['key']: f for f in fields}
        
        # =========================================================================
        # PASO 1: Calcular Cost of Revenue si no existe (IFRS por naturaleza)
        # =========================================================================
        # Verificar si cost_of_revenue tiene valores null que necesitan calcularse
        existing_cor = field_map.get('cost_of_revenue')
        cor_has_nulls = existing_cor and any(v is None for v in existing_cor['values'])
        needs_cor_calc = ('cost_of_revenue' not in field_map) or cor_has_nulls
        
        if needs_cor_calc and 'revenue' in field_map:
            direct_cost_fields = []
            opex_fields = []
            
            # Clasificar todos los campos de gastos
            for f in fields:
                key = f['key']
                # Solo campos que parecen gastos (valores negativos o nombres de gastos)
                is_expense = any(x in key for x in ['expense', 'cost', 'charge', 'fee', 'payment'])
                is_excluded = key in ['interest_expense', 'income_tax', 'finance_income_cost', 'interest_revenue_expense']
                
                if is_expense and not is_excluded:
                    classification = self._classify_expense(key)
                    if classification == 'direct':
                        direct_cost_fields.append(f)
                    else:
                        opex_fields.append(f)
            
            # Calcular Cost of Revenue = suma de gastos directos
            if direct_cost_fields:
                # Calcular valores desde gastos directos
                calculated_cor = [0.0] * num_periods
                source_fields = []
                
                for f in direct_cost_fields:
                    source_fields.append(f['key'])
                    for i, v in enumerate(f['values']):
                        if i < num_periods and v is not None:
                            calculated_cor[i] += abs(v)
                
                # Si ya existe cost_of_revenue, solo rellenar los nulls
                if existing_cor:
                    merged_cor = []
                    for i in range(num_periods):
                        existing_val = existing_cor['values'][i] if i < len(existing_cor['values']) else None
                        calc_val = calculated_cor[i] if i < len(calculated_cor) else 0
                        # Usar existente si no es null, sino usar calculado
                        if existing_val is not None:
                            merged_cor.append(existing_val)
                        elif calc_val > 0:
                            merged_cor.append(calc_val)
                        else:
                            merged_cor.append(None)
                    existing_cor['values'] = merged_cor
                    existing_cor['source_fields'] = existing_cor.get('source_fields', []) + source_fields
                    existing_cor['calculated'] = True
                    logger.info(f"Merged Cost of Revenue with calculated values from: {source_fields}")
                else:
                    # Crear nuevo campo
                    if any(v > 0 for v in calculated_cor):
                        fields.append({
                            'key': 'cost_of_revenue',
                            'label': 'Cost of Revenue',
                            'values': calculated_cor,
                            'importance': 9500,
                            'source_fields': source_fields,
                            'calculated': True
                        })
                        field_map['cost_of_revenue'] = fields[-1]
                        logger.info(f"Created Cost of Revenue from: {source_fields}")
            
            # Calcular Operating Expenses = suma de gastos operativos
            if opex_fields and 'operating_expenses' not in field_map:
                operating_expenses = [0.0] * num_periods
                source_fields = []
                
                for f in opex_fields:
                    source_fields.append(f['key'])
                    for i, v in enumerate(f['values']):
                        if i < num_periods and v is not None:
                            operating_expenses[i] += abs(v)
                
                if any(v > 0 for v in operating_expenses):
                    fields.append({
                        'key': 'operating_expenses',
                        'label': 'Operating Expenses',
                        'values': operating_expenses,
                        'importance': 8500,
                        'source_fields': source_fields,
                        'calculated': True
                    })
                    field_map['operating_expenses'] = fields[-1]
        
        # =========================================================================
        # PASO 2: Calcular Gross Profit = Revenue - Cost of Revenue
        # =========================================================================
        existing_gp = field_map.get('gross_profit')
        gp_has_nulls = existing_gp and any(v is None for v in existing_gp['values'])
        needs_gp_calc = ('gross_profit' not in field_map) or gp_has_nulls
        
        if needs_gp_calc and 'revenue' in field_map and 'cost_of_revenue' in field_map:
            revenue = field_map['revenue']['values']
            cost = field_map['cost_of_revenue']['values']
            calculated_gp = []
            
            for i in range(num_periods):
                r = revenue[i] if i < len(revenue) else None
                c = cost[i] if i < len(cost) else None
                if r is not None and c is not None:
                    calculated_gp.append(r - c)
                else:
                    calculated_gp.append(None)
            
            if existing_gp:
                # Merge: usar existente si no es null, sino usar calculado
                merged_gp = []
                for i in range(num_periods):
                    existing_val = existing_gp['values'][i] if i < len(existing_gp['values']) else None
                    calc_val = calculated_gp[i] if i < len(calculated_gp) else None
                    merged_gp.append(existing_val if existing_val is not None else calc_val)
                existing_gp['values'] = merged_gp
                existing_gp['calculated'] = True
            else:
                if any(v is not None for v in calculated_gp):
                    fields.append({
                        'key': 'gross_profit',
                        'label': 'Gross Profit',
                        'values': calculated_gp,
                        'importance': 9400,
                        'source_fields': ['revenue', 'cost_of_revenue'],
                        'calculated': True
                    })
                    field_map['gross_profit'] = fields[-1]
        
        # =========================================================================
        # PASO 3: Calcular Operating Income SOLO si no existe o tiene nulls
        # =========================================================================
        # NO sobrescribir valores del XBRL - solo rellenar nulls o crear si no existe
        existing_oi = field_map.get('operating_income')
        oi_has_nulls = existing_oi and any(v is None for v in existing_oi['values'])
        needs_oi_calc = ('operating_income' not in field_map) or oi_has_nulls
        
        if needs_oi_calc and 'gross_profit' in field_map and 'operating_expenses' in field_map:
            gross = field_map['gross_profit']['values']
            opex = field_map['operating_expenses']['values']
            calculated_oi = []
            
            for i in range(num_periods):
                g = gross[i] if i < len(gross) else None
                o = opex[i] if i < len(opex) else None
                if g is not None and o is not None:
                    calculated_oi.append(g - o)
                else:
                    calculated_oi.append(None)
            
            if existing_oi:
                # Solo rellenar nulls, no sobrescribir valores existentes
                merged_oi = []
                for i in range(num_periods):
                    existing_val = existing_oi['values'][i] if i < len(existing_oi['values']) else None
                    calc_val = calculated_oi[i] if i < len(calculated_oi) else None
                    merged_oi.append(existing_val if existing_val is not None else calc_val)
                existing_oi['values'] = merged_oi
            else:
                if any(v is not None for v in calculated_oi):
                    fields.append({
                        'key': 'operating_income',
                        'label': 'Operating Income',
                        'values': calculated_oi,
                        'importance': 8000,
                        'source_fields': ['gross_profit', 'operating_expenses'],
                        'calculated': True
                    })
                    field_map['operating_income'] = fields[-1]
        
        # =========================================================================
        # PASO 4: Calcular Income Before Tax
        # =========================================================================
        if 'income_before_tax' not in field_map and 'net_income' in field_map and 'income_tax' in field_map:
            net_income = field_map['net_income']['values']
            tax = field_map['income_tax']['values']
            income_before_tax = []
            
            for i in range(num_periods):
                ni = net_income[i] if i < len(net_income) else None
                t = tax[i] if i < len(tax) else None
                if ni is not None and t is not None:
                    income_before_tax.append(ni + abs(t))
                else:
                    income_before_tax.append(None)
            
            if any(v is not None for v in income_before_tax):
                fields.append({
                    'key': 'income_before_tax',
                    'label': 'Income Before Tax',
                    'values': income_before_tax,
                    'importance': 6500,
                    'source_fields': ['net_income', 'income_tax'],
                    'calculated': True
                })
                field_map['income_before_tax'] = fields[-1]
        
        # =========================================================================
        # PASO 5: Calcular EBITDA = Operating Income + D&A
        # =========================================================================
        if 'operating_income' in field_map:
            op_income = field_map['operating_income']['values']
            
            # Combinar depreciation de múltiples campos (10-K usa un nombre, 20-F usa otro)
            da_fields = [
                field_map.get('depreciation'),
                field_map.get('depreciation_expense'),
                field_map.get('depreciation_amortization'),
            ]
            
            # Merge: para cada período, usar el primer valor no-null de cualquier campo
            da = [0] * num_periods
            for i in range(num_periods):
                for da_field in da_fields:
                    if da_field and i < len(da_field['values']) and da_field['values'][i] is not None:
                        da[i] = da_field['values'][i]
                        break
            
            ebitda = []
            for i in range(num_periods):
                oi = op_income[i] if i < len(op_income) else None
                d = da[i] if da[i] else 0
                if oi is not None:
                    ebitda.append(oi + abs(d))
                else:
                    ebitda.append(None)
            
            if any(v is not None for v in ebitda):
                # Actualizar o añadir EBITDA
                if 'ebitda' in field_map:
                    field_map['ebitda']['values'] = ebitda
                    field_map['ebitda']['calculated'] = True
                else:
                    fields.append({
                        'key': 'ebitda',
                        'label': 'EBITDA',
                        'values': ebitda,
                        'importance': 4600,
                        'source_fields': ['operating_income', 'depreciation'],
                        'calculated': True
                    })
        
        return fields
    
    def _recalculate_ebitda_with_cashflow(
        self, 
        income_fields: List[Dict], 
        cashflow_fields: List[Dict],
        num_periods: int
    ) -> List[Dict]:
        """
        Recalcular EBITDA usando D&A de Cash Flow Statement.
        Muchas empresas reportan D&A solo en Cash Flow (como ajuste al Net Income),
        no en el Income Statement.
        
        EBITDA = Operating Income + D&A
        """
        # Crear mapas para acceso rápido
        income_map = {f['key']: f for f in income_fields}
        cashflow_map = {f['key']: f for f in cashflow_fields}
        
        # Obtener Operating Income
        op_income_field = income_map.get('operating_income')
        if not op_income_field:
            return income_fields
        
        op_income = op_income_field['values']
        
        # Buscar D&A en múltiples fuentes (primero Income Statement, luego Cash Flow)
        # Incluir variantes de nombres usados por diferentes empresas
        da_sources = [
            ('income', 'depreciation'),
            ('income', 'depreciation_expense'),
            ('income', 'depreciation_amortization'),
            ('income', 'depreciation_and_impairment_on_disposition_of_property_and_equipment'),
            ('cashflow', 'depreciation'),
            ('cashflow', 'depreciation_expense'),
            ('cashflow', 'depreciation_amortization'),
            ('cashflow', 'depreciation_and_impairment_on_disposition_of_property_and_equipment'),
        ]
        
        # Combinar D&A de todas las fuentes
        da_values = [0] * num_periods
        da_source_found = None
        
        for source_type, field_key in da_sources:
            source_map = income_map if source_type == 'income' else cashflow_map
            da_field = source_map.get(field_key)
            
            if da_field and any(v is not None and v != 0 for v in da_field['values']):
                # Merge: usar valores de esta fuente donde no tengamos ya
                for i in range(min(num_periods, len(da_field['values']))):
                    if da_values[i] == 0 and da_field['values'][i] is not None:
                        da_values[i] = da_field['values'][i]
                        da_source_found = f"{source_type}:{field_key}"
        
        # Calcular EBITDA = Operating Income + |D&A|
        ebitda_values = []
        for i in range(num_periods):
            oi = op_income[i] if i < len(op_income) else None
            da = abs(da_values[i]) if da_values[i] else 0
            
            if oi is not None:
                ebitda_values.append(oi + da)
            else:
                ebitda_values.append(None)
        
        # Actualizar o añadir EBITDA en income_fields
        if 'ebitda' in income_map:
            # Actualizar valores existentes
            income_map['ebitda']['values'] = ebitda_values
            income_map['ebitda']['calculated'] = True
            if da_source_found:
                income_map['ebitda']['source_fields'] = ['operating_income', da_source_found]
        else:
            # Añadir nuevo campo EBITDA
            income_fields.append({
                'key': 'ebitda',
                'label': 'EBITDA',
                'values': ebitda_values,
                'importance': 4600,
                'source_fields': ['operating_income', da_source_found or 'depreciation'],
                'calculated': True
            })
        
        return income_fields
    
    def _add_calculated_metrics(
        self,
        income_fields: List[Dict],
        cashflow_fields: List[Dict],
        num_periods: int
    ) -> List[Dict]:
        """
        Añadir métricas calculadas como TIKR:
        1. % Margins (Gross, Operating, Net, EBITDA)
        2. % YoY para métricas clave
        3. Dividend per Share
        """
        income_map = {f['key']: f for f in income_fields}
        cashflow_map = {f['key']: f for f in cashflow_fields}
        
        # Obtener valores base para cálculos
        revenue = income_map.get('revenue', {}).get('values', [])
        gross_profit = income_map.get('gross_profit', {}).get('values', [])
        operating_income = income_map.get('operating_income', {}).get('values', [])
        net_income = income_map.get('net_income', {}).get('values', [])
        ebitda = income_map.get('ebitda', {}).get('values', [])
        shares_basic = income_map.get('shares_basic', {}).get('values', [])
        dividends_paid = cashflow_map.get('dividends_paid', {}).get('values', [])
        
        # =========================================================================
        # 1. MÁRGENES (% del Revenue)
        # =========================================================================
        def calc_margin(values: List, revenue: List) -> List:
            """Calcular margen como porcentaje del revenue."""
            margin = []
            for i in range(num_periods):
                val = values[i] if i < len(values) else None
                rev = revenue[i] if i < len(revenue) else None
                if val is not None and rev is not None and rev != 0:
                    margin.append(round(val / rev, 4))  # 4 decimales (0.5432 = 54.32%)
                else:
                    margin.append(None)
            return margin
        
        # Gross Margin
        if gross_profit and revenue:
            gross_margin = calc_margin(gross_profit, revenue)
            if any(v is not None for v in gross_margin):
                income_fields.append({
                    'key': 'gross_margin',
                    'label': 'Gross Margin %',
                    'values': gross_margin,
                    'importance': 9350,
                    'data_type': 'percent',
                    'source_fields': ['gross_profit', 'revenue'],
                    'calculated': True
                })
        
        # Operating Margin
        if operating_income and revenue:
            operating_margin = calc_margin(operating_income, revenue)
            if any(v is not None for v in operating_margin):
                income_fields.append({
                    'key': 'operating_margin',
                    'label': 'Operating Margin %',
                    'values': operating_margin,
                    'importance': 7950,
                    'data_type': 'percent',
                    'source_fields': ['operating_income', 'revenue'],
                    'calculated': True
                })
        
        # Net Margin
        if net_income and revenue:
            net_margin = calc_margin(net_income, revenue)
            if any(v is not None for v in net_margin):
                income_fields.append({
                    'key': 'net_margin',
                    'label': 'Net Margin %',
                    'values': net_margin,
                    'importance': 5450,
                    'data_type': 'percent',
                    'source_fields': ['net_income', 'revenue'],
                    'calculated': True
                })
        
        # EBITDA Margin
        if ebitda and revenue:
            ebitda_margin = calc_margin(ebitda, revenue)
            if any(v is not None for v in ebitda_margin):
                income_fields.append({
                    'key': 'ebitda_margin',
                    'label': 'EBITDA Margin %',
                    'values': ebitda_margin,
                    'importance': 4550,
                    'data_type': 'percent',
                    'source_fields': ['ebitda', 'revenue'],
                    'calculated': True
                })
        
        # =========================================================================
        # 2. % YoY (Cambio interanual)
        # =========================================================================
        def calc_yoy(values: List) -> List:
            """Calcular cambio YoY. Los períodos están en orden descendente (2024, 2023, 2022...)."""
            yoy = [None]  # Primer período no tiene YoY
            for i in range(1, num_periods):
                curr = values[i] if i < len(values) else None
                prev = values[i - 1] if (i - 1) < len(values) else None  # El período anterior cronológicamente
                # En nuestro array, i-1 es más reciente, i es más antiguo
                # YoY = (actual - anterior) / anterior
                # Pero el orden es invertido: values[0] = 2024, values[1] = 2023
                # YoY de 2024 = (2024 - 2023) / 2023
                if curr is not None and prev is not None and curr != 0:
                    yoy.append(round((prev - curr) / abs(curr), 4))
                else:
                    yoy.append(None)
            return yoy
        
        # YoY para Revenue
        if revenue and len(revenue) > 1:
            revenue_yoy = calc_yoy(revenue)
            if any(v is not None for v in revenue_yoy):
                income_fields.append({
                    'key': 'revenue_yoy',
                    'label': 'Revenue % YoY',
                    'values': revenue_yoy,
                    'importance': 9900,
                    'data_type': 'percent',
                    'source_fields': ['revenue'],
                    'calculated': True
                })
        
        # YoY para Net Income
        if net_income and len(net_income) > 1:
            net_income_yoy = calc_yoy(net_income)
            if any(v is not None for v in net_income_yoy):
                income_fields.append({
                    'key': 'net_income_yoy',
                    'label': 'Net Income % YoY',
                    'values': net_income_yoy,
                    'importance': 5400,
                    'data_type': 'percent',
                    'source_fields': ['net_income'],
                    'calculated': True
                })
        
        # YoY para EPS
        eps = income_map.get('eps_diluted', {}).get('values', [])
        if eps and len(eps) > 1:
            eps_yoy = calc_yoy(eps)
            if any(v is not None for v in eps_yoy):
                income_fields.append({
                    'key': 'eps_yoy',
                    'label': 'EPS % YoY',
                    'values': eps_yoy,
                    'importance': 4850,
                    'data_type': 'percent',
                    'source_fields': ['eps_diluted'],
                    'calculated': True
                })
        
        # =========================================================================
        # 3. DIVIDEND PER SHARE
        # =========================================================================
        if dividends_paid and shares_basic:
            dps = []
            for i in range(num_periods):
                div = dividends_paid[i] if i < len(dividends_paid) else None
                shares = shares_basic[i] if i < len(shares_basic) else None
                if div is not None and shares is not None and shares > 0:
                    # dividends_paid suele ser positivo o negativo dependiendo del filing
                    dps.append(round(abs(div) / shares, 4))
                else:
                    dps.append(None)
            
            if any(v is not None and v > 0 for v in dps):
                income_fields.append({
                    'key': 'dividend_per_share',
                    'label': 'Dividend per Share',
                    'values': dps,
                    'importance': 4750,
                    'data_type': 'perShare',
                    'source_fields': ['dividends_paid', 'shares_basic'],
                    'calculated': True
                })
        
        return income_fields
    
    def _add_structure_metadata(
        self,
        fields: List[Dict],
        statement_type: str  # 'income', 'balance', 'cashflow'
    ) -> List[Dict]:
        """
        Añadir metadata de estructura jerárquica a los campos para renderizado profesional.
        
        Añade: section, display_order, indent_level, is_subtotal
        """
        if statement_type == 'income':
            structure = self.INCOME_STATEMENT_STRUCTURE
        elif statement_type == 'balance':
            structure = self.BALANCE_SHEET_STRUCTURE
        elif statement_type == 'cashflow':
            structure = self.CASH_FLOW_STRUCTURE
        else:
            return fields
        
        enriched = []
        for field in fields:
            key = field.get('key', '')
            field_copy = field.copy()
            
            if key in structure:
                meta = structure[key]
                field_copy['section'] = meta['section']
                field_copy['display_order'] = meta['order']
                field_copy['indent_level'] = meta['indent']
                field_copy['is_subtotal'] = meta['is_subtotal']
            else:
                # Campos no mapeados van al final, en sección "Other"
                field_copy['section'] = 'Other'
                field_copy['display_order'] = 9000
                field_copy['indent_level'] = 0
                field_copy['is_subtotal'] = False
            
            enriched.append(field_copy)
        
        # Ordenar por display_order
        enriched.sort(key=lambda x: x.get('display_order', 9999))
        
        return enriched
    
    # =========================================================================
    # ESTRUCTURA JERÁRQUICA DEL INCOME STATEMENT (estilo institucional)
    # Cada campo tiene: (orden, nivel_indentación, es_subtotal)
    # =========================================================================
    INCOME_STATEMENT_STRUCTURE = {
        # === SECCIÓN: REVENUE ===
        'revenue':           {'section': 'Revenue',           'order': 100, 'indent': 0, 'is_subtotal': False},
        'revenue_yoy':       {'section': 'Revenue',           'order': 101, 'indent': 1, 'is_subtotal': False},
        
        # === SECCIÓN: COST & GROSS PROFIT ===
        'cost_of_revenue':   {'section': 'Cost & Gross Profit', 'order': 200, 'indent': 0, 'is_subtotal': False},
        'gross_profit':      {'section': 'Cost & Gross Profit', 'order': 210, 'indent': 0, 'is_subtotal': True},
        'gross_margin':      {'section': 'Cost & Gross Profit', 'order': 211, 'indent': 1, 'is_subtotal': False},
        
        # === SECCIÓN: OPERATING EXPENSES ===
        'rd_expenses':       {'section': 'Operating Expenses', 'order': 300, 'indent': 1, 'is_subtotal': False},
        'sales_marketing':   {'section': 'Operating Expenses', 'order': 310, 'indent': 1, 'is_subtotal': False},
        'fulfillment_expense':{'section': 'Operating Expenses', 'order': 315, 'indent': 1, 'is_subtotal': False},
        'sga_expenses':      {'section': 'Operating Expenses', 'order': 320, 'indent': 1, 'is_subtotal': False},
        'ga_expenses':       {'section': 'Operating Expenses', 'order': 325, 'indent': 1, 'is_subtotal': False},
        'stock_compensation':{'section': 'Operating Expenses', 'order': 320, 'indent': 1, 'is_subtotal': False},
        'restructuring_charges': {'section': 'Operating Expenses', 'order': 330, 'indent': 1, 'is_subtotal': False},
        'operating_expenses':{'section': 'Operating Expenses', 'order': 390, 'indent': 0, 'is_subtotal': True},
        
        # === SECCIÓN: OPERATING INCOME ===
        'operating_income':  {'section': 'Operating Income',  'order': 400, 'indent': 0, 'is_subtotal': True},
        'operating_margin':  {'section': 'Operating Income',  'order': 401, 'indent': 1, 'is_subtotal': False},
        'depreciation':      {'section': 'Operating Income',  'order': 410, 'indent': 1, 'is_subtotal': False},
        'ebitda':            {'section': 'Operating Income',  'order': 420, 'indent': 0, 'is_subtotal': True},
        'ebitda_margin':     {'section': 'Operating Income',  'order': 421, 'indent': 1, 'is_subtotal': False},
        
        # === SECCIÓN: NON-OPERATING ===
        'interest_income':   {'section': 'Non-Operating',     'order': 500, 'indent': 1, 'is_subtotal': False},
        'interest_expense':  {'section': 'Non-Operating',     'order': 510, 'indent': 1, 'is_subtotal': False},
        'other_income':      {'section': 'Non-Operating',     'order': 520, 'indent': 1, 'is_subtotal': False},
        'foreign_currency_transaction_gain_loss_before_tax': {'section': 'Non-Operating', 'order': 530, 'indent': 1, 'is_subtotal': False},
        
        # === SECCIÓN: EARNINGS ===
        'income_before_tax': {'section': 'Earnings',          'order': 600, 'indent': 0, 'is_subtotal': True},
        'income_tax':        {'section': 'Earnings',          'order': 610, 'indent': 1, 'is_subtotal': False},
        'net_income':        {'section': 'Earnings',          'order': 620, 'indent': 0, 'is_subtotal': True},
        'net_margin':        {'section': 'Earnings',          'order': 621, 'indent': 1, 'is_subtotal': False},
        'net_income_yoy':    {'section': 'Earnings',          'order': 622, 'indent': 1, 'is_subtotal': False},
        
        # === SECCIÓN: PER SHARE DATA ===
        'eps_basic':         {'section': 'Per Share Data',    'order': 700, 'indent': 0, 'is_subtotal': False},
        'eps_diluted':       {'section': 'Per Share Data',    'order': 710, 'indent': 0, 'is_subtotal': False},
        'eps_yoy':           {'section': 'Per Share Data',    'order': 711, 'indent': 1, 'is_subtotal': False},
        'shares_basic':      {'section': 'Per Share Data',    'order': 720, 'indent': 0, 'is_subtotal': False},
        'shares_diluted':    {'section': 'Per Share Data',    'order': 730, 'indent': 0, 'is_subtotal': False},
        'dividend_per_share':{'section': 'Per Share Data',    'order': 740, 'indent': 0, 'is_subtotal': False},
    }
    
    # =========================================================================
    # ESTRUCTURA JERÁRQUICA DEL BALANCE SHEET
    # =========================================================================
    BALANCE_SHEET_STRUCTURE = {
        # === SECCIÓN: ASSETS ===
        'cash':              {'section': 'Current Assets',    'order': 100, 'indent': 1, 'is_subtotal': False},
        'st_investments':    {'section': 'Current Assets',    'order': 110, 'indent': 1, 'is_subtotal': False},
        'receivables':       {'section': 'Current Assets',    'order': 120, 'indent': 1, 'is_subtotal': False},
        'inventory':         {'section': 'Current Assets',    'order': 130, 'indent': 1, 'is_subtotal': False},
        'prepaid':           {'section': 'Current Assets',    'order': 140, 'indent': 1, 'is_subtotal': False},
        'current_assets':    {'section': 'Current Assets',    'order': 190, 'indent': 0, 'is_subtotal': True},
        
        'ppe':               {'section': 'Non-Current Assets','order': 200, 'indent': 1, 'is_subtotal': False},
        'goodwill':          {'section': 'Non-Current Assets','order': 210, 'indent': 1, 'is_subtotal': False},
        'intangibles':       {'section': 'Non-Current Assets','order': 220, 'indent': 1, 'is_subtotal': False},
        'lt_investments':    {'section': 'Non-Current Assets','order': 230, 'indent': 1, 'is_subtotal': False},
        'total_assets':      {'section': 'Non-Current Assets','order': 290, 'indent': 0, 'is_subtotal': True},
        
        # === SECCIÓN: LIABILITIES ===
        'accounts_payable':  {'section': 'Current Liabilities','order': 300, 'indent': 1, 'is_subtotal': False},
        'accrued_liabilities':{'section': 'Current Liabilities','order': 310, 'indent': 1, 'is_subtotal': False},
        'deferred_revenue':  {'section': 'Current Liabilities','order': 320, 'indent': 1, 'is_subtotal': False},
        'st_debt':           {'section': 'Current Liabilities','order': 330, 'indent': 1, 'is_subtotal': False},
        'current_liabilities':{'section': 'Current Liabilities','order': 390, 'indent': 0, 'is_subtotal': True},
        
        'lt_debt':           {'section': 'Non-Current Liabilities','order': 400, 'indent': 1, 'is_subtotal': False},
        'lease_liability':   {'section': 'Non-Current Liabilities','order': 410, 'indent': 1, 'is_subtotal': False},
        'total_liabilities': {'section': 'Non-Current Liabilities','order': 490, 'indent': 0, 'is_subtotal': True},
        
        # === SECCIÓN: EQUITY ===
        'common_stock':      {'section': 'Equity',            'order': 500, 'indent': 1, 'is_subtotal': False},
        'apic':              {'section': 'Equity',            'order': 510, 'indent': 1, 'is_subtotal': False},
        'retained_earnings': {'section': 'Equity',            'order': 520, 'indent': 1, 'is_subtotal': False},
        'treasury_stock':    {'section': 'Equity',            'order': 530, 'indent': 1, 'is_subtotal': False},
        'total_equity':      {'section': 'Equity',            'order': 590, 'indent': 0, 'is_subtotal': True},
    }
    
    # =========================================================================
    # ESTRUCTURA JERÁRQUICA DEL CASH FLOW STATEMENT
    # =========================================================================
    CASH_FLOW_STRUCTURE = {
        # === SECCIÓN: OPERATING ===
        'net_income':        {'section': 'Operating Activities','order': 100, 'indent': 1, 'is_subtotal': False},
        'depreciation':      {'section': 'Operating Activities','order': 110, 'indent': 1, 'is_subtotal': False},
        'stock_compensation':{'section': 'Operating Activities','order': 120, 'indent': 1, 'is_subtotal': False},
        'deferred_revenue':  {'section': 'Operating Activities','order': 130, 'indent': 1, 'is_subtotal': False},
        'operating_cf':      {'section': 'Operating Activities','order': 190, 'indent': 0, 'is_subtotal': True},
        
        # === SECCIÓN: INVESTING ===
        'capex':             {'section': 'Investing Activities','order': 200, 'indent': 1, 'is_subtotal': False},
        'purchase_investments':{'section': 'Investing Activities','order': 210, 'indent': 1, 'is_subtotal': False},
        'sale_investments':  {'section': 'Investing Activities','order': 220, 'indent': 1, 'is_subtotal': False},
        'intangibles':       {'section': 'Investing Activities','order': 230, 'indent': 1, 'is_subtotal': False},
        'investing_cf':      {'section': 'Investing Activities','order': 290, 'indent': 0, 'is_subtotal': True},
        
        # === SECCIÓN: FINANCING ===
        'dividends_paid':    {'section': 'Financing Activities','order': 300, 'indent': 1, 'is_subtotal': False},
        'stock_repurchased': {'section': 'Financing Activities','order': 310, 'indent': 1, 'is_subtotal': False},
        'stock_issued':      {'section': 'Financing Activities','order': 320, 'indent': 1, 'is_subtotal': False},
        'debt_issued':       {'section': 'Financing Activities','order': 330, 'indent': 1, 'is_subtotal': False},
        'debt_repaid':       {'section': 'Financing Activities','order': 340, 'indent': 1, 'is_subtotal': False},
        'financing_cf':      {'section': 'Financing Activities','order': 390, 'indent': 0, 'is_subtotal': True},
    }
    
    KEY_FINANCIAL_FIELDS = {
        # === INCOME STATEMENT ===
        'revenue', 'cost_of_revenue', 'gross_profit',
        'operating_income', 'operating_expenses', 'sga_expenses', 'rd_expenses', 'sales_marketing', 'fulfillment_expense',
        'net_income', 'income_before_tax', 'income_tax',
        'ebitda', 'eps_basic', 'eps_diluted',
        'interest_income', 'interest_expense', 'other_income',
        'depreciation', 'depreciation_expense',
        'shares_basic', 'shares_diluted',
        'stock_compensation', 'restructuring_charges',
        # Nuevos campos calculados
        'gross_margin', 'operating_margin', 'net_margin', 'ebitda_margin',
        'revenue_yoy', 'net_income_yoy', 'eps_yoy',
        'dividend_per_share',
        
        # === BALANCE SHEET ===
        'total_assets', 'current_assets', 'cash',
        'receivables', 'inventory', 'st_investments', 'prepaid',
        'ppe', 'goodwill', 'intangibles', 'lt_investments',
        'total_liabilities', 'current_liabilities',
        'accounts_payable', 'accrued_liabilities', 'deferred_revenue',
        'st_debt', 'lt_debt', 'lease_liability',
        'total_equity', 'retained_earnings', 'common_stock', 'apic', 'treasury_stock',
        
        # === CASH FLOW ===
        'operating_cf', 'investing_cf', 'financing_cf',
        'capex', 'cf_receivables', 'cf_inventory', 'cf_payables',
        'dividends_paid', 'stock_repurchased', 'stock_issued',
        'debt_issued', 'debt_repaid',
        'purchase_investments', 'sale_investments', 'acquisitions',
    }
    
    def _filter_low_value_fields(
        self, 
        fields: List[Dict[str, Any]], 
        threshold_ratio: float = 0.3,
        min_significant_value: float = 10_000_000  # $10M umbral para valores únicos importantes
    ) -> List[Dict[str, Any]]:
        """
        Filtrar campos con pocos datos o valores mayormente cero.
        threshold_ratio: mínimo ratio de valores no-nulos/no-cero requerido
        min_significant_value: si un campo tiene al menos un valor > este umbral, mantenerlo
        
        Campos clave (revenue, cost_of_revenue, etc.) NUNCA se filtran.
        Campos con valores muy grandes (>$10M) se mantienen aunque aparezcan en pocos períodos.
        """
        filtered = []
        
        for field in fields:
            key = field["key"]
            values = field["values"]
            total = len(values)
            
            # Campos clave SIEMPRE se mantienen (si tienen al menos 1 valor)
            if key in self.KEY_FINANCIAL_FIELDS:
                if any(v is not None for v in values):
                    filtered.append(field)
                continue
            
            # Contar valores significativos (no null y no cero)
            significant = sum(1 for v in values if v is not None and abs(v) > 0.01)
            
            # NUEVO: Si hay al menos un valor muy grande, mantenerlo
            # Esto captura campos como CryptoGains que solo tienen datos en algunos años
            has_large_value = any(v is not None and abs(v) >= min_significant_value for v in values)
            
            # Mantener si tiene suficientes valores significativos O si tiene un valor grande
            if has_large_value or (total > 0 and significant / total >= threshold_ratio):
                filtered.append(field)
        
        return filtered
    
    # =========================================================================
    # API PRINCIPAL
    # =========================================================================
    
    async def _fetch_xbrl_with_semaphore(
        self, 
        filing: Dict[str, Any],
        is_quarterly: bool = False
    ) -> Optional[Tuple[str, str, str, Dict]]:
        """
        Fetch XBRL data con semáforo para rate limiting.
        Retorna: (period_label, filed_at, period_end, xbrl_data) o None si falla.
        """
        async with self._xbrl_semaphore:
            accession_no = filing.get("accessionNo")
            filed_at = filing.get("filedAt", "")
            
            # Pequeño delay para evitar rate limiting
            await asyncio.sleep(self.XBRL_REQUEST_DELAY)
            
            xbrl = await self.get_xbrl_data(accession_no)
            if not xbrl:
                return None
            
            period_end = self._get_period_end_date(xbrl, filed_at)
            
            # Determinar etiqueta del período
            if is_quarterly and period_end:
                # Para quarterly: usar Q1/Q2/Q3/Q4 basado en el mes del period_end
                try:
                    month = int(period_end[5:7])
                    year = period_end[:4]
                    quarter = (month - 1) // 3 + 1
                    period_label = f"Q{quarter} {year}"
                except:
                    period_label = filed_at[:4]
            else:
                # Para annual: solo el año
                period_label = period_end[:4] if period_end else filed_at[:4]
            
            return (period_label, filed_at, period_end, xbrl)
    
    def _extract_filing_data(
        self, 
        xbrl: Dict, 
        fiscal_year: str
    ) -> Tuple[Dict, Dict, Dict]:
        """
        Extraer datos de income, balance y cashflow de un XBRL.
        
        NUEVO ENFOQUE (v2): Procesar TODAS las secciones del XBRL y clasificar
        cada campo por su concepto FASB, no por la sección en la que aparece.
        """
        income_fields = {}
        balance_fields = {}
        cashflow_fields = {}
        
        # Procesar TODAS las secciones del XBRL
        for section_name, section_data in xbrl.items():
            # Saltar secciones no relevantes
            if not isinstance(section_data, dict):
                continue
            if self._should_skip_section(section_name):
                continue
            
            # Detectar categoría por nombre de sección (fallback)
            section_category = self._get_section_category(section_name)
            
            # Extraer campos de esta sección
            fields = self._extract_all_fields_from_section(xbrl, section_name, fiscal_year)
            
            for field_key, field_data in fields.items():
                # ENFOQUE PROFESIONAL: Priorizar la clasificación de SEC-API (sección)
                # SEC-API ya clasifica correctamente los campos por statement
                # Solo usar concept_category como override para campos ambiguos
                
                # Si la sección es definitiva (statements principales), usarla
                is_primary_statement = any(x in section_name.lower() for x in [
                    'statementsof', 'balancesheets', 'consolidatedstatements'
                ])
                
                if is_primary_statement and section_category:
                    category = section_category
                else:
                    # Fallback: clasificar por concepto del campo
                    original_name = field_data[1] if isinstance(field_data, tuple) else field_key
                    concept_category = self._classify_concept_category(original_name)
                    category = concept_category or section_category
                
                if category == "income":
                    # No sobrescribir si ya existe con mayor importancia
                    if field_key not in income_fields:
                        income_fields[field_key] = field_data
                elif category == "balance":
                    if field_key not in balance_fields:
                        balance_fields[field_key] = field_data
                elif category == "cashflow":
                    if field_key not in cashflow_fields:
                        cashflow_fields[field_key] = field_data
        
        return income_fields, balance_fields, cashflow_fields
    
    def _get_section_category(self, section_name: str) -> Optional[str]:
        """
        Obtener categoría de una sección por su nombre (fallback).
        """
        name = section_name.lower()
        
        # Cash Flow sections
        if 'cashflow' in name or 'cash_flow' in name:
            return 'cashflow'
        
        # Balance Sheet sections
        if 'balance' in name or 'position' in name or 'assets' in name:
            return 'balance'
        
        # Income Statement sections
        if any(x in name for x in ['income', 'operations', 'earnings', 'profit', 'loss', 'revenue', 'expense', 'tax']):
            return 'income'
        
        return None
    
    def _extract_all_annual_periods(
        self, 
        xbrl: Dict,
        form_type: str = "10-K"
    ) -> List[Tuple[str, str, Dict, Dict, Dict]]:
        """
        Extraer TODOS los años anuales de un XBRL (para obtener datos comparativos).
        
        Cada 10-K típicamente tiene 3 años de datos comparativos.
        Cada S-1 puede tener más años de datos históricos pre-IPO.
        
        Args:
            xbrl: Datos XBRL parseados
            form_type: Tipo de formulario (10-K, S-1, etc.) para priorización
            
        Returns:
            Lista de (year, end_date, income_data, balance_data, cashflow_data)
            ordenada por año descendente (más reciente primero)
        """
        from datetime import datetime, timedelta
        
        # 1. Detectar todos los períodos anuales disponibles en el XBRL
        # Un período anual es ~365 días (permitimos 350-380 días)
        annual_periods = {}  # {fiscal_year_label: end_date}
        
        income_sections = ["StatementsOfIncome", "StatementsOfOperations", "StatementsOfComprehensiveIncome"]
        
        for section in income_sections:
            section_data = xbrl.get(section, {})
            for field_name, values in section_data.items():
                if not isinstance(values, list):
                    continue
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    # Skip si tiene segment (breakdown)
                    if item.get("segment"):
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
                        
                        # Período anual: entre 350 y 380 días
                        if 350 <= days <= 380:
                            # Usar el año del end_date como label fiscal
                            fiscal_year = end[:4]
                            if fiscal_year not in annual_periods:
                                annual_periods[fiscal_year] = end
                    except ValueError:
                        continue
        
        if not annual_periods:
            return []
        
        # 2. Extraer datos para cada año detectado
        results = []
        for fiscal_year in sorted(annual_periods.keys(), reverse=True):
            end_date = annual_periods[fiscal_year]
            income, balance, cashflow = self._extract_filing_data(xbrl, fiscal_year)
            
            # Solo incluir si tiene datos significativos
            if income or balance:
                results.append((fiscal_year, end_date, income, balance, cashflow, form_type))
        
        return results
    
    def _extract_all_quarters_from_xbrl(
        self, 
        xbrl: Dict
    ) -> List[Tuple[str, Dict, Dict, Dict]]:
        """
        Extraer TODOS los trimestres de un XBRL (para empresas extranjeras con 6-K).
        Retorna lista de (period_label, end_date, income_data, balance_data, cashflow_data).
        
        IMPORTANTE: Los períodos se detectan SOLO desde Income Statement (startDate/endDate).
        El Balance Sheet usa fechas instant que se asocian al end_date del income.
        
        Esto evita crear períodos "fantasma" basados solo en balance sheet
        que no tienen datos de income statement.
        """
        from datetime import datetime
        
        # 1. Detectar períodos SOLO desde secciones de income statement
        quarterly_periods = set()  # (end_date, period_label)
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
                            
                            # Solo períodos de ~3 meses (80-100 días)
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
        
        # 2. Extraer datos para cada trimestre detectado
        results = []
        for end_date, period_label in sorted(quarterly_periods, reverse=True):
            income_data = self._extract_fields_for_period(xbrl, "income", end_date)
            balance_data = self._extract_fields_for_period(xbrl, "balance", end_date)
            cashflow_data = self._extract_fields_for_period(xbrl, "cashflow", end_date)
            
            # Solo incluir si hay datos de income (el período se detectó desde income)
            if income_data:
                results.append((period_label, end_date, income_data, balance_data, cashflow_data))
        
        return results
    
    def _extract_fields_for_period(
        self, 
        xbrl: Dict, 
        category: str, 
        target_end_date: str
    ) -> Dict[str, Tuple[float, str]]:
        """
        Extraer campos para un período específico.
        
        NUEVO ENFOQUE (v2): Procesar TODAS las secciones y clasificar
        cada campo por su concepto.
        
        Busca tanto:
        - endDate (para Income/CashFlow)
        - instant (para Balance Sheet)
        
        Para Balance Sheet, permite fechas cercanas (±5 días) al target_end_date
        porque algunas empresas usan fechas ligeramente diferentes.
        """
        results = {}
        
        # Para balance sheet, aceptar fechas cercanas
        target_year_month = target_end_date[:7] if target_end_date else ""  # "YYYY-MM"
        
        # Procesar TODAS las secciones del XBRL
        for section_name, section_data in xbrl.items():
            if not isinstance(section_data, dict):
                continue
            if self._should_skip_section(section_name):
                continue
            
            for field_name, values in section_data.items():
                if not isinstance(values, list):
                    continue
                
                # Clasificar por concepto del campo
                concept_category = self._classify_concept_category(field_name)
                section_category = self._get_section_category(section_name)
                field_category = concept_category or section_category
                
                # Solo procesar si coincide con la categoría buscada
                if field_category != category:
                    continue
                
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    
                    period = item.get("period", {})
                    if not isinstance(period, dict):
                        continue
                    
                    # Buscar tanto endDate como instant
                    end_date = period.get("endDate", "")
                    instant = period.get("instant", "")
                    
                    # Coincidir con fecha exacta o misma año-mes para balance sheet
                    date_match = False
                    if end_date == target_end_date or instant == target_end_date:
                        date_match = True
                    elif category == "balance" and target_year_month:
                        # Para balance sheet, aceptar cualquier fecha del mismo mes
                        if (end_date and end_date[:7] == target_year_month) or \
                           (instant and instant[:7] == target_year_month):
                            date_match = True
                    
                    if date_match:
                        try:
                            raw_value = item.get("value")
                            if raw_value is None:
                                continue
                            value = float(raw_value)
                            normalized = self._camel_to_snake(field_name)
                            
                            # Preferir valores sin segmento
                            segment = item.get("segment")
                            if normalized not in results or segment is None:
                                results[normalized] = (value, field_name)
                        except (ValueError, TypeError):
                            continue
        
        return results
    
    async def get_financials(
        self,
        ticker: str,
        period: str = "annual",
        limit: int = 10,
        cik: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtener datos financieros consolidados semánticamente.
        
        OPTIMIZADO: Requests XBRL en paralelo con semáforo.
        - Splits y filings se obtienen en paralelo
        - XBRL requests con concurrencia controlada (max 8)
        - Soporta empresas US (10-K/10-Q) y extranjeras (20-F/6-K)
        
        Args:
            ticker: Símbolo del ticker (usado para splits y como fallback)
            period: "annual" o "quarter"
            limit: Número de períodos a obtener
            cik: CIK de la empresa (opcional pero RECOMENDADO para evitar
                 mezclar datos de empresas que reutilizaron el mismo ticker)
        """
        # Form types: 
        # - US companies: 10-K/10-Q
        # - Foreign companies: 20-F/6-K  
        # - S-1/S-1A: Registration statements with historical data (pre-IPO)
        if period == "annual":
            form_types = ["10-K", "20-F", "S-1", "S-1/A"]  # Annual reports + S-1 for historical
        else:
            form_types = ["10-Q", "6-K"]  # Quarterly reports
        
        start_time = asyncio.get_event_loop().time()
        
        # 1. PARALELO: Obtener filings de ambos tipos Y splits simultáneamente
        # Si tenemos CIK, lo usamos para búsqueda precisa (evita tickers reutilizados)
        filing_tasks = [self.get_filings(ticker, ft, limit + 5, cik=cik) for ft in form_types]
        splits_task = self.get_splits(ticker)
        
        results = await asyncio.gather(*filing_tasks, splits_task)
        
        # Combinar filings de ambos tipos
        all_filings = []
        for i, ft in enumerate(form_types):
            all_filings.extend(results[i] or [])
        splits = results[-1]
        
        # Ordenar por fecha descendente
        all_filings.sort(key=lambda x: x.get("filedAt", ""), reverse=True)
        
        if period == "annual":
            # Para ANNUAL: Deduplicar por año fiscal (priorizar 10-K sobre 20-F)
            seen_years = set()
            filings = []
            for f in all_filings:
                fiscal_year = f.get("filedAt", "")[:4]
                form = f.get("formType", "")
                
                if fiscal_year not in seen_years:
                    filings.append(f)
                    seen_years.add(fiscal_year)
                elif form == "10-K":
                    # Reemplazar 20-F con 10-K si existe
                    for i, existing in enumerate(filings):
                        if existing.get("filedAt", "")[:4] == fiscal_year:
                            if existing.get("formType") == "20-F":
                                filings[i] = f
                            break
        else:
            # Para QUARTERLY: Deduplicar por periodOfReport (período que cubre el reporte)
            # NO usar filedAt porque múltiples 6-K pueden presentarse el mismo mes:
            # - Business updates (SIN datos financieros)
            # - Reportes trimestrales (CON datos financieros)
            # 
            # Priorizar:
            # 1. 10-Q sobre 6-K
            # 2. Archivos con formato ticker-YYYYMMDD.htm (reportes financieros reales)
            #    sobre archivos como "form6-k...", "businessupdate...", etc.
            seen_periods = set()  # periodOfReport como clave
            filings = []
            
            for f in all_filings:
                period_of_report = f.get("periodOfReport", "")  # Usar período, NO fecha presentación
                form = f.get("formType", "")
                link = f.get("linkToFilingDetails", "")
                filename = link.split('/')[-1].lower() if link else ""
                
                # Determinar si es un reporte financiero real vs business update
                # Los reportes financieros tienen formato: ticker-YYYYMMDD.htm
                # Los updates tienen: form6-k..., irenlimited-6kbusiness..., etc.
                is_financial_report = (
                    filename.startswith(('iren-', 'googl-', 'goog-', 'aapl-', 'msft-')) or
                    (len(filename) > 15 and filename[4] == '-' and filename[5:13].isdigit())
                )
                
                if period_of_report not in seen_periods:
                    filings.append(f)
                    seen_periods.add(period_of_report)
                else:
                    # Ya existe uno para este período, ver si debemos reemplazarlo
                    for i, existing in enumerate(filings):
                        if existing.get("periodOfReport") == period_of_report:
                            existing_form = existing.get("formType", "")
                            existing_link = existing.get("linkToFilingDetails", "")
                            existing_filename = existing_link.split('/')[-1].lower() if existing_link else ""
                            existing_is_financial = (
                                existing_filename.startswith(('iren-', 'googl-', 'goog-', 'aapl-', 'msft-')) or
                                (len(existing_filename) > 15 and existing_filename[4] == '-' and existing_filename[5:13].isdigit())
                            )
                            
                            # Prioridad: 10-Q > 6-K financiero > 6-K update
                            should_replace = False
                            if form == "10-Q" and existing_form != "10-Q":
                                should_replace = True
                            elif is_financial_report and not existing_is_financial:
                                should_replace = True
                            
                            if should_replace:
                                filings[i] = f
                            break
        
        if not filings:
            return self._empty_response(ticker)
        
        logger.info(f"[{ticker}] Got {len(filings)} filings, {len(splits)} splits in {asyncio.get_event_loop().time() - start_time:.2f}s")
        
        # 2. PARALELO: Fetch todos los XBRL con semáforo (max 5 concurrent)
        is_quarterly = (period == "quarterly")
        xbrl_tasks = [
            self._fetch_xbrl_with_semaphore(filing, is_quarterly) 
            for filing in filings[:limit]
        ]
        
        xbrl_results = await asyncio.gather(*xbrl_tasks, return_exceptions=True)
        
        # 3. Procesar resultados
        income_data = []
        balance_data = []
        cashflow_data = []
        fiscal_years = []
        period_end_dates = []
        
        if is_quarterly:
            # Para QUARTERLY: extraer solo el período principal de cada filing
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
        else:
            # Para ANNUAL: extraer TODOS los años de cada filing (datos comparativos)
            # Esto permite obtener datos históricos de S-1 y años comparativos de 10-K
            all_years_data = {}  # {year: (end_date, income, balance, cashflow, form_type, priority)}
            
            # Prioridad de fuentes (menor número = mayor prioridad)
            FORM_PRIORITY = {"10-K": 1, "20-F": 2, "S-1": 3, "S-1/A": 3}
            
            for i, result in enumerate(xbrl_results):
                if result is None or isinstance(result, Exception):
                    continue
                
                fiscal_year, filed_at, period_end, xbrl = result
                form_type = filings[i].get("formType", "10-K") if i < len(filings) else "10-K"
                
                # Extraer TODOS los años de este filing
                all_periods = self._extract_all_annual_periods(xbrl, form_type)
                
                for year_data in all_periods:
                    year, end_date, income, balance, cashflow, ft = year_data
                    priority = FORM_PRIORITY.get(ft, 99)
                    
                    # Solo usar si es mejor fuente o no existe
                    if year not in all_years_data:
                        all_years_data[year] = (end_date, income, balance, cashflow, ft, priority)
                    else:
                        existing_priority = all_years_data[year][5]
                        if priority < existing_priority:
                            # Mejor fuente encontrada
                            all_years_data[year] = (end_date, income, balance, cashflow, ft, priority)
            
            # Ordenar por año descendente
            for year in sorted(all_years_data.keys(), reverse=True):
                end_date, income, balance, cashflow, ft, _ = all_years_data[year]
                fiscal_years.append(year)
                period_end_dates.append(end_date)
                income_data.append(income)
                balance_data.append(balance)
                cashflow_data.append(cashflow)
            
            # Log de fuentes usadas
            sources_used = {}
            for year in all_years_data:
                ft = all_years_data[year][4]
                sources_used[ft] = sources_used.get(ft, 0) + 1
            logger.info(f"[{ticker}] Year sources: {sources_used}")
        
        if not fiscal_years:
            return self._empty_response(ticker)
        
        logger.info(f"[{ticker}] Fetched {len(fiscal_years)} periods from XBRL in {asyncio.get_event_loop().time() - start_time:.2f}s")
        
        # 4. Consolidar semánticamente
        income_consolidated = self._consolidate_fields_semantically(income_data, fiscal_years)
        balance_consolidated = self._consolidate_fields_semantically(balance_data, fiscal_years)
        cashflow_consolidated = self._consolidate_fields_semantically(cashflow_data, fiscal_years)
        
        # 4.5 Recalcular EBITDA usando D&A de Cash Flow (muchas empresas no lo tienen en Income Statement)
        income_consolidated = self._recalculate_ebitda_with_cashflow(income_consolidated, cashflow_consolidated, len(fiscal_years))
        
        # 5. Ajustar EPS y Shares por splits
        if splits:
            income_consolidated = self._adjust_for_splits(income_consolidated, splits, period_end_dates)
        
        # 5.5 Añadir métricas calculadas (márgenes, YoY, DPS)
        income_consolidated = self._add_calculated_metrics(
            income_consolidated, 
            cashflow_consolidated, 
            len(fiscal_years)
        )
        
        # 6. Filtrar campos con pocos datos
        income_filtered = self._filter_low_value_fields(income_consolidated)
        balance_filtered = self._filter_low_value_fields(balance_consolidated)
        cashflow_filtered = self._filter_low_value_fields(cashflow_consolidated)
        
        total_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"[{ticker}] Total processing: {total_time:.2f}s ({len(fiscal_years)} periods)")
        
        # 7. Formatear respuesta
        has_split_adjustments = any(f.get('split_adjusted') for f in income_filtered)
        
        # Detectar el mes típico de cierre del año fiscal
        # (la mayoría de empresas cierran el mismo mes cada año)
        fiscal_year_end_month = None
        if period_end_dates:
            months = [int(d[5:7]) for d in period_end_dates if d and len(d) >= 7]
            if months:
                # Usar el mes más común
                from collections import Counter
                fiscal_year_end_month = Counter(months).most_common(1)[0][0]
        
        # 8. Enriquecer campos con estructura jerárquica
        income_structured = self._add_structure_metadata(income_filtered, 'income')
        balance_structured = self._add_structure_metadata(balance_filtered, 'balance')
        cashflow_structured = self._add_structure_metadata(cashflow_filtered, 'cashflow')
        
        return {
            "symbol": ticker,
            "currency": "USD",
            "source": "sec-api-xbrl",
            "symbiotic": True,
            "split_adjusted": has_split_adjustments,
            "splits": [{"date": s.get("execution_date"), "ratio": f"{s.get('split_to')}:{s.get('split_from')}"} for s in splits] if splits else [],
            "periods": fiscal_years,
            "period_end_dates": period_end_dates,  # Fechas exactas de cierre de cada período
            "fiscal_year_end_month": fiscal_year_end_month,  # Mes típico de cierre (1-12)
            "income_statement": income_structured,
            "balance_sheet": balance_structured,
            "cash_flow": cashflow_structured,
            "processing_time_seconds": round(total_time, 2),
            "last_updated": datetime.utcnow().isoformat()
        }
    
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
