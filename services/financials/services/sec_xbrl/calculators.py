"""
SEC XBRL Calculators - Métricas calculadas para estados financieros.

Implementa:
- Márgenes (Gross, Operating, Net, EBITDA)
- YoY (Year over Year changes)
- FCF (Free Cash Flow) y derivados
- Métricas de balance (Net Debt, Book Value, etc.)
"""

from typing import List, Dict, Optional, Any

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class FinancialCalculator:
    """
    Calculadora de métricas financieras derivadas.
    
    Añade campos calculados a partir de datos base:
    - Márgenes de rentabilidad
    - Crecimientos interanuales
    - Free Cash Flow
    - Métricas de balance
    """
    
    def add_income_metrics(
        self,
        income_fields: List[Dict],
        cashflow_fields: List[Dict],
        num_periods: int
    ) -> List[Dict]:
        """
        Añadir métricas calculadas al income statement.
        """
        income_map = {f['key']: f for f in income_fields}
        cashflow_map = {f['key']: f for f in cashflow_fields}
        
        revenue = income_map.get('revenue', {}).get('values', [])
        cost_of_revenue = income_map.get('cost_of_revenue', {}).get('values', [])
        gross_profit = income_map.get('gross_profit', {}).get('values', [])
        operating_income = income_map.get('operating_income', {}).get('values', [])
        net_income = income_map.get('net_income', {}).get('values', [])
        ebitda = income_map.get('ebitda', {}).get('values', [])
        shares_basic = income_map.get('shares_basic', {}).get('values', [])
        dividends_paid = cashflow_map.get('dividends_paid', {}).get('values', [])
        
        # 0. CALCULAR GROSS PROFIT si no existe
        # Gross Profit = Revenue - Cost of Revenue
        if not gross_profit and revenue and cost_of_revenue:
            gross_profit = []
            for i in range(num_periods):
                rev = revenue[i] if i < len(revenue) else None
                cogs = cost_of_revenue[i] if i < len(cost_of_revenue) else None
                if rev is not None and cogs is not None:
                    # COGS puede ser negativo en XBRL (gasto), así que usamos abs
                    gross_profit.append(rev - abs(cogs))
                else:
                    gross_profit.append(None)
            
            if any(v is not None for v in gross_profit):
                income_fields.append({
                    'key': 'gross_profit',
                    'label': 'Gross Profit',
                    'values': gross_profit,
                    'importance': 9400,
                    'data_type': 'monetary',
                    'source_fields': ['revenue', 'cost_of_revenue'],
                    'calculated': True
                })
                # Actualizar el mapa
                income_map['gross_profit'] = {'values': gross_profit}
        
        # 1. MÁRGENES
        self._add_margin(income_fields, 'gross_margin', 'Gross Margin %', 
                        gross_profit, revenue, num_periods, 9350)
        
        self._add_margin(income_fields, 'operating_margin', 'Operating Margin %',
                        operating_income, revenue, num_periods, 7950)
        
        self._add_margin(income_fields, 'net_margin', 'Net Margin %',
                        net_income, revenue, num_periods, 5450)
        
        self._add_margin(income_fields, 'ebitda_margin', 'EBITDA Margin %',
                        ebitda, revenue, num_periods, 4550)
        
        # 2. YoY
        self._add_yoy(income_fields, 'revenue_yoy', 'Revenue % YoY',
                     revenue, num_periods, 9900)
        
        self._add_yoy(income_fields, 'gross_profit_yoy', 'Gross Profit % YoY',
                     gross_profit, num_periods, 9350)
        
        self._add_yoy(income_fields, 'operating_income_yoy', 'Operating Income % YoY',
                     operating_income, num_periods, 7900)
        
        self._add_yoy(income_fields, 'net_income_yoy', 'Net Income % YoY',
                     net_income, num_periods, 5400)
        
        eps = income_map.get('eps_diluted', {}).get('values', [])
        self._add_yoy(income_fields, 'eps_yoy', 'EPS % YoY',
                     eps, num_periods, 4850)
        
        # 3. DIVIDEND PER SHARE
        self._add_dps(income_fields, dividends_paid, shares_basic, num_periods)
        
        return income_fields
    
    def add_cashflow_metrics(
        self,
        income_fields: List[Dict],
        cashflow_fields: List[Dict],
        num_periods: int
    ) -> List[Dict]:
        """
        Añadir métricas de cash flow (FCF, FCF Margin, FCF per Share).
        """
        income_map = {f['key']: f for f in income_fields}
        cashflow_map = {f['key']: f for f in cashflow_fields}
        
        revenue = income_map.get('revenue', {}).get('values', [])
        shares_diluted = income_map.get('shares_diluted', {}).get('values', [])
        operating_cf = cashflow_map.get('operating_cf', {}).get('values', [])
        
        # Buscar CapEx en varios campos
        capex = self._find_capex(cashflow_map, num_periods)
        
        if not operating_cf or not capex:
            return cashflow_fields
        
        # FCF = Operating CF - |CapEx|
        fcf_values = []
        for i in range(num_periods):
            ocf = operating_cf[i] if i < len(operating_cf) else None
            cap = capex[i] if i < len(capex) else None
            if ocf is not None and cap is not None:
                fcf_values.append(ocf - abs(cap))
            else:
                fcf_values.append(None)
        
        if not any(v is not None for v in fcf_values):
            return cashflow_fields
        
        # Add FCF
        cashflow_fields.append({
            'key': 'free_cash_flow',
            'label': 'Free Cash Flow',
            'values': fcf_values,
            'importance': 9500,
            'data_type': 'monetary',
            'source_fields': ['operating_cf', 'capex'],
            'calculated': True
        })
        
        # FCF Margin %
        if revenue:
            fcf_margin = []
            for i in range(num_periods):
                fcf = fcf_values[i] if i < len(fcf_values) else None
                rev = revenue[i] if i < len(revenue) else None
                if fcf is not None and rev is not None and rev != 0:
                    fcf_margin.append(round(fcf / rev, 4))
                else:
                    fcf_margin.append(None)
            
            if any(v is not None for v in fcf_margin):
                cashflow_fields.append({
                    'key': 'fcf_margin',
                    'label': 'FCF Margin %',
                    'values': fcf_margin,
                    'importance': 9400,
                    'data_type': 'percent',
                    'source_fields': ['free_cash_flow', 'revenue'],
                    'calculated': True
                })
        
        # FCF per Share
        if shares_diluted:
            fcf_per_share = []
            for i in range(num_periods):
                fcf = fcf_values[i] if i < len(fcf_values) else None
                shares = shares_diluted[i] if i < len(shares_diluted) else None
                if fcf is not None and shares is not None and shares > 0:
                    fcf_per_share.append(round(fcf / shares, 2))
                else:
                    fcf_per_share.append(None)
            
            if any(v is not None for v in fcf_per_share):
                cashflow_fields.append({
                    'key': 'fcf_per_share',
                    'label': 'FCF per Share',
                    'values': fcf_per_share,
                    'importance': 9300,
                    'data_type': 'perShare',
                    'source_fields': ['free_cash_flow', 'shares_diluted'],
                    'calculated': True
                })
        
        return cashflow_fields
    
    def add_balance_metrics(
        self,
        balance_fields: List[Dict],
        income_fields: List[Dict],
        num_periods: int
    ) -> List[Dict]:
        """
        Añadir métricas de balance (Net Debt, Book Value, etc.)
        """
        balance_map = {f['key']: f for f in balance_fields}
        income_map = {f['key']: f for f in income_fields}
        
        # Corregir Total Equity si es incorrecto
        self._correct_total_equity(balance_map, num_periods)
        
        # Obtener valores base
        total_assets = balance_map.get('total_assets', {}).get('values', [])
        total_liabilities = balance_map.get('total_liabilities', {}).get('values', [])
        total_equity = balance_map.get('total_equity', {}).get('values', [])
        cash = balance_map.get('cash', {}).get('values', [])
        st_investments = balance_map.get('st_investments', {}).get('values', [])
        st_debt = balance_map.get('st_debt', {}).get('values', [])
        lt_debt = balance_map.get('lt_debt', {}).get('values', [])
        goodwill = balance_map.get('goodwill', {}).get('values', [])
        intangibles = balance_map.get('intangibles', {}).get('values', [])
        shares_basic = income_map.get('shares_basic', {}).get('values', [])
        
        # 1. Total Debt
        total_debt = self._calc_total_debt(st_debt, lt_debt, num_periods)
        if total_debt and 'total_debt' not in balance_map:
            balance_fields.append({
                'key': 'total_debt',
                'label': 'Total Debt',
                'values': total_debt,
                'importance': 3500,
                'data_type': 'monetary',
                'source_fields': ['st_debt', 'lt_debt'],
                'calculated': True
            })
        
        # 2. Net Debt
        if total_debt and cash:
            net_debt = []
            for i in range(num_periods):
                debt = total_debt[i] if i < len(total_debt) else None
                c = cash[i] if i < len(cash) else 0
                st_inv = st_investments[i] if st_investments and i < len(st_investments) else 0
                
                if debt is not None:
                    net_debt.append(debt - (c or 0) - (st_inv or 0))
                else:
                    net_debt.append(None)
            
            if any(v is not None for v in net_debt):
                balance_fields.append({
                    'key': 'net_debt',
                    'label': 'Net Debt',
                    'values': net_debt,
                    'importance': 3400,
                    'data_type': 'monetary',
                    'source_fields': ['total_debt', 'cash', 'st_investments'],
                    'calculated': True
                })
        
        # 3. Book Value per Share
        if total_equity and shares_basic:
            bvps = []
            for i in range(num_periods):
                equity = total_equity[i] if i < len(total_equity) else None
                shares = shares_basic[i] if i < len(shares_basic) else None
                
                if equity is not None and shares is not None and shares > 0:
                    bvps.append(round(equity / shares, 2))
                else:
                    bvps.append(None)
            
            if any(v is not None for v in bvps):
                balance_fields.append({
                    'key': 'book_value_per_share',
                    'label': 'Book Value / Share',
                    'values': bvps,
                    'importance': 3300,
                    'data_type': 'perShare',
                    'source_fields': ['total_equity', 'shares_basic'],
                    'calculated': True
                })
        
        # 4. Tangible Book Value
        if total_equity:
            tbv = []
            for i in range(num_periods):
                equity = total_equity[i] if i < len(total_equity) else None
                gw = goodwill[i] if goodwill and i < len(goodwill) else 0
                intang = intangibles[i] if intangibles and i < len(intangibles) else 0
                
                if equity is not None:
                    tbv.append(equity - (gw or 0) - (intang or 0))
                else:
                    tbv.append(None)
            
            if any(v is not None for v in tbv):
                balance_fields.append({
                    'key': 'tangible_book_value',
                    'label': 'Tangible Book Value',
                    'values': tbv,
                    'importance': 3200,
                    'data_type': 'monetary',
                    'source_fields': ['total_equity', 'goodwill', 'intangibles'],
                    'calculated': True
                })
                
                # Tangible Book Value per Share
                if shares_basic:
                    tbvps = []
                    for i in range(num_periods):
                        t = tbv[i] if i < len(tbv) else None
                        shares = shares_basic[i] if i < len(shares_basic) else None
                        
                        if t is not None and shares is not None and shares > 0:
                            tbvps.append(round(t / shares, 2))
                        else:
                            tbvps.append(None)
                    
                    if any(v is not None for v in tbvps):
                        balance_fields.append({
                            'key': 'tangible_book_value_per_share',
                            'label': 'Tangible Book Value / Share',
                            'values': tbvps,
                            'importance': 3100,
                            'data_type': 'perShare',
                            'source_fields': ['tangible_book_value', 'shares_basic'],
                            'calculated': True
                        })
        
        return balance_fields
    
    def recalculate_ebitda(
        self, 
        income_fields: List[Dict], 
        cashflow_fields: List[Dict],
        num_periods: int
    ) -> List[Dict]:
        """
        Recalcular EBITDA usando D&A de Cash Flow Statement.
        """
        income_map = {f['key']: f for f in income_fields}
        cashflow_map = {f['key']: f for f in cashflow_fields}
        
        op_income_field = income_map.get('operating_income')
        if not op_income_field:
            return income_fields
        
        op_income = op_income_field['values']
        
        # Buscar D&A en múltiples fuentes
        da_sources = [
            ('income', 'depreciation'),
            ('income', 'depreciation_expense'),
            ('income', 'depreciation_amortization'),
            ('cashflow', 'depreciation'),
            ('cashflow', 'depreciation_expense'),
            ('cashflow', 'depreciation_amortization'),
        ]
        
        da_values = [0] * num_periods
        da_source_found = None
        
        for source_type, field_key in da_sources:
            source_map = income_map if source_type == 'income' else cashflow_map
            da_field = source_map.get(field_key)
            
            if da_field and any(v is not None and v != 0 for v in da_field['values']):
                for i in range(min(num_periods, len(da_field['values']))):
                    if da_values[i] == 0 and da_field['values'][i] is not None:
                        da_values[i] = da_field['values'][i]
                        da_source_found = f"{source_type}:{field_key}"
        
        # EBITDA = Operating Income + |D&A|
        ebitda_values = []
        for i in range(num_periods):
            oi = op_income[i] if i < len(op_income) else None
            da = abs(da_values[i]) if da_values[i] else 0
            
            if oi is not None:
                ebitda_values.append(oi + da)
            else:
                ebitda_values.append(None)
        
        # Actualizar o añadir EBITDA
        if 'ebitda' in income_map:
            income_map['ebitda']['values'] = ebitda_values
            income_map['ebitda']['calculated'] = True
            if da_source_found:
                income_map['ebitda']['source_fields'] = ['operating_income', da_source_found]
        else:
            income_fields.append({
                'key': 'ebitda',
                'label': 'EBITDA',
                'values': ebitda_values,
                'importance': 4600,
                'source_fields': ['operating_income', da_source_found or 'depreciation'],
                'calculated': True
            })
        
        return income_fields
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _add_margin(
        self,
        fields: List[Dict],
        key: str,
        label: str,
        numerator: List,
        denominator: List,
        num_periods: int,
        importance: int
    ) -> None:
        """Añadir un campo de margen."""
        if not numerator or not denominator:
            return
        
        margin = []
        for i in range(num_periods):
            num = numerator[i] if i < len(numerator) else None
            den = denominator[i] if i < len(denominator) else None
            if num is not None and den is not None and den != 0:
                margin.append(round(num / den, 4))
            else:
                margin.append(None)
        
        if any(v is not None for v in margin):
            fields.append({
                'key': key,
                'label': label,
                'values': margin,
                'importance': importance,
                'data_type': 'percent',
                'calculated': True
            })
    
    def _add_yoy(
        self,
        fields: List[Dict],
        key: str,
        label: str,
        values: List,
        num_periods: int,
        importance: int
    ) -> None:
        """Añadir un campo YoY."""
        if not values or len(values) <= 1:
            return
        
        yoy = [None]
        for i in range(1, num_periods):
            curr = values[i] if i < len(values) else None
            prev = values[i - 1] if (i - 1) < len(values) else None
            if curr is not None and prev is not None and curr != 0:
                yoy.append(round((prev - curr) / abs(curr), 4))
            else:
                yoy.append(None)
        
        if any(v is not None for v in yoy):
            fields.append({
                'key': key,
                'label': label,
                'values': yoy,
                'importance': importance,
                'data_type': 'percent',
                'calculated': True
            })
    
    def _add_dps(
        self,
        fields: List[Dict],
        dividends_paid: List,
        shares_basic: List,
        num_periods: int
    ) -> None:
        """Añadir Dividend per Share."""
        if not dividends_paid or not shares_basic:
            return
        
        dps = []
        for i in range(num_periods):
            div = dividends_paid[i] if i < len(dividends_paid) else None
            shares = shares_basic[i] if i < len(shares_basic) else None
            if div is not None and shares is not None and shares > 0:
                dps.append(round(abs(div) / shares, 4))
            else:
                dps.append(None)
        
        if any(v is not None and v > 0 for v in dps):
            fields.append({
                'key': 'dividend_per_share',
                'label': 'Dividend per Share',
                'values': dps,
                'importance': 4750,
                'data_type': 'perShare',
                'calculated': True
            })
    
    def _find_capex(
        self,
        cashflow_map: Dict,
        num_periods: int
    ) -> List[Optional[float]]:
        """Buscar CapEx en varios campos posibles."""
        capex_candidates = ['ppe', 'capex', 'payments_property_plant', 'capital_expenditures']
        
        for field_name in capex_candidates:
            if field_name in cashflow_map:
                vals = cashflow_map[field_name].get('values', [])
                if vals:
                    max_val = max((abs(v) for v in vals if v is not None), default=0)
                    if max_val > 1e9:  # > $1B
                        return vals
        
        return []
    
    def _calc_total_debt(
        self,
        st_debt: List,
        lt_debt: List,
        num_periods: int
    ) -> Optional[List]:
        """Calcular Total Debt."""
        if not st_debt and not lt_debt:
            return None
        
        total = []
        for i in range(num_periods):
            st = st_debt[i] if st_debt and i < len(st_debt) and st_debt[i] is not None else 0
            lt = lt_debt[i] if lt_debt and i < len(lt_debt) and lt_debt[i] is not None else 0
            total.append(st + lt if (st or lt) else None)
        
        return total if any(v is not None for v in total) else None
    
    def _correct_total_equity(
        self,
        balance_map: Dict,
        num_periods: int
    ) -> None:
        """Corregir Total Equity si es igual a Total Assets (error común)."""
        total_assets = balance_map.get('total_assets', {}).get('values', [])
        total_liabilities = balance_map.get('total_liabilities', {}).get('values', [])
        total_equity = balance_map.get('total_equity', {}).get('values', [])
        
        if not total_equity or not total_assets or not total_liabilities:
            return
        
        corrected = False
        for i in range(min(len(total_equity), len(total_assets), len(total_liabilities))):
            eq = total_equity[i]
            assets = total_assets[i]
            liab = total_liabilities[i]
            
            if eq is not None and assets is not None and liab is not None:
                if assets > 0 and abs(eq - assets) / assets < 0.01:
                    total_equity[i] = assets - liab
                    corrected = True
        
        if corrected and 'total_equity' in balance_map:
            balance_map['total_equity']['values'] = total_equity
            balance_map['total_equity']['corrected'] = True

