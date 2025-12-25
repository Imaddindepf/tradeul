"""
SEC XBRL Extractors - Extracción y normalización de datos XBRL.

Procesa datos JSON de SEC-API y los normaliza semánticamente.

Utiliza el Mapping Engine multi-etapa:
1. Cache (PostgreSQL) - Mapeos ya conocidos
2. XBRL_TO_CANONICAL - Diccionario directo
3. Regex Patterns - Patrones compilados
4. FASB Labels - 10,732 etiquetas US-GAAP
5. LLM (opcional) - Grok para conceptos desconocidos
"""

import re
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

from shared.utils.logger import get_logger

# Importar el nuevo sistema de mapping
try:
    from services.mapping.adapter import XBRLMapper, get_mapper
    MAPPING_ENGINE_AVAILABLE = True
except ImportError:
    MAPPING_ENGINE_AVAILABLE = False

logger = get_logger(__name__)


class XBRLExtractor:
    """
    Extractor de datos XBRL.
    
    Procesa JSON de SEC-API y normaliza los campos semánticamente.
    Utiliza el Mapping Engine multi-etapa para clasificación inteligente.
    """
    
    def __init__(self, use_mapping_engine: bool = True, use_llm: bool = False):
        """
        Inicializar extractor.
        
        Args:
            use_mapping_engine: Usar el nuevo Mapping Engine (recomendado)
            use_llm: Habilitar LLM para conceptos desconocidos
        """
        self._mapper = None
        if use_mapping_engine and MAPPING_ENGINE_AVAILABLE:
            try:
                self._mapper = get_mapper(use_engine=True, use_llm=use_llm)
                logger.info("XBRLExtractor: Mapping Engine enabled")
            except Exception as e:
                logger.warning(f"XBRLExtractor: Mapping Engine unavailable ({e})")
    
    # Secciones a IGNORAR completamente
    SKIP_SECTIONS = {
        'CoverPage', 'DocumentAndEntityInformation', 'AuditInformation',
        'AccountingPolicies', 'Policies', 'Tables', 'Parenthetical',
        'InsiderTradingArrangements', 'SignificantAccountingPolicies',
    }
    
    # Patrones de clasificación por concepto
    INCOME_PATTERNS = [
        r'revenue', r'sales', r'cost.*goods', r'cost.*revenue', r'gross_profit',
        r'operating.*income', r'operating.*expense', r'research.*development',
        r'selling.*marketing', r'general.*admin', r'sg.*a', r'depreciation',
        r'amortization', r'interest.*income', r'interest.*expense', r'finance.*cost',
        r'income.*before.*tax', r'income.*tax', r'net_income', r'profit_loss',
        r'earnings.*share', r'eps', r'weighted.*average.*shares', r'shares.*outstanding',
        r'dividend.*per.*share', r'effective.*tax.*rate', r'nonoperating', r'other_income',
        r'foreign.*currency.*transaction', r'gain_loss', r'equity.*method.*investment',
        r'comprehensive_income',
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
    
    # Campos clave que siempre se mantienen
    KEY_FINANCIAL_FIELDS = {
        # === Income Statement ===
        # Revenue
        'revenue', 'product_revenue', 'service_revenue', 'subscription_revenue', 'membership_fees',
        # Cost & Gross
        'cost_of_revenue', 'cost_of_goods_sold', 'cost_of_services', 'gross_profit',
        'gross_margin', 'gross_profit_yoy',
        # Operating Expenses
        'rd_expenses', 'sga_expenses', 'sales_marketing', 'ga_expenses',
        'fulfillment_expense', 'pre_opening_costs', 'stock_compensation',
        'depreciation_amortization', 'restructuring_charges', 'total_operating_expenses',
        # Operating Income
        'operating_income', 'operating_margin', 'operating_income_yoy',
        # EBITDA
        'ebitda', 'ebitda_margin', 'ebitda_yoy', 'ebitdar',
        # Non-Operating
        'interest_expense', 'interest_income', 'interest_and_other_income',
        'investment_income', 'equity_method_income', 'foreign_exchange_gain_loss',
        'gain_loss_securities', 'gain_loss_sale_assets', 'impairment_charges',
        'other_nonoperating', 'total_nonoperating',
        # Earnings
        'ebt_excl_unusual', 'unusual_items', 'income_before_tax',
        'income_tax', 'effective_tax_rate', 'income_continuing_ops', 'income_discontinued_ops',
        'minority_interest', 'net_income', 'net_income_to_common',
        'net_margin', 'net_income_yoy',
        # Per Share
        'eps_basic', 'eps_diluted', 'eps_yoy', 'shares_basic', 'shares_diluted',
        'dividend_per_share', 'special_dividend', 'payout_ratio',
        # Deprecated but kept for compatibility
        'operating_expenses', 'other_income', 'depreciation', 'gain_loss_business',
        
        # === Balance Sheet ===
        # Current Assets (TIKR order)
        'cash', 'restricted_cash', 'st_investments', 'total_cash_st_investments',
        'receivables', 'other_receivables', 'total_receivables',
        'inventory', 'prepaid', 'deferred_tax_assets_current', 'other_current_assets', 'current_assets',
        # Non-Current Assets
        'ppe_gross', 'accumulated_depreciation', 'ppe', 'land', 'construction_in_progress',
        'lt_investments', 'goodwill', 'intangibles', 'deferred_tax_assets',
        'rou_assets', 'operating_lease_rou', 'finance_lease_rou',
        'other_noncurrent_assets', 'total_assets',
        # Current Liabilities
        'accounts_payable', 'accrued_liabilities', 'st_debt', 'current_portion_lt_debt',
        'current_portion_capital_lease', 'deferred_revenue', 'income_tax_payable',
        'operating_lease_liability_current', 'other_current_liabilities', 'current_liabilities',
        # Non-Current Liabilities
        'lt_debt', 'capital_leases', 'finance_lease_liability', 'deferred_revenue_noncurrent',
        'operating_lease_liability', 'deferred_tax_liabilities',
        'pension_liability', 'other_noncurrent_liabilities', 'total_liabilities',
        # Equity
        'preferred_stock', 'common_stock', 'apic', 'retained_earnings',
        'treasury_stock', 'accumulated_oci', 'total_common_equity',
        'noncontrolling_interest', 'total_equity', 'total_liabilities_equity',
        # Supplementary Data
        'shares_outstanding', 'book_value_per_share', 'tangible_book_value', 'tangible_book_value_per_share',
        'total_debt', 'net_debt', 'working_capital', 'equity_method_investments', 'full_time_employees',
        
        # === Cash Flow ===
        'cf_net_income', 'depreciation', 'stock_compensation_cf', 'deferred_taxes',
        'gain_loss_investments', 'impairment_cf', 'change_receivables', 'change_inventory',
        'change_payables', 'change_deferred_revenue', 'other_operating_cf', 'operating_cf',
        'capex', 'acquisitions', 'purchase_investments', 'sale_investments',
        'other_investing_cf', 'investing_cf',
        'debt_issued', 'debt_repaid', 'stock_issued', 'stock_repurchased',
        'dividends_paid', 'other_financing_cf', 'financing_cf',
        'fx_effect', 'net_change_cash', 'cash_beginning', 'cash_ending',
        'free_cash_flow', 'fcf_margin', 'fcf_per_share', 'fcf_yoy',
    }
    
    # Patrones de detección de conceptos financieros
    CONCEPT_PATTERNS = [
        # Revenue
        (r'^revenue$|^revenues$|^net_sales|^sales_revenue|revenue.*contract.*customer|^total_revenue', 
         'revenue', 'Revenue', 10000, 'monetary'),
        
        # Cost of Revenue
        (r'cost.*revenue|cost.*goods.*sold|cost.*sales|^cost_of_sales$|information.*technology.*data.*processing', 
         'cost_of_revenue', 'Cost of Revenue', 9500, 'monetary'),
        
        # Gross Profit
        (r'gross_profit', 'gross_profit', 'Gross Profit', 9400, 'monetary'),
        
        # R&D
        (r'research.*development|r_and_d|technology.*infrastructure|technology.*content', 
         'rd_expenses', 'R&D Expenses', 9000, 'monetary'),
        
        # SG&A
        (r'selling.*general.*admin|sg.*a', 'sga_expenses', 'SG&A Expenses', 8900, 'monetary'),
        
        # Sales & Marketing
        (r'selling.*marketing|sales.*marketing|selling_expense|distribution_cost|^marketing_expense$', 
         'sales_marketing', 'Sales & Marketing', 8850, 'monetary'),
        
        # Fulfillment
        (r'fulfillment.*expense|fulfillment.*cost', 
         'fulfillment_expense', 'Fulfillment Expense', 8840, 'monetary'),
        
        # G&A
        (r'^administrative_expense$|^general.*admin', 
         'ga_expenses', 'G&A Expenses', 8800, 'monetary'),
        
        # Operating Expenses
        (r'operating_expenses|costs.*expenses|total.*operating.*cost', 
         'operating_expenses', 'Operating Expenses', 8500, 'monetary'),
        
        # Operating Income
        (r'^operating_income|^income.*operations|profit_loss_from_operating|operating_profit', 
         'operating_income', 'Operating Income', 8000, 'monetary'),
        
        # Interest Income/Expense
        (r'^finance_income$|^interest_income|investment_income.*interest', 
         'interest_income', 'Interest Income', 7500, 'monetary'),
        (r'^finance_cost|^interest_expense|finance_expense', 
         'interest_expense', 'Interest Expense', 7400, 'monetary'),
        
        # Non-Operating
        (r'^nonoperating|^other.*income|^other.*expense|other_nonoperating', 
         'other_income', 'Other Income/Expense', 7000, 'monetary'),
        
        # Investment Income (combined interest + dividends + investment gains)
        (r'investment_income_interest_and_dividend|interest.*dividend.*income|other_investment_gain_loss',
         'investment_income', 'Investment Income', 7450, 'monetary'),
        
        # Gain/Loss on Sale of Securities
        (r'gain.*loss.*sale.*securit|marketable.*securit.*realized.*gain|realized.*investment.*gain|unrealized_gain_loss_on_investments',
         'gain_loss_securities', 'Gain/Loss on Securities', 6900, 'monetary'),
        
        # Gain/Loss on Sale of Business
        (r'gain.*loss.*sale.*business|gain.*loss.*disposal.*business|gain.*loss.*divestiture',
         'gain_loss_business', 'Gain/Loss on Sale of Business', 6850, 'monetary'),
        
        # Asset Impairment / Write-offs
        (r'asset.*impairment|impairment.*charge|goodwill.*impairment|write.*off|write.*down',
         'impairment_charges', 'Impairment/Write-offs', 6800, 'monetary'),
        
        # Unusual Items
        (r'unusual.*infrequent.*item|extraordinary.*item|special.*charge|restructuring.*charge',
         'unusual_items', 'Unusual Items', 6750, 'monetary'),
        
        # Income Before Tax
        (r'income.*before.*tax|profit.*loss.*before.*tax|income.*continuing.*operations.*before', 
         'income_before_tax', 'Income Before Tax', 6500, 'monetary'),
        
        # Income Tax
        (r'income.*tax.*expense|income.*tax.*benefit|provision.*income.*tax|^income_tax$', 
         'income_tax', 'Income Tax', 6000, 'monetary'),
        
        # Net Income
        (r'^net_income$|^net_income_loss$|^profit_loss$|^profit_loss_attributable', 
         'net_income', 'Net Income', 5500, 'monetary'),
        
        # EPS
        (r'earnings.*share.*basic|eps.*basic|basic_earnings.*per.*share', 
         'eps_basic', 'EPS Basic', 5000, 'perShare'),
        (r'earnings.*share.*diluted|eps.*diluted|diluted_earnings.*per.*share', 
         'eps_diluted', 'EPS Diluted', 4900, 'perShare'),
        
        # Shares
        (r'weighted.*shares.*basic|shares.*outstanding.*basic', 
         'shares_basic', 'Shares Basic', 4800, 'shares'),
        (r'weighted.*shares.*diluted|diluted.*shares', 
         'shares_diluted', 'Shares Diluted', 4700, 'shares'),
        
        # D&A
        (r'depreciation.*amortization|depreciation_depletion', 
         'depreciation', 'D&A', 4500, 'monetary'),
        
        # Balance Sheet - Assets
        (r'^assets$|^total_assets', 'total_assets', 'Total Assets', 10000, 'monetary'),
        (r'assets_current|current_assets|^assets_current$', 'current_assets', 'Current Assets', 9500, 'monetary'),
        (r'cash.*equivalents|cash_and_cash|^cash$', 'cash', 'Cash & Equivalents', 9400, 'monetary'),
        (r'short.*term.*investments|marketable.*securities.*current', 'st_investments', 'Short-term Investments', 9300, 'monetary'),
        (r'accounts.*receivable|receivables.*net|^receivables$', 'receivables', 'Accounts Receivable', 9200, 'monetary'),
        (r'inventory|inventories', 'inventory', 'Inventory', 9100, 'monetary'),
        (r'prepaid.*expense|other.*assets.*current', 'prepaid', 'Prepaid & Other', 9000, 'monetary'),
        (r'property.*plant.*equipment', 'ppe', 'PP&E', 8500, 'monetary'),
        (r'goodwill$', 'goodwill', 'Goodwill', 8400, 'monetary'),
        (r'intangible', 'intangibles', 'Intangible Assets', 8300, 'monetary'),
        (r'long.*term.*investments|investments.*noncurrent', 'lt_investments', 'Long-term Investments', 8200, 'monetary'),
        
        # Balance Sheet - Liabilities
        (r'^liabilities$|^total_liabilities', 'total_liabilities', 'Total Liabilities', 7500, 'monetary'),
        (r'liabilities_current|current_liabilities', 'current_liabilities', 'Current Liabilities', 7400, 'monetary'),
        (r'accounts.*payable|payable.*and.*accrued', 'accounts_payable', 'Accounts Payable', 7300, 'monetary'),
        (r'accrued.*liabilities|accrued.*expenses', 'accrued_liabilities', 'Accrued Liabilities', 7250, 'monetary'),
        (r'short.*term.*debt|short.*term.*borrowings|current.*portion.*long.*term', 'st_debt', 'Short-term Debt', 7200, 'monetary'),
        (r'long.*term.*debt|long.*term.*notes|convertible.*long.*term', 'lt_debt', 'Long-term Debt', 7000, 'monetary'),
        (r'contract.*customer.*liability|deferred.*revenue|unearned.*revenue', 'deferred_revenue', 'Deferred Revenue', 6900, 'monetary'),
        (r'operating.*lease.*liability', 'lease_liability', 'Lease Liabilities', 6800, 'monetary'),
        
        # Balance Sheet - Equity
        (r'stockholders.*equity|total.*equity|^equity$', 'total_equity', 'Total Equity', 6500, 'monetary'),
        (r'retained_earnings|accumulated_deficit', 'retained_earnings', 'Retained Earnings', 6400, 'monetary'),
        (r'common.*stock.*value|^common_stock$', 'common_stock', 'Common Stock', 6300, 'monetary'),
        (r'additional.*paid.*capital|paid.*capital', 'apic', 'Additional Paid-in Capital', 6200, 'monetary'),
        (r'treasury.*stock', 'treasury_stock', 'Treasury Stock', 6100, 'monetary'),
        
        # Cash Flow - Operating
        (r'net.*cash.*operating|operating_activities|^cash.*flows.*operating', 'operating_cf', 'Operating Cash Flow', 10000, 'monetary'),
        (r'share.*based.*compensation|stock.*compensation', 'stock_compensation', 'Stock Compensation', 9200, 'monetary'),
        
        # Cash Flow - Investing
        (r'net.*cash.*investing|investing_activities', 'investing_cf', 'Investing Cash Flow', 9000, 'monetary'),
        (r'capital.*expenditure|payments.*acquire.*property|purchase.*property.*plant', 'capex', 'CapEx', 8500, 'monetary'),
        (r'purchase.*investments|payments.*acquire.*investments', 'purchase_investments', 'Purchases of Investments', 8400, 'monetary'),
        (r'sale.*investments|proceeds.*sale.*investments', 'sale_investments', 'Sales of Investments', 8300, 'monetary'),
        
        # Cash Flow - Financing
        (r'net.*cash.*financing|financing_activities', 'financing_cf', 'Financing Cash Flow', 8000, 'monetary'),
        (r'dividends.*paid|payments.*dividends', 'dividends_paid', 'Dividends Paid', 7500, 'monetary'),
        (r'repurchase.*common.*stock|stock.*repurchased', 'stock_repurchased', 'Stock Repurchased', 7400, 'monetary'),
        (r'proceeds.*issuance.*common.*stock|proceeds.*stock', 'stock_issued', 'Stock Issued', 7300, 'monetary'),
        (r'proceeds.*debt|proceeds.*borrowings', 'debt_issued', 'Debt Issued', 7200, 'monetary'),
        (r'repayments.*debt|payments.*long.*term', 'debt_repaid', 'Debt Repaid', 7100, 'monetary'),
    ]
    
    def _camel_to_snake(self, name: str) -> str:
        """Convertir CamelCase a snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    
    def classify_concept(self, field_name: str) -> Optional[str]:
        """
        Clasificar un campo XBRL en su categoría.
        
        Returns: 'income', 'balance', 'cashflow', o None
        """
        name = self._camel_to_snake(field_name).lower()
        
        if self._should_skip_field(field_name):
            return None
        
        for pattern in self.CASHFLOW_PATTERNS:
            if re.search(pattern, name):
                return 'cashflow'
        
        for pattern in self.BALANCE_PATTERNS:
            if re.search(pattern, name):
                return 'balance'
        
        for pattern in self.INCOME_PATTERNS:
            if re.search(pattern, name):
                return 'income'
        
        return None
    
    def detect_concept(self, field_name: str, statement_type: str = "income") -> Tuple[str, str, int, str]:
        """
        Detectar el concepto financiero de un campo XBRL.
        
        Utiliza el Mapping Engine multi-etapa si está disponible:
        1. Cache (PostgreSQL)
        2. XBRL_TO_CANONICAL directo
        3. Regex patterns
        4. FASB labels
        5. LLM (si habilitado)
        
        Returns: (canonical_key, display_label, importance_score, data_type)
        """
        # Usar el nuevo Mapping Engine si está disponible
        if MAPPING_ENGINE_AVAILABLE and hasattr(self, '_mapper'):
            try:
                return self._mapper.detect_concept(field_name, statement_type)
            except Exception as e:
                logger.debug(f"Mapping engine failed for {field_name}: {e}")
        
        # Fallback al método original
        return self._detect_concept_legacy(field_name)
    
    def _detect_concept_legacy(self, field_name: str) -> Tuple[str, str, int, str]:
        """
        Método legacy de detección de concepto.
        Usado como fallback si el Mapping Engine no está disponible.
        """
        name = self._camel_to_snake(field_name).lower()
        
        for pattern, key, label, importance, dtype in self.CONCEPT_PATTERNS:
            if re.search(pattern, name):
                return (key, label, importance, dtype)
        
        # Fallback: generar label del nombre
        words = name.split('_')[:4]
        auto_label = ' '.join(w.capitalize() for w in words if w not in {'and', 'the', 'of'})
        
        return (name, auto_label, 50, 'monetary')
    
    def _should_skip_field(self, field_name: str) -> bool:
        """Determinar si un campo debe ser ignorado."""
        name = field_name.lower()
        
        skip_patterns = [
            r'comprehensive_income',
            r'reclassification',
            r'adjustment',
            r'discontinued',
            r'preferred.*dividends',
            r'noncontrolling',
            r'segment',
            r'_hedge_',
            r'_aoci_',
            r'unrealized_holding',
            r'accumulated_depreciation',
            r'accumulated_depletion',
            r'accumulated_amortization',
        ]
        
        return any(re.search(p, name) for p in skip_patterns)
    
    def should_skip_section(self, section_name: str) -> bool:
        """Determinar si una sección completa debe ser ignorada."""
        for skip in self.SKIP_SECTIONS:
            if skip in section_name:
                return True
        
        name_lower = section_name.lower()
        if any(x in name_lower for x in ['table', 'note', 'schedule', 'policy', 'policies']):
            if 'earningspershare' in name_lower or 'netincomepershare' in name_lower:
                return False
            if 'incometax' in name_lower:
                return False
            if 'supplemental' in name_lower:
                return False
            # Allow Revenue Details sections (for InterestAndOtherIncome)
            if 'revenueschedule' in name_lower or 'revenuedetails' in name_lower:
                return False
            # Allow Other Income/Expense Details
            if 'otherincomeexpense' in name_lower and 'details' in name_lower:
                return False
            return True
        
        return False
    
    def get_section_category(self, section_name: str) -> Optional[str]:
        """Obtener categoría de una sección por su nombre."""
        name = section_name.lower()
        
        if 'cashflow' in name or 'cash_flow' in name:
            return 'cashflow'
        
        if 'balance' in name or 'position' in name or 'assets' in name:
            return 'balance'
        
        if any(x in name for x in ['income', 'operations', 'earnings', 'profit', 'loss', 'revenue', 'expense', 'tax']):
            return 'income'
        
        return None
    
    def extract_section_fields(
        self, 
        xbrl_data: Dict, 
        section_name: str,
        fiscal_year: str
    ) -> Dict[str, Tuple[float, str, int]]:
        """
        Extraer todos los campos de una sección XBRL.
        
        Returns: {normalized_name: (value, original_name, section_priority)}
        
        Section priority (lower = higher priority):
        - 1-5: Primary statements (Income, Balance, Cash Flow)
        - 10-15: Disclosures
        - 20+: Notes and other
        """
        from .value_selector import ValueSelector
        
        section_data = xbrl_data.get(section_name, {})
        section_priority = ValueSelector.get_section_priority(section_name)
        results = {}
        
        for field_name, values in section_data.items():
            if not isinstance(values, list) or not values:
                continue
            
            # Prioridad 1: Valores consolidados (sin segmento)
            consolidated = [
                item for item in values 
                if isinstance(item, dict) and "segment" not in item and item.get("value") is not None
            ]
            
            # Prioridad 2: Valores segmentados (only if no consolidated)
            if not consolidated:
                consolidated = self._aggregate_segmented_values(values)
            
            if not consolidated:
                continue
            
            # Buscar valor del año fiscal
            best_value = self._find_best_value(consolidated, fiscal_year)
            
            if best_value is not None:
                normalized = self._camel_to_snake(field_name)
                results[normalized] = (best_value, field_name, section_priority)
        
        return results
    
    def _aggregate_segmented_values(self, values: List) -> List:
        """Agregar valores segmentados por período."""
        period_sums = {}
        period_max = {}
        
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
            
            if end_date not in period_max or abs(val) > abs(period_max[end_date]):
                period_max[end_date] = val
            
            segment = item.get("segment", {})
            segment_dim = segment.get("dimension", "") if isinstance(segment, dict) else ""
            segment_val = segment.get("value", "") if isinstance(segment, dict) else ""
            
            is_product_segment = (
                "ProductsAndServices" in segment_dim or
                "Revenue" in segment_val or
                "Member" in segment_val and "country:" not in segment_val and "srt:" not in segment_val
            )
            
            if is_product_segment:
                if end_date not in period_sums:
                    period_sums[end_date] = 0
                period_sums[end_date] += val
        
        period_values = {}
        for end_date in set(list(period_sums.keys()) + list(period_max.keys())):
            if end_date in period_sums and period_sums[end_date] != 0:
                period_values[end_date] = period_sums[end_date]
            elif end_date in period_max:
                period_values[end_date] = period_max[end_date]
        
        return [
            {"value": str(v), "period": {"endDate": d}}
            for d, v in period_values.items()
        ]
    
    def extract_finance_division_revenue(
        self, 
        xbrl_data: Dict, 
        fiscal_years: List[str]
    ) -> Optional[Dict]:
        """
        Extraer ingresos del segmento Finance Division (CAT, GE, etc.).
        
        Busca en secciones de segmentos el tag de Financial Products.
        Retorna un dict con la estructura de campo o None si no existe.
        """
        # Buscar secciones de segmentos de revenue
        segment_sections = [
            name for name in xbrl_data.keys() 
            if 'segment' in name.lower() and ('revenue' in name.lower() or 'disaggregation' in name.lower())
        ]
        
        logger.debug(f"Segment sections found: {segment_sections}")
        
        if not segment_sections:
            return None
        
        finance_values = {}
        
        for section_name in segment_sections:
            section = xbrl_data.get(section_name, {})
            
            # Buscar tag Revenues
            revenues = section.get('Revenues', [])
            if not revenues:
                continue
            
            for item in revenues:
                if not isinstance(item, dict) or item.get('value') is None:
                    continue
                
                # Buscar segmento Financial Products
                segment = item.get('segment', {})
                
                # El segmento puede ser dict simple o lista de dicts
                segment_str = str(segment).lower()
                
                is_finance_segment = (
                    'financialproduct' in segment_str or
                    'financialservices' in segment_str or
                    'catfinancial' in segment_str
                )
                
                # Evitar valores de inter-segment elimination
                if 'intersegmentelimination' in segment_str:
                    continue
                
                # Evitar valores de related party (ventas internas)
                if 'relatedparty' in segment_str:
                    continue
                
                if is_finance_segment:
                    period = item.get('period', {})
                    end_date = period.get('endDate', '')
                    year = end_date[:4] if end_date else ''
                    
                    if year:
                        try:
                            val = float(item['value'])
                            # Evitar valores muy pequeños (< 100M)
                            if abs(val) < 1e8:
                                continue
                            
                            # =========================================================
                            # LÓGICA PROFESIONAL: Preferir valor con MENOS dimensiones
                            # =========================================================
                            # En XBRL, menos dimensiones = valor más primario/consolidado
                            # Más dimensiones = desglose (geográfico, por producto, etc.)
                            #
                            # Ejemplo CAT 2024:
                            #   3,446M - 1 dimension (ProductOrServiceAxis) ← PRIMARIO
                            #   4,053M - 2 dimensions (ConsolidationItemsAxis + Segment)
                            #   2,702M - 3 dimensions (Consolidation + Geography + Segment)
                            
                            if isinstance(segment, list):
                                num_dimensions = len(segment)
                            elif isinstance(segment, dict) and segment:
                                num_dimensions = 1
                            else:
                                num_dimensions = 0  # Sin dimensión = valor puro
                            
                            if year not in finance_values:
                                # Primer valor para este año
                                finance_values[year] = (val, num_dimensions)
                            else:
                                existing_val, existing_dims = finance_values[year]
                                # Preferir el valor con MENOS dimensiones (más primario)
                                if num_dimensions < existing_dims:
                                    finance_values[year] = (val, num_dimensions)
                                    logger.debug(f"Finance Div {year}: {existing_val/1e6:.0f}M ({existing_dims}d) -> {val/1e6:.0f}M ({num_dimensions}d)")
                        except (ValueError, TypeError):
                            continue
        
        if not finance_values:
            return None
        
        # Extraer solo los valores (descartar flags de prioridad)
        finance_values_clean = {
            year: data[0] if isinstance(data, tuple) else data
            for year, data in finance_values.items()
        }
        
        logger.debug(f"Finance Division values by year: {finance_values_clean}")
        
        # Construir valores para los años fiscales
        values = []
        for fy in fiscal_years:
            year = str(fy)[:4]
            values.append(finance_values_clean.get(year))
        
        # Solo retornar si tenemos datos válidos
        if not any(v is not None for v in values):
            return None
        
        return {
            'key': 'finance_division_revenue',
            'label': 'Finance Div. Revenue',
            'values': values,
            'importance': 9000,
            'data_type': 'monetary',
            'source_fields': ['Revenues:FinancialProductsSegmentMember'],
            'calculated': False
        }
    
    def extract_finance_division_costs(
        self, 
        xbrl_data: Dict[str, Any], 
        fiscal_years: List[str]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Extract Finance Division costs for companies like CAT, GE, Ford.
        
        Returns two fields:
        1. finance_div_operating_exp: Sum of depreciation, lease depreciation, SG&A
           from Financial Products segment
        2. interest_expense_finance_div: Interest expense from financing operations
        
        These are needed to calculate Gross Profit correctly:
        Gross Profit = Total Revenue - COGS - Finance Div Op Exp - Interest Exp Finance
        
        XBRL Concepts (CAT example):
        - DepreciationDepletionAndAmortization (Financial Products): 740M
        - OperatingLeasesIncomeStatementDepreciationExpenseOnPropertySubjectToOrHeldForLease: 722M
        - SellingGeneralAndAdministrativeResearchAndDevelopment (Financial Products): 771M
        - FinancingInterestExpense: 1,286M
        """
        # Components of Finance Division Operating Expenses
        OPERATING_EXP_CONCEPTS = [
            'DepreciationDepletionAndAmortization',
            'OperatingLeasesIncomeStatementDepreciationExpenseOnPropertySubjectToOrHeldForLease',
            'SellingGeneralAndAdministrativeResearchAndDevelopment',
        ]
        
        # Interest expense concept
        INTEREST_EXP_CONCEPT = 'FinancingInterestExpense'
        
        # Find segment sections
        segment_sections = [
            name for name in xbrl_data.keys() 
            if isinstance(xbrl_data.get(name), dict)
        ]
        
        # Collect values by year
        operating_exp_by_year: Dict[str, float] = {}
        interest_exp_by_year: Dict[str, float] = {}
        
        for section_name in segment_sections:
            section = xbrl_data.get(section_name, {})
            
            # Process each concept
            for concept in OPERATING_EXP_CONCEPTS + [INTEREST_EXP_CONCEPT]:
                items = section.get(concept, [])
                if not items:
                    continue
                
                for item in items:
                    if not isinstance(item, dict) or item.get('value') is None:
                        continue
                    
                    segment = item.get('segment', {})
                    segment_str = str(segment).lower()
                    
                    # Must be Financial Products segment
                    is_finance_segment = (
                        'financialproduct' in segment_str or
                        'financialservices' in segment_str
                    )
                    
                    if not is_finance_segment:
                        continue
                    
                    # Get period info
                    period = item.get('period', {})
                    start_date = period.get('startDate', '')
                    end_date = period.get('endDate', '')
                    
                    if not start_date or not end_date:
                        continue
                    
                    year = end_date[:4]
                    
                    try:
                        val = float(item['value'])
                        
                        # Count dimensions (prefer fewer = more consolidated)
                        if isinstance(segment, list):
                            num_dims = len(segment)
                        elif isinstance(segment, dict) and segment:
                            num_dims = 1
                        else:
                            num_dims = 0
                        
                        if concept == INTEREST_EXP_CONCEPT:
                            # Interest expense
                            if year not in interest_exp_by_year:
                                interest_exp_by_year[year] = (val, num_dims)
                            elif num_dims < interest_exp_by_year[year][1]:
                                interest_exp_by_year[year] = (val, num_dims)
                        else:
                            # Operating expense component - accumulate
                            key = f"{year}_{concept}"
                            if key not in operating_exp_by_year:
                                operating_exp_by_year[key] = (val, num_dims, concept)
                            elif num_dims < operating_exp_by_year[key][1]:
                                operating_exp_by_year[key] = (val, num_dims, concept)
                    except (ValueError, TypeError):
                        continue
        
        # Aggregate operating expenses by year
        op_exp_totals: Dict[str, float] = {}
        for key, (val, _, concept) in operating_exp_by_year.items():
            year = key.split('_')[0]
            if year not in op_exp_totals:
                op_exp_totals[year] = 0
            op_exp_totals[year] += val
            logger.debug(f"Finance Div Op Exp {year}: +{val/1e6:.0f}M from {concept}")
        
        # Clean interest expense values
        interest_exp_clean = {
            year: data[0] for year, data in interest_exp_by_year.items()
        }
        
        # Build result fields
        results = []
        
        # 1. Finance Division Operating Expenses
        if op_exp_totals:
            op_exp_values = []
            for fy in fiscal_years:
                year = str(fy)[:4]
                op_exp_values.append(op_exp_totals.get(year))
            
            if any(v is not None for v in op_exp_values):
                results.append({
                    'key': 'finance_div_operating_exp',
                    'label': 'Finance Div. Operating Exp.',
                    'values': op_exp_values,
                    'importance': 9400,
                    'data_type': 'monetary',
                    'source_fields': OPERATING_EXP_CONCEPTS,
                    'calculated': True,  # Sum of components
                    'section': 'Cost & Gross Profit',
                })
                logger.debug(f"Finance Div Op Exp by year: {op_exp_totals}")
        
        # 2. Interest Expense - Finance Division
        if interest_exp_clean:
            int_exp_values = []
            for fy in fiscal_years:
                year = str(fy)[:4]
                int_exp_values.append(interest_exp_clean.get(year))
            
            if any(v is not None for v in int_exp_values):
                results.append({
                    'key': 'interest_expense_finance_div',
                    'label': 'Interest Expense - Finance Div.',
                    'values': int_exp_values,
                    'importance': 9350,
                    'data_type': 'monetary',
                    'source_fields': [INTEREST_EXP_CONCEPT],
                    'calculated': False,
                    'section': 'Cost & Gross Profit',
                })
                logger.debug(f"Interest Exp Finance Div by year: {interest_exp_clean}")
        
        return results if results else None
    
    def _find_best_value(self, consolidated: List, fiscal_year: str) -> Optional[float]:
        """
        Encontrar el mejor valor para un año fiscal.
        
        IMPORTANTE: NO usa fallback. Si no encuentra un valor para el año exacto,
        retorna None. Esto evita el bug donde datos de años recientes se duplican
        en años anteriores cuando SEC-API no incluye datos históricos.
        """
        fiscal_year_str = str(fiscal_year)[:4]
        
        # Buscar coincidencia exacta del año fiscal
        for item in consolidated:
            period = item.get("period", {})
            end_date = period.get("endDate") or period.get("instant", "")
            
            if end_date and end_date[:4] == fiscal_year_str:
                try:
                    return float(item["value"])
                except (ValueError, TypeError):
                    continue
            
        # NO usar fallback - retornar None si no hay coincidencia exacta
        # Los datos correctos vendrán del 10-K correspondiente a ese año
        return None
    
    # Campos donde preferimos el valor más grande (totales)
    # NOTA: 'revenue' removido - usar ValueSelector para selección inteligente
    # El criterio "más grande" causaba bugs (ej: ASTS tomaba 13.8M en lugar de 4.4M)
    PREFER_LARGER_VALUE_FIELDS = {
        'total_operating_expenses',  # Suma de gastos operativos
        'total_assets', 'total_liabilities', 'total_equity',  # Balance totals
        'current_assets', 'current_liabilities', 'total_debt',
        'operating_cf', 'investing_cf', 'financing_cf',  # Cash flow totals
    }
    
    # Campos que requieren selección inteligente (no "más grande")
    # Estos usan ValueSelector para priorizar por sección y concepto
    INTELLIGENT_SELECTION_FIELDS = {
        'revenue', 'cost_of_revenue', 'gross_profit',
        'operating_income', 'net_income', 'income_before_tax',
        'ebitda', 'free_cash_flow'
    }
    
    def consolidate_fields(
        self,
        all_periods_data: List[Dict[str, Tuple[float, str]]],
        fiscal_years: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Consolidar campos semánticamente relacionados.
        Para campos de tipo "total", preferimos el valor más grande.
        
        Incluye Quality Score:
        - confidence: 0.0-1.0 indicando fiabilidad del mapeo
        - mapping_source: "direct" | "regex" | "fasb" | "fallback"
        """
        concept_groups: Dict[str, Dict] = {}
        
        for period_idx, period_data in enumerate(all_periods_data):
            # Validar que period_data es un diccionario
            if not isinstance(period_data, dict):
                logger.warning(f"Period {period_idx} data is not a dict: {type(period_data)}")
                continue
            
            for normalized_name, item in period_data.items():
                # Validar estructura de tupla (value, original) o (value, original, section_priority)
                if not isinstance(item, (tuple, list)) or len(item) < 2:
                    logger.debug(f"Skipping malformed item for {normalized_name}: {type(item)}")
                    continue
                
                if len(item) == 3:
                    value, original, section_priority = item
                else:
                    value, original = item
                    section_priority = 99  # Default low priority
                if self._should_skip_field(normalized_name):
                    continue
                
                # Pasar el nombre original (CamelCase) para mapeo directo XBRL
                # Usar modo extendido para obtener confidence y source
                if MAPPING_ENGINE_AVAILABLE and hasattr(self, '_mapper') and self._mapper:
                    mapping_result = self._mapper.detect_concept(original, extended=True)
                    if len(mapping_result) == 6:
                        canonical_key, label, importance, data_type, confidence, mapping_source = mapping_result
                    else:
                        canonical_key, label, importance, data_type = mapping_result
                        confidence, mapping_source = 0.8, "legacy"
                else:
                    canonical_key, label, importance, data_type = self.detect_concept(original)
                    confidence, mapping_source = 0.8, "legacy"
                
                if canonical_key is None:
                    logger.error(f"detect_concept returned None for canonical_key: {original}")
                    continue
                
                # Skip campos marcados para exclusión (ej: _skip_shares, _skip_balance_sheet)
                if canonical_key.startswith('_skip'):
                    continue
                
                if canonical_key not in concept_groups:
                    concept_groups[canonical_key] = {
                        'key': canonical_key,
                        'label': label,
                        'importance': importance,
                        'data_type': data_type,
                        'confidence': confidence,
                        'mapping_source': mapping_source,
                        'values': [None] * len(all_periods_data),
                        'sources': []
                    }
                else:
                    # Si encontramos un mapeo con mayor confianza, actualizar
                    if confidence > concept_groups[canonical_key].get('confidence', 0):
                        concept_groups[canonical_key]['confidence'] = confidence
                        concept_groups[canonical_key]['mapping_source'] = mapping_source
                
                current_value = concept_groups[canonical_key]['values'][period_idx]
                current_source = concept_groups[canonical_key].get('_period_sources', {}).get(period_idx)
                current_section_pri = concept_groups[canonical_key].get('_section_priorities', {}).get(period_idx, 99)
                
                # Inicializar tracking de fuentes por período si no existe
                if '_period_sources' not in concept_groups[canonical_key]:
                    concept_groups[canonical_key]['_period_sources'] = {}
                if '_section_priorities' not in concept_groups[canonical_key]:
                    concept_groups[canonical_key]['_section_priorities'] = {}
                
                # Determinar si debemos actualizar el valor
                should_update = False
                
                if current_value is None:
                    should_update = True
                elif canonical_key in self.INTELLIGENT_SELECTION_FIELDS:
                    # Selección inteligente profesional:
                    # 1. Preferir secciones primarias (Income Statement) sobre disclosures
                    # 2. Preferir conceptos primarios sobre alternativos
                    from .value_selector import ValueSelector
                    
                    current_concept_pri = ValueSelector.get_concept_priority(current_source or '')
                    new_concept_pri = ValueSelector.get_concept_priority(original)
                    
                    # Calcular prioridad total: section + concept
                    current_total_pri = current_section_pri + current_concept_pri
                    new_total_pri = section_priority + new_concept_pri
                    
                    # Solo actualizar si el nuevo tiene mejor prioridad total (número menor)
                    if new_total_pri < current_total_pri:
                        should_update = True
                        logger.debug(f"Intelligent selection: {canonical_key} updating from {current_source} (total_pri={current_total_pri}) to {original} (total_pri={new_total_pri})")
                elif canonical_key in self.PREFER_LARGER_VALUE_FIELDS:
                    # Para totales, preferir el valor más grande (absoluto)
                    if value is not None and abs(value) > abs(current_value):
                        should_update = True
                # else: Comportamiento original - mantener primer valor
                
                if should_update and value is not None:
                    concept_groups[canonical_key]['values'][period_idx] = value
                    concept_groups[canonical_key]['_period_sources'][period_idx] = original
                    concept_groups[canonical_key]['_section_priorities'][period_idx] = section_priority
                
                if original not in concept_groups[canonical_key]['sources']:
                    concept_groups[canonical_key]['sources'].append(original)
        
        consolidated_fields = []
        seen_keys = set()
        
        for concept_key, group in concept_groups.items():
            if any(v is not None for v in group['values']):
                # Skip duplicates (keep first occurrence which has highest importance due to consolidation order)
                if group['key'] in seen_keys:
                    continue
                seen_keys.add(group['key'])
                
                field_data = {
                    'key': group['key'],
                    'label': group['label'],
                    'values': group['values'],
                    'importance': group['importance'],
                    'data_type': group.get('data_type', 'monetary'),
                    'source_fields': group['sources'],
                    # Quality Score metadata
                    'confidence': group.get('confidence', 0.8),
                    'mapping_source': group.get('mapping_source', 'unknown')
                }
                # No incluir campos internos de tracking (_period_sources, _section_priorities)
                consolidated_fields.append(field_data)
        
        consolidated_fields.sort(key=lambda x: x['importance'], reverse=True)
        
        return consolidated_fields
    
    def filter_low_value_fields(
        self, 
        fields: List[Dict[str, Any]], 
        threshold_ratio: float = 0.3,
        min_significant_value: float = 10_000_000
    ) -> List[Dict[str, Any]]:
        """
        Filtrar campos con pocos datos o valores mayormente cero.
        """
        filtered = []
        
        for field in fields:
            key = field["key"]
            values = field["values"]
            total = len(values)
            
            if key in self.KEY_FINANCIAL_FIELDS:
                if any(v is not None for v in values):
                    filtered.append(field)
                continue
            
            significant = sum(1 for v in values if v is not None and abs(v) > 0.01)
            has_large_value = any(v is not None and abs(v) >= min_significant_value for v in values)
            
            if has_large_value or (total > 0 and significant / total >= threshold_ratio):
                filtered.append(field)
        
        return filtered

