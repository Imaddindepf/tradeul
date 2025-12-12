"""
SEC XBRL Extractors - Extracción y normalización de datos XBRL.

Procesa datos JSON de SEC-API y los normaliza semánticamente.
"""

import re
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class XBRLExtractor:
    """
    Extractor de datos XBRL.
    
    Procesa JSON de SEC-API y normaliza los campos semánticamente.
    """
    
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
        # Income
        'revenue', 'cost_of_revenue', 'gross_profit', 'operating_income', 
        'operating_expenses', 'sga_expenses', 'rd_expenses', 'sales_marketing',
        'net_income', 'income_before_tax', 'income_tax', 'ebitda',
        'eps_basic', 'eps_diluted', 'interest_income', 'interest_expense',
        'depreciation', 'shares_basic', 'shares_diluted',
        'gross_margin', 'operating_margin', 'net_margin', 'ebitda_margin',
        'revenue_yoy', 'net_income_yoy', 'eps_yoy', 'dividend_per_share',
        'gross_profit_yoy', 'operating_income_yoy',
        # Non-Operating
        'investment_income', 'other_income', 'gain_loss_securities', 
        'gain_loss_business', 'impairment_charges', 'unusual_items',
        # Balance
        'total_assets', 'current_assets', 'cash', 'receivables', 'inventory',
        'ppe', 'goodwill', 'intangibles', 'total_liabilities', 'current_liabilities',
        'accounts_payable', 'st_debt', 'lt_debt', 'total_equity', 'retained_earnings',
        # Cash Flow
        'operating_cf', 'investing_cf', 'financing_cf', 'capex', 'dividends_paid',
        'stock_repurchased', 'debt_issued', 'debt_repaid',
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
    
    def detect_concept(self, field_name: str) -> Tuple[str, str, int, str]:
        """
        Detectar el concepto financiero de un campo XBRL.
        
        Returns: (canonical_key, display_label, importance_score, data_type)
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
    ) -> Dict[str, Tuple[float, str]]:
        """
        Extraer todos los campos de una sección XBRL.
        
        Returns: {normalized_name: (value, original_name)}
        """
        section_data = xbrl_data.get(section_name, {})
        results = {}
        
        for field_name, values in section_data.items():
            if not isinstance(values, list) or not values:
                continue
            
            # Prioridad 1: Valores consolidados (sin segmento)
            consolidated = [
                item for item in values 
                if isinstance(item, dict) and "segment" not in item and item.get("value") is not None
            ]
            
            # Prioridad 2: Valores segmentados
            if not consolidated:
                consolidated = self._aggregate_segmented_values(values)
            
            if not consolidated:
                continue
            
            # Buscar valor del año fiscal
            best_value = self._find_best_value(consolidated, fiscal_year)
            
            if best_value is not None:
                normalized = self._camel_to_snake(field_name)
                results[normalized] = (best_value, field_name)
        
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
    
    def _find_best_value(self, consolidated: List, fiscal_year: str) -> Optional[float]:
        """Encontrar el mejor valor para un año fiscal."""
        best_value = None
        best_date = ""
        
        for item in consolidated:
            period = item.get("period", {})
            end_date = period.get("endDate") or period.get("instant", "")
            
            if end_date and end_date[:4] == str(fiscal_year)[:4]:
                try:
                    return float(item["value"])
                except (ValueError, TypeError):
                    continue
            
            if end_date > best_date:
                try:
                    best_value = float(item["value"])
                    best_date = end_date
                except (ValueError, TypeError):
                    continue
        
        return best_value
    
    def consolidate_fields(
        self,
        all_periods_data: List[Dict[str, Tuple[float, str]]],
        fiscal_years: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Consolidar campos semánticamente relacionados.
        """
        concept_groups: Dict[str, Dict] = {}
        
        for period_idx, period_data in enumerate(all_periods_data):
            for normalized_name, (value, original) in period_data.items():
                if self._should_skip_field(normalized_name):
                    continue
                
                canonical_key, label, importance, data_type = self.detect_concept(normalized_name)
                
                if canonical_key not in concept_groups:
                    concept_groups[canonical_key] = {
                        'key': canonical_key,
                        'label': label,
                        'importance': importance,
                        'data_type': data_type,
                        'values': [None] * len(all_periods_data),
                        'sources': []
                    }
                
                if concept_groups[canonical_key]['values'][period_idx] is None:
                    concept_groups[canonical_key]['values'][period_idx] = value
                
                if original not in concept_groups[canonical_key]['sources']:
                    concept_groups[canonical_key]['sources'].append(original)
        
        consolidated_fields = []
        
        for concept_key, group in concept_groups.items():
            if any(v is not None for v in group['values']):
                field_data = {
                    'key': group['key'],
                    'label': group['label'],
                    'values': group['values'],
                    'importance': group['importance'],
                    'data_type': group.get('data_type', 'monetary'),
                    'source_fields': group['sources']
                }
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

