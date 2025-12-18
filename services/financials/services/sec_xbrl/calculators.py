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
    
    @staticmethod
    def _deduplicate_fields(fields: List[Dict]) -> List[Dict]:
        """
        Remove duplicate fields, keeping the one with MORE valid data.
        For calculated fields that have data vs extracted fields with no data, prefer calculated.
        """
        seen = {}
        for field in fields:
            key = field.get('key')
            if key in seen:
                existing = seen[key]
                # Count non-null values
                existing_count = sum(1 for v in existing.get('values', []) if v is not None)
                new_count = sum(1 for v in field.get('values', []) if v is not None)
                
                # ALWAYS prefer the one with MORE data
                # If same count, prefer calculated=True (it was computed for a reason)
                if new_count > existing_count:
                    logger.debug(f"Deduplicate: replacing {key} (existing={existing_count} values) with new ({new_count} values)")
                    seen[key] = field
                elif new_count == existing_count and new_count > 0:
                    # Same count with data - prefer calculated (more recent/accurate)
                    if field.get('calculated', False) and not existing.get('calculated', False):
                        logger.debug(f"Deduplicate: replacing {key} with calculated version")
                        seen[key] = field
            else:
                seen[key] = field
        
        # Remove overlapping fields to avoid double-counting
        # If we have interest_investment_income, remove interest_income (it's included)
        if 'interest_investment_income' in seen and 'interest_income' in seen:
            del seen['interest_income']
        
        # If we have interest_and_other_income, also remove interest_income
        if 'interest_and_other_income' in seen and 'interest_income' in seen:
            del seen['interest_income']
        
        # If we have sga_expenses (combined), remove sales_marketing and ga_expenses
        # to avoid showing both the total and its components (like TIKR does)
        if 'sga_expenses' in seen:
            sga_has_data = any(v is not None for v in seen['sga_expenses'].get('values', []))
            if sga_has_data:
                if 'sales_marketing' in seen:
                    del seen['sales_marketing']
                if 'ga_expenses' in seen:
                    del seen['ga_expenses']
        
        return list(seen.values())
    
    @staticmethod
    def adjust_revenue_presentation(fields: List[Dict], industry: str) -> List[Dict]:
        """
        Adjust revenue presentation for proper hierarchical display.
        
        Handles two cases:
        1. Finance Division (CAT, GE, etc.) - estructura TIKR:
           - Revenues (productos/servicios)
           - Finance Div. Revenues
           - Total Revenues (subtotal)
        
        2. Interest Income (fintech, banking, crypto):
           - Operating Revenue
           - Interest & Investment Income
           - Total Revenue (subtotal)
        
        Returns modified fields list.
        """
        field_map = {f['key']: f for f in fields}
        revenue = field_map.get('revenue')
        
        if not revenue:
            return fields
        
        rev_vals = revenue.get('values', [])
        if not rev_vals or not rev_vals[0]:
            return fields
        
        # =====================================================================
        # CASE 1: Finance Division (CAT, GE, Ford, etc.)
        # =====================================================================
        finance_div = field_map.get('finance_division_revenue')
        if finance_div:
            fin_vals = finance_div.get('values', [])
            if fin_vals and any(v is not None for v in fin_vals):
                return FinancialCalculator._adjust_for_finance_division(fields, revenue, finance_div)
        
        # =====================================================================
        # CASE 2: Interest Income (fintech, banking, crypto)
        # =====================================================================
        interest_inv = field_map.get('interest_investment_income')
        if interest_inv:
            int_vals = interest_inv.get('values', [])
            if int_vals and int_vals[0]:
                # Check if interest income is significant (>3% of revenue)
                ratio = abs(int_vals[0]) / abs(rev_vals[0]) if rev_vals[0] != 0 else 0
                if ratio >= 0.03:
                    return FinancialCalculator._adjust_for_interest_income(fields, revenue, interest_inv)
        
            return fields
        
    @staticmethod
    def _adjust_for_finance_division(fields: List[Dict], revenue: Dict, finance_div: Dict) -> List[Dict]:
        """
        Adjust presentation for companies with Finance Division.
        
        TIKR Structure:
        - Revenues (de productos/servicios)    ← Operating Revenue (calculado)
        - Finance Div. Revenues                ← Extraído de segmentos
        - Total Revenues                       ← Subtotal (el revenue original del XBRL)
        """
        rev_vals = revenue.get('values', [])
        fin_vals = finance_div.get('values', [])
        num_periods = len(rev_vals)
        
        # Calculate Operating Revenue = Total Revenue - Finance Division
        operating_rev = []
        for i in range(num_periods):
            rv = rev_vals[i] if i < len(rev_vals) else None
            fv = fin_vals[i] if i < len(fin_vals) else None
            if rv is not None and fv is not None:
                operating_rev.append(rv - fv)
            elif rv is not None:
                operating_rev.append(rv)
            else:
                operating_rev.append(None)
        
        new_fields = []
        finance_div_added = False
        
        for f in fields:
            key = f.get('key')
            
            if key == 'revenue':
                # 1. Operating Revenue (Revenues de productos/servicios)
                new_fields.append({
                    'key': 'operating_revenue',
                    'label': 'Revenues',
                    'label_tooltip': 'Sales of machinery, engines, products and services',
                    'values': operating_rev,
                    'importance': 10100,
                    'data_type': 'monetary',
                    'source_fields': ['revenue - finance_division_revenue'],
                    'calculated': True,
                    'section': 'Revenue',
                    'display_order': 90,
                    'indent_level': 0,
                    'is_subtotal': False,
                })
                
                # 2. Finance Division Revenue
                new_fields.append({
                    'key': 'finance_division_revenue',
                    'label': 'Finance Div. Revenues',
                    'values': fin_vals,
                    'importance': 10050,
                    'data_type': 'monetary',
                    'source_fields': finance_div.get('source_fields', []),
                    'section': 'Revenue',
                    'display_order': 95,
                    'indent_level': 0,
                    'is_subtotal': False,
                })
                finance_div_added = True
                
                # 3. Total Revenue (subtotal)
                new_f = f.copy()
                new_f['key'] = 'total_revenue'
                new_f['label'] = 'Total Revenues'
                new_f['display_order'] = 100
                new_f['is_subtotal'] = True
                new_fields.append(new_f)
                
            elif key == 'finance_division_revenue':
                # Skip - already added above
                continue
                
            else:
                new_fields.append(f)
        
        return new_fields
    
    @staticmethod
    def _adjust_for_interest_income(fields: List[Dict], revenue: Dict, interest_inv: Dict) -> List[Dict]:
        """
        Adjust presentation for companies with significant Interest Income.
        
        Structure:
        - Operating Revenue
        - Interest & Investment Income
        - Total Revenue (subtotal)
        """
        rev_vals = revenue.get('values', [])
        int_vals = interest_inv.get('values', [])
        num_periods = len(rev_vals)
        
        # Calculate Operating Revenue = Total Revenue - Interest Income
        operating_rev = []
        for i in range(num_periods):
            rv = rev_vals[i] if i < len(rev_vals) else None
            iv = int_vals[i] if i < len(int_vals) else None
            if rv is not None and iv is not None:
                operating_rev.append(rv - iv)
            elif rv is not None:
                operating_rev.append(rv)
            else:
                operating_rev.append(None)
        
        new_fields = []
        
        for f in fields:
            key = f.get('key')
            
            if key == 'revenue':
                # 1. Operating Revenue
                new_fields.append({
                    'key': 'operating_revenue',
                    'label': 'Operating Revenue',
                    'values': operating_rev,
                    'importance': 10100,
                    'data_type': 'monetary',
                    'source_fields': ['revenue', 'interest_investment_income'],
                    'calculated': True,
                    'section': 'Revenue',
                    'display_order': 90,
                    'indent_level': 0,
                    'is_subtotal': False,
                })
                
                # 2. Interest Income
                new_fields.append({
                    'key': 'interest_income_revenue',
                    'label': 'Interest & Investment Income',
                    'values': int_vals,
                    'importance': 10050,
                    'data_type': 'monetary',
                    'source_fields': interest_inv.get('source_fields', []),
                    'section': 'Revenue',
                    'display_order': 95,
                    'indent_level': 0,
                    'is_subtotal': False,
                })
                
                # 3. Total Revenue (subtotal)
                new_f = f.copy()
                new_f['key'] = 'total_revenue'
                new_f['label'] = 'Total Revenue'
                new_f['display_order'] = 100
                new_f['is_subtotal'] = True
                new_fields.append(new_f)
                
            elif key == 'interest_investment_income':
                # Skip - already added to Revenue section
                continue
                
            else:
                new_fields.append(f)
        
        return new_fields
    
    def add_income_metrics(
        self,
        income_fields: List[Dict],
        cashflow_fields: List[Dict],
        num_periods: int,
        industry: Optional[str] = None
    ) -> List[Dict]:
        """
        Añadir métricas calculadas al income statement.
        
        Args:
            income_fields: Campos del income statement
            cashflow_fields: Campos del cash flow (para SBC, etc.)
            num_periods: Número de períodos
            industry: Industria detectada (para fórmulas específicas)
        
        Industry-specific calculations:
        - manufacturing_finance: Gross Profit = Revenue - COGS - Finance Div Op Exp - Interest Exp Finance
        - standard: Gross Profit = Revenue - COGS
        """
        income_map = {f['key']: f for f in income_fields}
        cashflow_map = {f['key']: f for f in cashflow_fields}
        
        # FIX: Stock compensation puede tener valores incorrectos (ratios de impuestos)
        # Si los valores son muy pequeños (<1000), usar el valor del Cash Flow
        income_sbc = income_map.get('stock_compensation', {}).get('values', [])
        cashflow_sbc = cashflow_map.get('stock_compensation', {}).get('values', [])
        
        if cashflow_sbc:
            # Verificar si income_sbc tiene valores incorrectos (ratios < 1 o muy pequeños)
            income_sbc_seems_wrong = all(
                v is None or (isinstance(v, (int, float)) and abs(v) < 1000)
                for v in income_sbc[:num_periods]
            ) if income_sbc else True
            
            if income_sbc_seems_wrong:
                # Usar valores del Cash Flow
                for f in income_fields:
                    if f.get('key') == 'stock_compensation':
                        f['values'] = cashflow_sbc[:num_periods]
                        f['source_fields'] = ['ShareBasedCompensation (from Cash Flow)']
                        f['calculated'] = True
                        income_map['stock_compensation'] = f
                        break
                else:
                    # Si no existe en income, agregar desde cash flow
                    if any(v is not None for v in cashflow_sbc[:num_periods]):
                        new_field = {
                            'key': 'stock_compensation',
                            'label': 'Stock-Based Compensation',
                            'values': cashflow_sbc[:num_periods],
                            'importance': 8400,
                            'data_type': 'monetary',
                            'source_fields': ['ShareBasedCompensation (from Cash Flow)'],
                            'calculated': True
                        }
                        income_fields.append(new_field)
                        income_map['stock_compensation'] = new_field
        
        # Revenue puede estar como 'revenue' o 'total_revenue' (si adjust_revenue_presentation ya se ejecutó)
        revenue = income_map.get('revenue', {}).get('values', [])
        if not revenue or not any(v is not None for v in revenue):
            revenue = income_map.get('total_revenue', {}).get('values', [])
        cost_of_revenue = income_map.get('cost_of_revenue', {}).get('values', [])
        gross_profit = income_map.get('gross_profit', {}).get('values', [])
        operating_income = income_map.get('operating_income', {}).get('values', [])
        net_income = income_map.get('net_income', {}).get('values', [])
        ebitda = income_map.get('ebitda', {}).get('values', [])
        shares_basic = income_map.get('shares_basic', {}).get('values', [])
        dividends_paid = cashflow_map.get('dividends_paid', {}).get('values', [])
        
        # -1. CALCULAR COST OF REVENUE si no existe
        # Algunas empresas (ej: ORCL) reportan COGS desglosado por segmento
        if not cost_of_revenue or not any(v is not None for v in cost_of_revenue):
            cogs_components = [
                income_map.get('cloud_services_and_license_support_expenses', {}).get('values', []),
                income_map.get('hardware_expenses', {}).get('values', []),
                income_map.get('services_expense', {}).get('values', []),
                income_map.get('cost_of_services', {}).get('values', []),
                income_map.get('cost_of_goods_sold', {}).get('values', []),
            ]
            
            # Verificar si hay componentes válidos
            has_components = any(
                any(v is not None for v in comp) 
                for comp in cogs_components if comp
            )
            
            if has_components:
                cost_of_revenue = []
                for i in range(num_periods):
                    total = 0
                    has_value = False
                    for comp in cogs_components:
                        if comp and i < len(comp) and comp[i] is not None:
                            total += abs(comp[i])  # COGS típicamente positivo
                            has_value = True
                    cost_of_revenue.append(total if has_value else None)
                
                if any(v is not None for v in cost_of_revenue):
                    income_fields.append({
                        'key': 'cost_of_revenue',
                        'label': 'Cost of Revenue',
                        'values': cost_of_revenue,
                        'importance': 9500,
                        'data_type': 'monetary',
                        'source_fields': ['cloud_services_and_license_support_expenses', 'hardware_expenses', 'services_expense'],
                        'calculated': True
                    })
                    income_map['cost_of_revenue'] = {'values': cost_of_revenue}
        
        # 0. CALCULAR/COMPLETAR GROSS PROFIT
        # Re-leer cost_of_revenue del mapa en caso de que se haya calculado arriba
        cost_of_revenue = income_map.get('cost_of_revenue', {}).get('values', [])
        cost_of_revenue_has_values = cost_of_revenue and any(v is not None for v in cost_of_revenue)
        
        # Get Finance Division costs (for manufacturing_finance industry)
        finance_div_op_exp = income_map.get('finance_div_operating_exp', {}).get('values', [])
        interest_exp_finance = income_map.get('interest_expense_finance_div', {}).get('values', [])
        has_finance_div_costs = (
            (finance_div_op_exp and any(v is not None for v in finance_div_op_exp)) or
            (interest_exp_finance and any(v is not None for v in interest_exp_finance))
        )
        
        # Determine if we should use Finance Division formula
        # TIKR/Bloomberg method: if Finance Div costs exist, use extended formula
        use_finance_div_formula = has_finance_div_costs and industry in ('manufacturing_finance', None)
        
        # Calcular Gross Profit POR PERÍODO (no todo o nada)
        # Algunas empresas dejan de reportar GrossProfit en años recientes
        if revenue and cost_of_revenue_has_values:
            calculated_gp = []
            needs_update = False
            
            for i in range(num_periods):
                existing_gp = gross_profit[i] if gross_profit and i < len(gross_profit) else None
                rev = revenue[i] if i < len(revenue) else None
                cogs = cost_of_revenue[i] if i < len(cost_of_revenue) else None
                
                # For companies with Finance Division, recalculate even if XBRL has a value
                # because their reported Gross Profit may not include Finance Div costs
                should_recalculate = use_finance_div_formula and rev is not None and cogs is not None
                
                if should_recalculate:
                    # TIKR Formula for Manufacturing with Finance Division:
                    # Gross Profit = Total Revenue - COGS - Finance Div Op Exp - Interest Exp Finance
                    fin_op = finance_div_op_exp[i] if finance_div_op_exp and i < len(finance_div_op_exp) and finance_div_op_exp[i] else 0
                    fin_int = interest_exp_finance[i] if interest_exp_finance and i < len(interest_exp_finance) and interest_exp_finance[i] else 0
                    
                    gp = rev - abs(cogs) - abs(fin_op) - abs(fin_int)
                    calculated_gp.append(gp)
                    needs_update = True
                    logger.debug(f"Gross Profit[{i}] = {rev/1e6:.0f}M - {abs(cogs)/1e6:.0f}M - {abs(fin_op)/1e6:.0f}M - {abs(fin_int)/1e6:.0f}M = {gp/1e6:.0f}M")
                elif existing_gp is not None:
                    # Usar valor existente del XBRL
                    calculated_gp.append(existing_gp)
                elif rev is not None and cogs is not None:
                    # Standard formula: Revenue - COGS
                    calculated_gp.append(rev - abs(cogs))
                    needs_update = True
                else:
                    calculated_gp.append(None)
            
            if needs_update and any(v is not None for v in calculated_gp):
                # Actualizar o agregar el campo gross_profit
                gp_field = next((f for f in income_fields if f['key'] == 'gross_profit'), None)
                
                source_fields = ['revenue', 'cost_of_revenue']
                if use_finance_div_formula:
                    source_fields.extend(['finance_div_operating_exp', 'interest_expense_finance_div'])
                
                if gp_field:
                    gp_field['values'] = calculated_gp
                    gp_field['calculated'] = True
                    gp_field['source_fields'] = source_fields
                else:
                    income_fields.append({
                        'key': 'gross_profit',
                        'label': 'Gross Profit',
                        'values': calculated_gp,
                        'importance': 9400,
                        'data_type': 'monetary',
                        'source_fields': source_fields,
                        'calculated': True
                    })
                income_map['gross_profit'] = {'values': calculated_gp}
                gross_profit = calculated_gp  # Actualizar variable local para uso posterior
        
        # 0.45. AJUSTAR TOTAL OPERATING EXPENSES (excluir COGS)
        # TIKR y otros calculan: Total OpEx = Raw OpEx - COGS
        # Porque COGS se muestra arriba de Gross Profit, no en OpEx
        total_op_exp_raw = income_map.get('total_operating_expenses', {}).get('values', [])
        cogs = income_map.get('cost_of_revenue', {}).get('values', [])
        
        if total_op_exp_raw and cogs:
            adjusted_opex = []
            for i in range(num_periods):
                opex_v = total_op_exp_raw[i] if i < len(total_op_exp_raw) and total_op_exp_raw[i] else None
                cogs_v = cogs[i] if i < len(cogs) and cogs[i] else 0
                if opex_v is not None:
                    # Restar COGS del Total Operating Expenses
                    adjusted_opex.append(opex_v - abs(cogs_v))
                else:
                    adjusted_opex.append(None)
            
            # Actualizar el campo total_operating_expenses
            for f in income_fields:
                if f.get('key') == 'total_operating_expenses':
                    f['values'] = adjusted_opex
                    f['source_fields'] = f.get('source_fields', []) + ['(adjusted: - cost_of_revenue)']
                    f['calculated'] = True
                    income_map['total_operating_expenses'] = {'values': adjusted_opex}
                    break
        
        total_op_exp = income_map.get('total_operating_expenses', {}).get('values', [])
        
        # 0.5. CALCULAR OPERATING INCOME si no existe
        # Operating Income = Revenue - Total Operating Expenses
        if not operating_income and revenue and total_op_exp:
            operating_income = []
            for i in range(num_periods):
                rev = revenue[i] if i < len(revenue) else None
                opex = total_op_exp[i] if i < len(total_op_exp) else None
                if rev is not None and opex is not None:
                    # Operating Expenses suele ser positivo en XBRL
                    operating_income.append(rev - abs(opex))
                else:
                    operating_income.append(None)
            
            if any(v is not None for v in operating_income):
                income_fields.append({
                    'key': 'operating_income',
                    'label': 'Operating Income',
                    'values': operating_income,
                    'importance': 8000,
                    'data_type': 'monetary',
                    'source_fields': ['revenue', 'total_operating_expenses'],
                    'calculated': True
                })
                income_map['operating_income'] = {'values': operating_income}
        
        # 0.6. CALCULAR REVENUE BEFORE PROVISION (para Banking/Brokerage)
        # Solo si hay net_interest_income (indica que es financial)
        net_interest = income_map.get('net_interest_income', {}).get('values', [])
        provision = income_map.get('provision_bad_debts', {}).get('values', []) or \
                   income_map.get('provision_for_loan_losses', {}).get('values', [])
        
        if net_interest and revenue and not income_map.get('revenue_before_provision'):
            rev_before_prov = []
            for i in range(num_periods):
                rev = revenue[i] if i < len(revenue) else None
                prov = provision[i] if provision and i < len(provision) else 0
                if rev is not None:
                    # Revenue Before Provision = Total Revenue (provision se resta después)
                    rev_before_prov.append(rev)
                else:
                    rev_before_prov.append(None)
            
            if any(v is not None for v in rev_before_prov):
                income_fields.append({
                    'key': 'revenue_before_provision',
                    'label': 'Revenues Before Provision',
                    'values': rev_before_prov,
                    'importance': 9200,
                    'data_type': 'monetary',
                    'source_fields': ['revenue'],
                    'calculated': True
                })
        
        # 0.9. CALCULAR SG&A COMBINADO si no existe
        # SG&A = Sales & Marketing + G&A
        sga = income_map.get('sga_expenses', {}).get('values', [])
        sales_marketing = income_map.get('sales_marketing', {}).get('values', [])
        ga_expenses = income_map.get('ga_expenses', {}).get('values', [])
        
        if (not sga or not any(v is not None for v in sga)) and sales_marketing and ga_expenses:
            calculated_sga = []
            for i in range(num_periods):
                sm = sales_marketing[i] if i < len(sales_marketing) and sales_marketing[i] else 0
                ga = ga_expenses[i] if i < len(ga_expenses) and ga_expenses[i] else 0
                if sm or ga:
                    calculated_sga.append(sm + ga)
                else:
                    calculated_sga.append(None)
            
            if any(v is not None for v in calculated_sga):
                income_fields.append({
                    'key': 'sga_expenses',
                    'label': 'Selling, General & Admin',
                    'values': calculated_sga,
                    'importance': 8750,
                    'data_type': 'monetary',
                    'source_fields': ['sales_marketing', 'ga_expenses'],
                    'calculated': True
                })
                income_map['sga_expenses'] = {'values': calculated_sga}
                
                # Marcar sales_marketing y ga_expenses para eliminación
                # (evitar mostrar breakdown cuando SG&A combinado existe)
                for f in income_fields:
                    if f['key'] in ('sales_marketing', 'ga_expenses'):
                        f['_hide_when_sga_exists'] = True
        
        # 0.95. RECLASIFICAR AMORTIZATION OF INTANGIBLES
        # El tag AmortizationOfIntangibleAssets se mapea a 'intangibles' pero debe estar en OpEx
        intangibles_field = next((f for f in income_fields if f['key'] == 'intangibles'), None)
        if intangibles_field and any(v is not None for v in intangibles_field.get('values', [])):
            # Crear nuevo campo con nombre correcto
            if not any(f['key'] == 'amortization_intangibles' for f in income_fields):
                amort_int_values = intangibles_field['values'].copy()
                income_fields.append({
                    'key': 'amortization_intangibles',
                    'label': 'Amortization of Intangibles',
                    'values': amort_int_values,
                    'importance': 8650,
                    'data_type': 'monetary',
                    'source_fields': intangibles_field.get('source_fields', ['AmortizationOfIntangibleAssets']),
                    'calculated': True
                })
                # También agregar al income_map para que esté disponible en cálculo de EBITDA
                income_map['amortization_intangibles'] = {'values': amort_int_values}
        
        # 0.96. RECALCULAR TOTAL OPERATING EXPENSES como suma de componentes (como TIKR)
        # Total OpEx = SG&A + R&D + Amort + Other
        # Esto es más preciso que usar el tag CostsAndExpenses que puede incluir más cosas
        sga_vals = income_map.get('sga_expenses', {}).get('values', [])
        rd_vals = income_map.get('rd_expenses', {}).get('values', [])
        amort_vals = income_map.get('amortization_intangibles', {}).get('values', [])
        other_opex = income_map.get('other_operating_expenses', {}).get('values', [])
        
        # Si tenemos los componentes principales, recalcular Total OpEx
        if sga_vals and rd_vals:
            calculated_total = []
            for i in range(num_periods):
                s = abs(sga_vals[i]) if i < len(sga_vals) and sga_vals[i] else 0
                r = abs(rd_vals[i]) if i < len(rd_vals) and rd_vals[i] else 0
                a = abs(amort_vals[i]) if i < len(amort_vals) and amort_vals[i] else 0
                o = abs(other_opex[i]) if i < len(other_opex) and other_opex[i] else 0
                
                if s or r:  # Al menos uno debe existir
                    calculated_total.append(s + r + a + o)
                else:
                    calculated_total.append(None)
            
            if any(v is not None for v in calculated_total):
                # Actualizar el campo existente o crear uno nuevo
                for f in income_fields:
                    if f['key'] == 'total_operating_expenses':
                        f['values'] = calculated_total
                        f['calculated'] = True
                        f['source_fields'] = ['sga_expenses', 'rd_expenses', 'amortization_intangibles', 'other_operating_expenses']
                        break
                else:
                    income_fields.append({
                        'key': 'total_operating_expenses',
                        'label': 'Total Operating Expenses',
                        'values': calculated_total,
                        'importance': 8500,
                        'data_type': 'monetary',
                        'source_fields': ['sga_expenses', 'rd_expenses', 'amortization_intangibles'],
                        'calculated': True
                    })
                income_map['total_operating_expenses'] = {'values': calculated_total}
        
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
        
        # Net Interest Income YoY (para banking)
        self._add_yoy(income_fields, 'net_interest_income_yoy', '% Change YoY',
                     net_interest, num_periods, 9050)
        
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
        
        # 4. EBT EXCL. UNUSUAL ITEMS (para banking especialmente)
        self._add_ebt_calculations(income_fields, income_map, num_periods)
        
        # 5. EARNINGS FROM CONTINUING OPERATIONS
        self._add_earnings_continuing(income_fields, income_map, num_periods)
        
        # 6. PAYOUT RATIO
        self._add_payout_ratio(income_fields, income_map, dividends_paid, num_periods)
        
        # 7. DEDUPLICATE
        deduplicated = self._deduplicate_fields(income_fields)
        
        return deduplicated
    
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
        
        return self._deduplicate_fields(cashflow_fields)
    
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
        
        # Corregir campos problemáticos antes de calcular métricas
        self._normalize_cash_field(balance_fields, balance_map, num_periods)
        self._normalize_total_liabilities(balance_fields, balance_map, num_periods)
        
        # Reconstruir el mapa después de las correcciones
        balance_map = {f['key']: f for f in balance_fields}
        
        # Corregir Total Equity si es incorrecto
        self._correct_total_equity(balance_map, num_periods)
        
        # Obtener valores base
        total_assets = balance_map.get('total_assets', {}).get('values', [])
        total_liabilities = balance_map.get('total_liabilities', {}).get('values', [])
        total_equity = balance_map.get('total_equity', {}).get('values', [])
        cash = balance_map.get('cash', {}).get('values', [])
        restricted_cash = balance_map.get('restricted_cash', {}).get('values', [])
        st_investments = balance_map.get('st_investments', {}).get('values', [])
        receivables = balance_map.get('receivables', {}).get('values', [])
        other_receivables = balance_map.get('other_receivables', {}).get('values', [])
        st_debt = balance_map.get('st_debt', {}).get('values', [])
        lt_debt = balance_map.get('lt_debt', {}).get('values', [])
        capital_leases = balance_map.get('capital_leases', {}).get('values', [])
        current_portion_capital_lease = balance_map.get('current_portion_capital_lease', {}).get('values', [])
        goodwill = balance_map.get('goodwill', {}).get('values', [])
        intangibles = balance_map.get('intangibles', {}).get('values', [])
        noncontrolling_interest = balance_map.get('noncontrolling_interest', {}).get('values', [])
        shares_basic = income_map.get('shares_basic', {}).get('values', [])
        
        # === TIKR-STYLE CALCULATED SUBTOTALS ===
        
        # Total Cash & Short-Term Investments
        if cash or st_investments:
            total_cash_st = []
            for i in range(num_periods):
                c = cash[i] if cash and i < len(cash) else 0
                rc = restricted_cash[i] if restricted_cash and i < len(restricted_cash) else 0
                st = st_investments[i] if st_investments and i < len(st_investments) else 0
                
                val = (c or 0) + (rc or 0) + (st or 0)
                total_cash_st.append(val if val > 0 else None)
            
            if any(v is not None for v in total_cash_st):
                balance_fields.append({
                    'key': 'total_cash_st_investments',
                    'label': 'Total Cash & Short-Term Investments',
                    'values': total_cash_st,
                    'importance': 9350,
                    'data_type': 'monetary',
                    'source_fields': ['cash', 'restricted_cash', 'st_investments'],
                    'calculated': True
                })
        
        # Total Receivables
        if receivables:
            total_recv = []
            for i in range(num_periods):
                r = receivables[i] if i < len(receivables) else 0
                other = other_receivables[i] if other_receivables and i < len(other_receivables) else 0
                
                val = (r or 0) + (other or 0)
                total_recv.append(val if val > 0 else None)
            
            if any(v is not None for v in total_recv):
                balance_fields.append({
                    'key': 'total_receivables',
                    'label': 'Total Receivables',
                    'values': total_recv,
                    'importance': 9180,
                    'data_type': 'monetary',
                    'source_fields': ['receivables', 'other_receivables'],
                    'calculated': True
                })
        
        # Total Common Equity (Total Equity - Noncontrolling Interest)
        if total_equity:
            common_equity = []
            for i in range(num_periods):
                eq = total_equity[i] if i < len(total_equity) else None
                nci = noncontrolling_interest[i] if noncontrolling_interest and i < len(noncontrolling_interest) else 0
                
                if eq is not None:
                    common_equity.append(eq - (nci or 0))
                else:
                    common_equity.append(None)
            
            if any(v is not None for v in common_equity):
                balance_fields.append({
                    'key': 'total_common_equity',
                    'label': 'Total Common Equity',
                    'values': common_equity,
                    'importance': 6000,
                    'data_type': 'monetary',
                    'source_fields': ['total_equity', 'noncontrolling_interest'],
                    'calculated': True
                })
        
        # Si no tenemos total_liabilities, calcularlo como total_assets - total_equity
        total_liabilities_calc = total_liabilities if total_liabilities and any(v is not None for v in total_liabilities) else None
        if not total_liabilities_calc and total_assets and total_equity:
            total_liabilities_calc = []
            for i in range(num_periods):
                assets = total_assets[i] if i < len(total_assets) else None
                eq = total_equity[i] if i < len(total_equity) else None
                
                if assets is not None and eq is not None:
                    total_liabilities_calc.append(assets - eq)
                else:
                    total_liabilities_calc.append(None)
            
            if any(v is not None for v in total_liabilities_calc) and 'total_liabilities' not in balance_map:
                balance_fields.append({
                    'key': 'total_liabilities',
                    'label': 'Total Liabilities',
                    'values': total_liabilities_calc,
                    'importance': 7700,
                    'data_type': 'monetary',
                    'source_fields': ['total_assets', 'total_equity'],
                    'calculated': True
                })
        
        # Total Liabilities And Equity (usar calculado si no existe)
        total_liab_for_le = total_liabilities_calc if total_liabilities_calc else total_liabilities
        if total_liab_for_le and total_equity:
            total_le = []
            for i in range(num_periods):
                liab = total_liab_for_le[i] if i < len(total_liab_for_le) else None
                eq = total_equity[i] if i < len(total_equity) else None
                
                if liab is not None and eq is not None:
                    total_le.append(liab + eq)
                else:
                    total_le.append(None)
            
            if any(v is not None for v in total_le) and 'total_liabilities_equity' not in balance_map:
                balance_fields.append({
                    'key': 'total_liabilities_equity',
                    'label': 'Total Liabilities And Equity',
                    'values': total_le,
                    'importance': 6700,
                    'data_type': 'monetary',
                    'source_fields': ['total_liabilities', 'total_equity'],
                    'calculated': True
                })
        
        # 1. Total Debt (including Capital Leases)
        total_debt = self._calc_total_debt(
            st_debt, lt_debt, capital_leases, current_portion_capital_lease, num_periods
        )
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
        
        return self._deduplicate_fields(balance_fields)
    
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
        
        # EBITDA = Operating Income + |D&A| + Amortization of Intangibles
        # (Algunas empresas como ORCL reportan amortización de intangibles por separado)
        amort_intangibles_field = income_map.get('amortization_intangibles')
        amort_intangibles = amort_intangibles_field.get('values', []) if amort_intangibles_field else []
        
        # También buscar en 'intangibles' si 'amortization_intangibles' no existe
        if not amort_intangibles or not any(v is not None and v != 0 for v in amort_intangibles):
            intangibles_field = income_map.get('intangibles')
            if intangibles_field:
                amort_intangibles = intangibles_field.get('values', [])
        
        ebitda_values = []
        ebitda_sources = ['operating_income']
        
        for i in range(num_periods):
            oi = op_income[i] if i < len(op_income) else None
            da = abs(da_values[i]) if da_values[i] else 0
            amort = abs(amort_intangibles[i]) if i < len(amort_intangibles) and amort_intangibles[i] else 0
            
            if oi is not None:
                ebitda_values.append(oi + da + amort)
            else:
                ebitda_values.append(None)
        
        if da_source_found:
            ebitda_sources.append(da_source_found)
        if any(v is not None and v != 0 for v in amort_intangibles):
            ebitda_sources.append('amortization_intangibles')
        
        # Actualizar o añadir EBITDA
        if 'ebitda' in income_map:
            income_map['ebitda']['values'] = ebitda_values
            income_map['ebitda']['calculated'] = True
            income_map['ebitda']['source_fields'] = ebitda_sources
        else:
            income_fields.append({
                'key': 'ebitda',
                'label': 'EBITDA',
                'values': ebitda_values,
                'importance': 4600,
                'source_fields': ebitda_sources,
                'calculated': True
            })
        
        # Add EBITDA YoY
        if any(v is not None for v in ebitda_values):
            ebitda_yoy = self._calculate_yoy(ebitda_values, num_periods)
            if any(v is not None for v in ebitda_yoy):
                income_fields.append({
                    'key': 'ebitda_yoy',
                    'label': 'EBITDA % YoY',
                    'values': ebitda_yoy,
                    'importance': 4550,
                    'data_type': 'percent',
                    'source_fields': ['ebitda'],
                    'calculated': True
                })
        
        # Add EBITDAR (EBITDA + Rent)
        rent_field = income_map.get('rent_expense') or cashflow_map.get('rent_expense')
        if rent_field:
            rent_values = rent_field.get('values', [])
            ebitdar_values = []
            for i in range(num_periods):
                eb = ebitda_values[i] if i < len(ebitda_values) else None
                rent = abs(rent_values[i]) if i < len(rent_values) and rent_values[i] else 0
                if eb is not None:
                    ebitdar_values.append(eb + rent)
                else:
                    ebitdar_values.append(None)
            
            if any(v is not None for v in ebitdar_values):
                income_fields.append({
                    'key': 'ebitdar',
                    'label': 'EBITDAR',
                    'values': ebitdar_values,
                    'importance': 4500,
                    'source_fields': ['ebitda', 'rent_expense'],
                    'calculated': True
                })
        
        return self._deduplicate_fields(income_fields)
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    @staticmethod
    def _calculate_yoy(values: List, num_periods: int) -> List:
        """Calculate Year-over-Year change as percentage."""
        yoy = [None]  # First period has no YoY
        for i in range(1, num_periods):
            curr = values[i] if i < len(values) else None
            prev = values[i-1] if i-1 < len(values) else None
            
            if curr is not None and prev is not None and prev != 0:
                yoy.append((curr - prev) / abs(prev))
            else:
                yoy.append(None)
        
        return yoy
    
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
    
    def _add_ebt_calculations(
        self,
        fields: List[Dict],
        income_map: Dict,
        num_periods: int
    ) -> None:
        """
        Calcular EBT Excl. Unusual Items.
        EBT Excl. = Operating Income + Other Non-Operating
        (antes de items inusuales como legal settlements, restructuring, etc.)
        """
        operating_income = income_map.get('operating_income', {}).get('values', [])
        income_before_tax = income_map.get('income_before_tax', {}).get('values', [])
        
        # Si ya existe EBT excl, no calcular
        if income_map.get('ebt_excl_unusual', {}).get('values'):
            return
        
        # Items inusuales que se restan de EBT
        unusual_keys = [
            'legal_settlements', 'restructuring_charges', 'asset_writedown',
            'merger_restructuring', 'other_unusual_items', 
            'business_combination_integration_related_costs'
        ]
        
        # Sumar todos los items inusuales
        unusual_total = [0] * num_periods
        for key in unusual_keys:
            vals = income_map.get(key, {}).get('values', [])
            if vals:
                for i in range(min(num_periods, len(vals))):
                    if vals[i] is not None:
                        unusual_total[i] += vals[i]
        
        # Si tenemos income_before_tax, calcular EBT excl = EBT + |unusual_items|
        # TIKR siempre muestra EBT Excl. incluso si no hay unusual items (en ese caso EBT Excl = EBT Incl)
        if income_before_tax:
            ebt_excl = []
            has_unusual = any(u != 0 for u in unusual_total)
            
            for i in range(num_periods):
                ebt = income_before_tax[i] if i < len(income_before_tax) else None
                unusual = unusual_total[i] if i < len(unusual_total) else 0
                
                if ebt is not None:
                    # Items inusuales negativos reducen EBT, así que sumamos su abs para "excluirlos"
                    # Si no hay unusual items, EBT Excl = EBT Incl
                    ebt_excl.append(ebt + abs(unusual))
                else:
                    ebt_excl.append(None)
            
            if any(v is not None for v in ebt_excl):
                fields.append({
                    'key': 'ebt_excl_unusual',
                    'label': 'EBT Excl. Unusual Items',
                    'values': ebt_excl,
                    'importance': 6100,
                    'data_type': 'monetary',
                    'source_fields': ['income_before_tax'] + (unusual_keys if has_unusual else []),
                    'calculated': True
                })
    
    def _add_earnings_continuing(
        self,
        fields: List[Dict],
        income_map: Dict,
        num_periods: int
    ) -> None:
        """
        Calcular Earnings From Continuing Operations.
        = Income Before Tax - Income Tax
        """
        # Si ya existe, no calcular
        if income_map.get('income_continuing_ops', {}).get('values'):
            return
        
        income_before_tax = income_map.get('income_before_tax', {}).get('values', [])
        income_tax = income_map.get('income_tax', {}).get('values', [])
        
        if not income_before_tax or not income_tax:
            return
        
        earnings_cont = []
        for i in range(num_periods):
            ebt = income_before_tax[i] if i < len(income_before_tax) else None
            tax = income_tax[i] if i < len(income_tax) else None
            
            if ebt is not None and tax is not None:
                # Tax puede ser negativo (beneficio) o positivo (gasto)
                # Si tax es positivo, es gasto y se resta
                # Si tax es negativo, es beneficio
                earnings_cont.append(ebt - abs(tax))
            else:
                earnings_cont.append(None)
        
        if any(v is not None for v in earnings_cont):
            fields.append({
                'key': 'income_continuing_ops',
                'label': 'Earnings From Continuing Operations',
                'values': earnings_cont,
                'importance': 5700,
                'data_type': 'monetary',
                'source_fields': ['income_before_tax', 'income_tax'],
                'calculated': True
            })
    
    def _add_payout_ratio(
        self,
        fields: List[Dict],
        income_map: Dict,
        dividends_paid: List,
        num_periods: int
    ) -> None:
        """
        Calcular Payout Ratio %.
        = Dividends Paid / Net Income to Common
        """
        net_income_common = income_map.get('net_income_to_common', {}).get('values', [])
        
        if not dividends_paid or not net_income_common:
            return
        
        payout = []
        for i in range(num_periods):
            div = dividends_paid[i] if i < len(dividends_paid) else None
            net = net_income_common[i] if i < len(net_income_common) else None
            
            if div is not None and net is not None and net > 0:
                # Dividends pagados suelen ser negativos en CF
                payout.append(round(abs(div) / net, 4))
            else:
                payout.append(None)
        
        if any(v is not None for v in payout):
            fields.append({
                'key': 'payout_ratio',
                'label': 'Payout Ratio %',
                'values': payout,
                'importance': 4700,
                'data_type': 'percent',
                'source_fields': ['dividends_paid', 'net_income_to_common'],
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
        capital_leases: List = None,
        current_portion_capital_lease: List = None,
        num_periods: int = 0
    ) -> Optional[List]:
        """
        Calcular Total Debt incluyendo Capital Leases.
        Total Debt = ST Debt + LT Debt + Capital Leases (current + noncurrent)
        """
        if not st_debt and not lt_debt and not capital_leases:
            return None
        
        total = []
        for i in range(num_periods):
            st = st_debt[i] if st_debt and i < len(st_debt) and st_debt[i] is not None else 0
            lt = lt_debt[i] if lt_debt and i < len(lt_debt) and lt_debt[i] is not None else 0
            cl = capital_leases[i] if capital_leases and i < len(capital_leases) and capital_leases[i] is not None else 0
            cl_curr = current_portion_capital_lease[i] if current_portion_capital_lease and i < len(current_portion_capital_lease) and current_portion_capital_lease[i] is not None else 0
            
            debt = st + lt + cl + cl_curr
            total.append(debt if debt > 0 else None)
        
        return total if any(v is not None for v in total) else None
    
    def _normalize_cash_field(
        self,
        balance_fields: List[Dict],
        balance_map: Dict,
        num_periods: int
    ) -> None:
        """
        Normalizar el campo Cash usando cash_ending si es más preciso.
        
        El tag CashAndCashEquivalentsAtCarryingValue a veces se mapea a cash_ending
        (del Cash Flow) en lugar de cash (del Balance Sheet). Esta función corrige
        eso usando el valor correcto.
        """
        cash_field = balance_map.get('cash')
        cash_ending_field = balance_map.get('cash_ending')
        
        if not cash_field or not cash_ending_field:
            return
        
        cash_values = cash_field.get('values', [])
        cash_ending_values = cash_ending_field.get('values', [])
        
        if not cash_values or not cash_ending_values:
            return
        
        # Verificar si cash_ending tiene valores significativamente mayores
        # (indica que cash usa un tag incorrecto como 'Cash' simple)
        should_replace = False
        for i in range(min(len(cash_values), len(cash_ending_values))):
            c = cash_values[i]
            ce = cash_ending_values[i]
            if c is not None and ce is not None and ce > 0:
                # Si cash_ending es más del 50% mayor que cash, usar cash_ending
                if ce > c * 1.5:
                    should_replace = True
                    break
        
        if should_replace:
            logger.info("Normalizing cash field: using cash_ending values (more accurate)")
            # Actualizar el campo cash con los valores de cash_ending
            cash_field['values'] = cash_ending_values.copy()
            cash_field['source_fields'] = cash_ending_field.get('source_fields', [])
            cash_field['normalized'] = True
    
    def _normalize_total_liabilities(
        self,
        balance_fields: List[Dict],
        balance_map: Dict,
        num_periods: int
    ) -> None:
        """
        Corregir total_liabilities si usa LiabilitiesAndStockholdersEquity (= Total Assets).
        
        El cálculo correcto es: Total Liabilities = Total Assets - Total Equity
        """
        total_liabilities_field = balance_map.get('total_liabilities')
        total_assets_field = balance_map.get('total_assets')
        total_equity_field = balance_map.get('total_equity')
        
        if not total_liabilities_field or not total_assets_field or not total_equity_field:
            return
        
        liab_values = total_liabilities_field.get('values', [])
        assets_values = total_assets_field.get('values', [])
        equity_values = total_equity_field.get('values', [])
        
        if not liab_values or not assets_values or not equity_values:
            return
        
        # Verificar si total_liabilities == total_assets (indica uso del tag incorrecto)
        should_recalculate = False
        for i in range(min(len(liab_values), len(assets_values))):
            liab = liab_values[i]
            assets = assets_values[i]
            if liab is not None and assets is not None and assets > 0:
                # Si son iguales (o muy cercanos), recalcular
                if abs(liab - assets) / assets < 0.01:
                    should_recalculate = True
                    break
        
        if should_recalculate:
            logger.info("Recalculating total_liabilities: Assets - Equity")
            new_liab = []
            for i in range(num_periods):
                assets = assets_values[i] if i < len(assets_values) else None
                equity = equity_values[i] if i < len(equity_values) else None
                
                if assets is not None and equity is not None:
                    new_liab.append(assets - equity)
                else:
                    new_liab.append(None)
            
            total_liabilities_field['values'] = new_liab
            total_liabilities_field['source_fields'] = ['total_assets', 'total_equity']
            total_liabilities_field['calculated'] = True
            total_liabilities_field['normalized'] = True
    
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

